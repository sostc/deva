"""Stock static search and rendering helpers for admin runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Generator
import time
import re

from walrus import Database
from whoosh import qparser
import whoosh
import pandas as pd

from deva import first, NB


db = Database()
cache = db.cache()


class Stock(object):
    """股票基础信息查询."""

    _index_name = "code_index"
    _index_path = str((Path(__file__).resolve().parent / "stock_index").resolve())

    @classmethod
    def get_name(cls, code):
        stock = cls.search_stocks(code) >> first
        return stock["name"]

    @classmethod
    def search_stocks(cls, query: str, limit: int = 50) -> Generator[dict, None, None]:
        _ix = whoosh.index.open_dir(cls._index_path, cls._index_name)
        qp = qparser.MultifieldParser(
            ["code", "name", "business", "tags", "industry", "concepts"],
            _ix.schema,
        )
        q = qp.parse(query)
        with _ix.searcher() as searcher:
            results = searcher.search(q, limit=limit)
            for stock in results:
                yield dict(stock)

    @classmethod
    def get_all_stocks(cls) -> Generator[dict, None, None]:
        _ix = whoosh.index.open_dir(cls._index_path, cls._index_name)
        with _ix.searcher() as searcher:
            results = searcher.documents()
            for stock in results:
                yield dict(stock)

    @classmethod
    def render(cls, df):
        basic_df = NB("naja")["basic_df"]
        return df.merge(basic_df, on="code", how="left")

    @classmethod
    def get_basics(cls):
        return _get_tushare_basics()


def _get_tushare_pro_api():
    import tushare as ts
    from deva.config import config
    token = config.get("tushare.token")
    if token:
        ts.set_token(token)
        return ts.pro_api()
    return None


def _get_tushare_basics():
    import tushare as ts
    import pandas as pd
    
    pro = _get_tushare_pro_api()
    if pro is not None:
        try:
            stock_basic = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
            daily_basic = pro.daily_basic(ts_code='', trade_date='', fields='ts_code,pe,pb,total_mv,circ_mv')
            
            stock_basic['code'] = stock_basic['symbol'].str.zfill(6)
            daily_basic['code'] = daily_basic['ts_code'].str[:6].str.zfill(6)
            
            merged = stock_basic.merge(daily_basic[['code', 'pe', 'total_mv']], on='code', how='left')
            merged = merged.rename(columns={
                'total_mv': 'totalAssets',
                'list_date': 'timeToMarket'
            })
            merged = merged.set_index('code')
            return merged
        except Exception as e:
            emit_stock_log(None, "WARNING", "tushare pro api failed, fallback to old api", error=str(e))
    
    return ts.get_stock_basics()

    @classmethod
    def gen_render_basic(cls):
        # Keep API compatibility while removing pytdx dependency.
        df = _build_em_industry_df()
        NB("naja")["basic_df"] = df

    @classmethod
    def get_property(cls, code, property="pe"):
        return cls.get_basics().loc[code][property]


def emit_stock_log(log_func, level, message, **extra):
    if callable(log_func):
        log_func(level, message, **extra)


def normalize_stock_code(v):
    text = str(v or "").strip()
    if not text:
        return ""
    # Normalize common variants: 000001 / SZ000001 / 000001.SZ / sh600000 ...
    if text.isdigit() and len(text) <= 6:
        return text.zfill(6)
    m = re.search(r"(\d{6})", text)
    if m:
        return m.group(1)
    return text


def pick_first_existing_column(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def normalize_and_dedup_stock_rows(df):
    out = df.copy()
    if "code" not in out.columns:
        out["code"] = ""
    out["code"] = out["code"].map(normalize_stock_code)
    out = out[out["code"] != ""]
    out = out.drop_duplicates(subset=["code"], keep="first")
    return out


def build_market_universe_dataframe(log_func=None):
    """Build full A-share universe as base rows."""
    import akshare as ak

    code_name_fetchers = [
        "stock_info_a_code_name",
        "stock_zh_a_name",
    ]
    code_name_candidates = []
    for fn_name in code_name_fetchers:
        fn = getattr(ak, fn_name, None)
        if not callable(fn):
            continue
        try:
            raw = fn()
            if raw is None or raw.empty:
                continue
            code_col = pick_first_existing_column(raw, ["代码", "证券代码", "code"])
            name_col = pick_first_existing_column(raw, ["名称", "name"])
            if code_col is None:
                continue
            candidate = pd.DataFrame({
                "code": raw[code_col].map(normalize_stock_code),
                "name": raw[name_col].astype(str) if name_col else raw[code_col].map(normalize_stock_code),
            })
            candidate = normalize_and_dedup_stock_rows(candidate)
            if not candidate.empty:
                code_name_candidates.append((fn_name, candidate))
                emit_stock_log(log_func, "INFO", "load market code-name api", api=fn_name, rows=int(len(candidate)))
        except Exception as e:
            emit_stock_log(log_func, "WARNING", "market code-name api failed", api=fn_name, error=str(e))

    spot_fetchers = [
        "stock_zh_a_spot_em",
        "stock_zh_a_spot",
    ]
    spot_df = None
    spot_api = None
    for fn_name in spot_fetchers:
        fn = getattr(ak, fn_name, None)
        if not callable(fn):
            continue
        try:
            raw = fn()
            if raw is None or raw.empty:
                continue
            spot_df = raw
            spot_api = fn_name
            emit_stock_log(log_func, "INFO", "load market spot api", api=fn_name, rows=int(len(raw)))
            break
        except Exception as e:
            emit_stock_log(log_func, "WARNING", "market spot api failed", api=fn_name, error=str(e))

    spot_base = None
    if spot_df is not None and not spot_df.empty:
        code_col = pick_first_existing_column(spot_df, ["代码", "证券代码", "code"])
        name_col = pick_first_existing_column(spot_df, ["名称", "name"])
        if code_col is not None:
            spot_base = pd.DataFrame({
                "code": spot_df[code_col].map(normalize_stock_code),
                "name": spot_df[name_col].astype(str) if name_col else spot_df[code_col].map(normalize_stock_code),
            })
            spot_base = normalize_and_dedup_stock_rows(spot_base)

    base_api = None
    if code_name_candidates:
        base_api, out = max(code_name_candidates, key=lambda x: len(x[1]))
    elif spot_base is not None and not spot_base.empty:
        base_api, out = (spot_api or "spot", spot_base)
    else:
        raise RuntimeError("no available market universe api")

    # If chosen base is unexpectedly small, try spot rows as fallback.
    if len(out) < 1000 and spot_base is not None and len(spot_base) > len(out):
        emit_stock_log(
            log_func,
            "WARNING",
            "market universe base too small, switch to spot base",
            base_api=base_api,
            base_rows=int(len(out)),
            spot_rows=int(len(spot_base)),
        )
        out = spot_base
        base_api = spot_api or "spot"

    out = out.copy()
    if spot_df is not None and not spot_df.empty:
        spot_code_col = pick_first_existing_column(spot_df, ["代码", "证券代码", "code"])
        industry_col = pick_first_existing_column(spot_df, ["行业", "所属行业", "行业名称"])
        if spot_code_col is not None and industry_col is not None:
            industry_map = pd.DataFrame({
                "code": spot_df[spot_code_col].map(normalize_stock_code),
                "industry": spot_df[industry_col].astype(str),
            })
            industry_map = normalize_and_dedup_stock_rows(industry_map[["code", "industry"]])
            out = out.merge(industry_map, on="code", how="left")

    if "industry" not in out.columns:
        out["industry"] = "unknown"
    out["industry"] = out["industry"].fillna("").astype(str).replace("", "unknown")
    out["blockname"] = "unknown"
    emit_stock_log(log_func, "INFO", "market universe built", api=base_api, rows=int(len(out)))
    return out


def build_tushare_industry_mapping_dataframe(log_func=None):
    """Secondary fill source for industry/blockname from tushare basics."""
    basic_df = Stock.get_basics().reset_index()
    if "index" in basic_df.columns and "code" not in basic_df.columns:
        basic_df = basic_df.rename(columns={"index": "code"})
    code_col = pick_first_existing_column(basic_df, ["code", "代码", "证券代码"])
    if code_col is None:
        raise RuntimeError(f"tushare basics missing code column: {list(basic_df.columns)}")

    name_col = pick_first_existing_column(basic_df, ["name", "名称"])
    industry_col = pick_first_existing_column(basic_df, ["industry", "行业"])
    if industry_col is None:
        raise RuntimeError("tushare basics missing industry column")

    out = pd.DataFrame({
        "code": basic_df[code_col].map(normalize_stock_code),
        "name": basic_df[name_col].astype(str) if name_col else basic_df[code_col].map(normalize_stock_code),
        "industry": basic_df[industry_col].astype(str),
    })
    out = normalize_and_dedup_stock_rows(out)
    out["industry"] = out["industry"].fillna("").astype(str).str.strip()
    out = out[out["industry"].ne("")]
    if out.empty:
        raise RuntimeError("tushare industry mapping is empty")
    out["blockname"] = out["industry"]
    emit_stock_log(log_func, "INFO", "tushare industry mapping built", rows=int(len(out)))
    return out


def build_ths_concept_mapping_dataframe(log_func=None):
    import akshare as ak

    block_map = {}
    name_map = {}

    # Compatible with multiple akshare versions.
    name_fetchers = [
        "stock_board_concept_name_ths",
        "stock_board_concept_name_em",
    ]
    concept_names = None
    for fn_name in name_fetchers:
        fn = getattr(ak, fn_name, None)
        if callable(fn):
            try:
                concept_names = fn()
                emit_stock_log(log_func, "INFO", "load board list api", api=fn_name)
                break
            except Exception as e:
                emit_stock_log(log_func, "WARNING", "board list api failed", api=fn_name, error=str(e))

    if concept_names is None or concept_names.empty:
        raise RuntimeError("no available board list api in current akshare")
    block_col = pick_first_existing_column(concept_names, ["概念名称", "板块名称", "名称", "name"])
    if block_col is None:
        raise RuntimeError(f"unsupported board list columns: {list(concept_names.columns)}")
    blocks = []
    for x in concept_names[block_col].dropna().tolist():
        b = str(x).strip()
        if (not b) or b.isdigit():
            continue
        blocks.append(b)
    blocks = sorted(set(blocks))
    emit_stock_log(log_func, "INFO", "load ths concept boards", count=len(blocks))

    cons_fetchers = [
        "stock_board_concept_cons_ths",
        "stock_board_concept_cons_em",
    ]
    for block in blocks:
        cons = None
        for fn_name in cons_fetchers:
            fn = getattr(ak, fn_name, None)
            if not callable(fn):
                continue
            try:
                cons = fn(symbol=block)
                break
            except Exception as e:
                emit_stock_log(log_func, "WARNING", "single board api failed", api=fn_name, block=block, error=str(e))
        if cons is None or cons.empty:
            continue
        code_col = "代码" if "代码" in cons.columns else cons.columns[0]
        name_col = "名称" if "名称" in cons.columns else (cons.columns[1] if len(cons.columns) > 1 else code_col)
        for _, row in cons.iterrows():
            code = normalize_stock_code(row.get(code_col))
            if not code:
                continue
            block_map.setdefault(code, set()).add(block)
            if code not in name_map:
                name_map[code] = str(row.get(name_col, code))

    if not block_map:
        raise RuntimeError("no ths board constituents loaded")

    rows = []
    for code, blocks_set in block_map.items():
        rows.append({
            "code": code,
            "name": name_map.get(code, code),
            "blockname": "|".join(sorted(blocks_set)),
        })
    return pd.DataFrame(rows)


def build_em_industry_mapping_dataframe(log_func=None):
    import akshare as ak

    # 1) Prefer industry-board constituent mapping (better coverage than spot snapshot in some envs).
    try:
        board_names = None
        board_name_api = None
        for fn_name in ["stock_board_industry_name_em", "stock_board_industry_name_ths"]:
            fn = getattr(ak, fn_name, None)
            if not callable(fn):
                continue
            try:
                board_names = fn()
                board_name_api = fn_name
                emit_stock_log(log_func, "INFO", "load industry board list api", api=fn_name, rows=int(len(board_names)))
                break
            except Exception as e:
                emit_stock_log(log_func, "WARNING", "industry board list api failed", api=fn_name, error=str(e))

        if board_names is not None and not board_names.empty:
            board_col = pick_first_existing_column(board_names, ["板块名称", "行业名称", "名称", "name"])
            if board_col:
                boards = []
                for x in board_names[board_col].dropna().tolist():
                    b = str(x).strip()
                    if b:
                        boards.append(b)
                boards = sorted(set(boards))
                emit_stock_log(log_func, "INFO", "load industry boards", api=board_name_api, count=len(boards))

                industry_map = {}
                name_map = {}
                cons_ok = 0
                for board in boards:
                    cons = None
                    for fn_name in ["stock_board_industry_cons_em", "stock_board_industry_cons_ths"]:
                        fn = getattr(ak, fn_name, None)
                        if not callable(fn):
                            continue
                        try:
                            cons = fn(symbol=board)
                            if cons is not None and not cons.empty:
                                cons_ok += 1
                            break
                        except Exception as e:
                            emit_stock_log(log_func, "WARNING", "single industry board api failed", api=fn_name, board=board, error=str(e))
                    if cons is None or cons.empty:
                        continue
                    code_col = pick_first_existing_column(cons, ["代码", "证券代码", "code"])
                    name_col = pick_first_existing_column(cons, ["名称", "name"])
                    if code_col is None:
                        continue
                    for _, row in cons.iterrows():
                        code = normalize_stock_code(row.get(code_col))
                        if not code:
                            continue
                        industry_map.setdefault(code, set()).add(board)
                        if code not in name_map:
                            name_map[code] = str(row.get(name_col, code))

                if industry_map:
                    rows = []
                    for code, industry_set in industry_map.items():
                        rows.append({
                            "code": code,
                            "name": name_map.get(code, code),
                            "industry": "|".join(sorted(industry_set)),
                            "blockname": "|".join(sorted(industry_set)),
                        })
                    out = pd.DataFrame(rows)
                    out = normalize_and_dedup_stock_rows(out)
                    emit_stock_log(
                        log_func,
                        "INFO",
                        "industry mapping built from industry boards",
                        boards_total=int(len(boards)),
                        boards_loaded=int(cons_ok),
                        rows=int(len(out)),
                    )
                    return out
    except Exception as e:
        emit_stock_log(log_func, "WARNING", "industry board mapping failed, fallback to spot", error=str(e))

    spot_fetchers = [
        "stock_zh_a_spot_em",
        "stock_zh_a_spot",
    ]
    spot_df = None
    for fn_name in spot_fetchers:
        fn = getattr(ak, fn_name, None)
        if not callable(fn):
            continue
        try:
            spot_df = fn()
            emit_stock_log(log_func, "INFO", "load spot api", api=fn_name, rows=int(len(spot_df)))
            break
        except Exception as e:
            emit_stock_log(log_func, "WARNING", "spot api failed", api=fn_name, error=str(e))

    if spot_df is None or spot_df.empty:
        raise RuntimeError("no available EM spot api")

    code_col = pick_first_existing_column(spot_df, ["代码", "证券代码", "code"])
    name_col = pick_first_existing_column(spot_df, ["名称", "name"])
    block_col = pick_first_existing_column(spot_df, ["行业", "所属行业", "行业名称", "板块名称"])
    if code_col is None or block_col is None:
        raise RuntimeError(f"spot columns missing code/blockname: {list(spot_df.columns)}")

    if name_col is None:
        spot_df["name"] = spot_df[code_col].map(normalize_stock_code)
        name_col = "name"

    out = pd.DataFrame({
        "code": spot_df[code_col].map(normalize_stock_code),
        "name": spot_df[name_col].astype(str),
        "industry": spot_df[block_col].astype(str),
        "blockname": spot_df[block_col].astype(str),
    })
    out = out[out["code"] != ""]
    out = out[out["blockname"].str.strip().ne("")]
    if out.empty:
        raise RuntimeError("em industry mapping is empty")
    out = normalize_and_dedup_stock_rows(out)
    emit_stock_log(log_func, "INFO", "industry mapping built from spot", rows=int(len(out)))
    return out


def refresh_stock_basic_dataframe(log_func=None):
    """Refresh stock basics: full market universe + best-effort blockname enrichment."""
    source = "universe_only"
    try:
        universe_df = build_market_universe_dataframe(log_func=log_func)
    except Exception as e:
        emit_stock_log(log_func, "WARNING", "market universe build failed, fallback to minimal basics", error=str(e))
        try:
            basic_df = Stock.get_basics().reset_index()
            if "index" in basic_df.columns and "code" not in basic_df.columns:
                basic_df = basic_df.rename(columns={"index": "code"})
            basic_df["code"] = basic_df["code"].map(normalize_stock_code)
            if "name" not in basic_df.columns:
                basic_df["name"] = basic_df["code"]
            if "industry" not in basic_df.columns:
                basic_df["industry"] = "unknown"
            basic_df["blockname"] = "unknown"
            keep_cols = ["blockname", "code", "name", "industry", "area", "pe", "totalAssets", "timeToMarket"]
            for c in keep_cols:
                if c not in basic_df.columns:
                    basic_df[c] = None
            df = normalize_and_dedup_stock_rows(basic_df[keep_cols])
            source = "minimal"
        except Exception as eee:
            raise RuntimeError(f"all refresh strategies failed: {eee}") from eee
    else:
        concept_df = None
        industry_df = None
        try:
            concept_df = build_ths_concept_mapping_dataframe(log_func=log_func)
            concept_df = normalize_and_dedup_stock_rows(concept_df[["code", "blockname"]])
            source = "universe+ths"
        except Exception as e:
            emit_stock_log(log_func, "WARNING", "ths block refresh failed", error=str(e))
        try:
            industry_df = build_em_industry_mapping_dataframe(log_func=log_func)
            industry_df = normalize_and_dedup_stock_rows(industry_df[["code", "blockname", "industry"]])
            if source == "universe_only":
                source = "universe+industry"
        except Exception as e:
            emit_stock_log(log_func, "WARNING", "industry block refresh failed", error=str(e))

        df = universe_df.copy()
        if concept_df is not None and not concept_df.empty:
            df = df.merge(concept_df.rename(columns={"blockname": "blockname_ths"}), on="code", how="left")
        else:
            df["blockname_ths"] = None
        if industry_df is not None and not industry_df.empty:
            industry_merge_df = industry_df[["code", "blockname", "industry"]].rename(
                columns={
                    "blockname": "blockname_industry",
                    "industry": "industry_new",
                }
            )
            df = df.merge(industry_merge_df, on="code", how="left")
        else:
            df["blockname_industry"] = None
            df["industry_new"] = None

        df["blockname"] = df["blockname_ths"].fillna("").astype(str).str.strip()
        industry_fill = df["blockname_industry"].fillna("").astype(str).str.strip()
        miss_mask = df["blockname"].eq("")
        df.loc[miss_mask, "blockname"] = industry_fill[miss_mask]
        df.loc[df["blockname"].eq(""), "blockname"] = "unknown"
        # Refresh industry field too: use mapped industry first, fallback to existing industry.
        if "industry" not in df.columns:
            df["industry"] = "unknown"
        old_industry = df["industry"].fillna("").astype(str).str.strip()
        new_industry = df["industry_new"].fillna("").astype(str).str.strip()
        use_new = new_industry.ne("")
        df["industry"] = old_industry
        df.loc[use_new, "industry"] = new_industry[use_new]
        df.loc[df["industry"].eq(""), "industry"] = "unknown"

        # Secondary fill: patch remaining missing industry/blockname from tushare basics.
        block_missing_mask = df["blockname"].fillna("").astype(str).str.strip().isin(["", "unknown"])
        industry_missing_mask = df["industry"].fillna("").astype(str).str.strip().isin(["", "unknown"])
        missing_before = int((block_missing_mask | industry_missing_mask).sum())
        if missing_before > 0:
            try:
                ts_fill_df = build_tushare_industry_mapping_dataframe(log_func=log_func)
                ts_fill_df = normalize_and_dedup_stock_rows(ts_fill_df[["code", "industry", "blockname"]]).rename(
                    columns={
                        "industry": "industry_ts_fill",
                        "blockname": "blockname_ts_fill",
                    }
                )
                df = df.merge(ts_fill_df, on="code", how="left")

                ts_industry = df["industry_ts_fill"].fillna("").astype(str).str.strip()
                ts_block = df["blockname_ts_fill"].fillna("").astype(str).str.strip()

                industry_missing_mask = df["industry"].fillna("").astype(str).str.strip().isin(["", "unknown"])
                block_missing_mask = df["blockname"].fillna("").astype(str).str.strip().isin(["", "unknown"])

                df.loc[industry_missing_mask & ts_industry.ne(""), "industry"] = ts_industry[industry_missing_mask & ts_industry.ne("")]
                df.loc[block_missing_mask & ts_block.ne(""), "blockname"] = ts_block[block_missing_mask & ts_block.ne("")]

                # Keep consistency: if blockname still missing but industry exists, use industry.
                block_missing_mask = df["blockname"].fillna("").astype(str).str.strip().isin(["", "unknown"])
                industry_present_mask = df["industry"].fillna("").astype(str).str.strip().ne("")
                df.loc[block_missing_mask & industry_present_mask, "blockname"] = df.loc[block_missing_mask & industry_present_mask, "industry"]

                df = df.drop(columns=["industry_ts_fill", "blockname_ts_fill"], errors="ignore")

                block_missing_after = df["blockname"].fillna("").astype(str).str.strip().isin(["", "unknown"])
                industry_missing_after = df["industry"].fillna("").astype(str).str.strip().isin(["", "unknown"])
                missing_after = int((block_missing_after | industry_missing_after).sum())
                filled_rows = int(max(0, missing_before - missing_after))
                if filled_rows > 0:
                    source = f"{source}+tushare_fill"
                emit_stock_log(
                    log_func,
                    "INFO",
                    "secondary fill completed",
                    missing_before=missing_before,
                    missing_after=missing_after,
                    filled_rows=filled_rows,
                )
            except Exception as e:
                emit_stock_log(log_func, "WARNING", "secondary fill failed", error=str(e), missing_before=missing_before)

        df = df.drop(columns=["blockname_ths", "blockname_industry", "industry_new"], errors="ignore")
        df = normalize_and_dedup_stock_rows(df)

    NB("naja")["basic_df"] = df
    meta = NB("naja_meta")
    meta["basic_df_updated_at"] = time.time()
    meta["basic_df_source"] = source
    meta["basic_df_rows"] = int(len(df))
    emit_stock_log(log_func, "INFO", "basic_df refreshed", source=source, rows=int(len(df)))
    return {
        "updated_at": meta["basic_df_updated_at"],
        "source": source,
        "rows": int(len(df)),
    }


def get_stock_basic_dataframe_metadata():
    meta = NB("naja_meta")
    return {
        "updated_at": float(meta.get("basic_df_updated_at", 0) or 0),
        "source": meta.get("basic_df_source", "unknown"),
        "rows": int(meta.get("basic_df_rows", 0) or 0),
    }


def ensure_stock_basic_dataframe_fresh(max_age_seconds=24 * 60 * 60, log_func=None):
    meta = get_stock_basic_dataframe_metadata()
    now = time.time()
    need_refresh = (meta["updated_at"] <= 0) or ((now - meta["updated_at"]) > max_age_seconds)
    if need_refresh:
        emit_stock_log(log_func, "INFO", "basic_df stale or missing, start refresh", max_age_seconds=max_age_seconds)
        return refresh_stock_basic_dataframe(log_func=log_func)
    emit_stock_log(log_func, "INFO", "basic_df still fresh, skip refresh", age_seconds=int(now - meta["updated_at"]))
    return meta


# Compatibility aliases
_emit = emit_stock_log
_normalize_code = normalize_stock_code
_pick_column = pick_first_existing_column
_build_ths_block_df = build_ths_concept_mapping_dataframe
_build_em_industry_df = build_em_industry_mapping_dataframe
refresh_basic_df = refresh_stock_basic_dataframe
get_basic_df_meta = get_stock_basic_dataframe_metadata
ensure_basic_df_fresh = ensure_stock_basic_dataframe_fresh
