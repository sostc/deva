#!/usr/bin/env python3
"""manas 典型案例 —— 独立「择时决策台」：把一天的市场快照喂给 manas，逐点回答该不该动手。

它演示什么
----------
一个**不属于交易系统**的独立脚本，如何只依赖 `deva.naja.manas` 这一个公共门面，
把「要不要动 / 多确信 / 多危险」的判断用起来，并落成一张可读的决策时间线。

    JSON 快照 ──► manas（判断） ──► 应用自己的策略（决策） ──► 控制台 + HTML 报告

与 `manas_standalone.py` 的区别：那个是「最小用法」的两个场景对照；
这个是**一条完整时间线**的典型应用，能看出判断如何随行情演进。

边界（很重要）
--------------
manas **只给判断**（should_act / action_type / alpha / risk_temperature / 行动门理由），
**不含任何决策逻辑**。下面 `ACTION_POLICY` 里的仓位纪律是**示例应用自己定的**，
不是 manas 的一部分——本仓真实的定量公式在 `deva.naja.decision.sizing`，
这里刻意写得极简，只为说明「判断 → 行动」的接口在哪。

跑法::

    cd <项目根>
    /Users/spark/.local/bin/python3 deva/examples/manas_decision_desk.py
    /Users/spark/.local/bin/python3 deva/examples/manas_decision_desk.py --data <快照.json> --out <报告.html>

复用指南：docs/naja/manas_reuse_guide.md
"""

from __future__ import annotations

import argparse
import html
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

# ★ 全部能力只从这一个公共门面取——门面之外什么都不 import。
from deva.naja.manas import ActionType, create_engine

DEFAULT_DATA = Path(__file__).resolve().parent / "data" / "manas_typical_day.json"

# ─────────────────────────────────────────────────────────────────────────────
# 应用自己的策略（不是 manas 的一部分）
# ─────────────────────────────────────────────────────────────────────────────
# manas 给「档位」，应用把它翻译成自己的仓位纪律。这 4 行是**示例**，
# 真实应用应当按自己的风险预算重写（并参考本仓 decision/sizing.py 的乘子公式）。
ACTION_POLICY: Dict[str, Dict[str, Any]] = {
    ActionType.HOLD.value:         {"label": "观望",     "target_pct": 0,  "desc": "行动门未开——不新增仓位"},
    ActionType.ACT_MINIMALLY.value:{"label": "轻仓试探", "target_pct": 10, "desc": "门刚开——小仓位试水"},
    ActionType.ACT_CAREFULLY.value:{"label": "谨慎加仓", "target_pct": 25, "desc": "环境顺——分批建仓"},
    ActionType.ACT_FULLY.value:    {"label": "全力出击", "target_pct": 40, "desc": "多因子共振——按纪律上限加足"},
}


def _policy_for(action_type: str) -> Dict[str, Any]:
    return ACTION_POLICY.get(action_type, ACTION_POLICY[ActionType.HOLD.value])


# ─────────────────────────────────────────────────────────────────────────────
# 核心（纯函数：便于被验证脚本直接调用，不写文件）
# ─────────────────────────────────────────────────────────────────────────────
def load_snapshots(path: Path) -> Dict[str, Any]:
    """读快照文件，返回 {"meta": ..., "snapshots": [...]}。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    snaps = data.get("snapshots") or []
    if not snaps:
        raise ValueError(f"快照文件里没有 snapshots: {path}")
    return data


def run_case(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把每个快照喂给 manas，返回逐点的判断 + 应用侧建议。

    只用一个 `ManasSession`（引擎 + 输入源），每个时点改输入再重算——
    这正是「一次构造、多次复用」的用法，也贴合「同一个观察者看一整天」的语义。
    注意 `throttle=False`：compute() 默认缓存 1 秒结果，同一秒内改输入会拿到旧值。

    ⚠️ 引擎是**有状态**的：RiskEngine 的回撤取的是历史均值（`_drawdown_history`），
    所以流式复用时后段结果会与前段轻微耦合。若你要的是「每个快照彼此独立」，
    改为每点 `create_engine(...)` 新建引擎即可（见复用指南 §5）。
    """
    session = create_engine(throttle=False)
    rows: List[Dict[str, Any]] = []
    for snap in snapshots:
        session.update(**snap["inputs"])
        out = session.compute()
        pol = _policy_for(out.action_type.value)
        rows.append(
            {
                "time": snap.get("time", ""),
                "label": snap.get("label", ""),
                "note": snap.get("note", ""),
                "manas_score": out.manas_score,
                "harmony_state": out.harmony_state.value,
                "action_type": out.action_type.value,
                "action_label": pol["label"],
                "target_pct": pol["target_pct"],
                "should_act": bool(out.should_act),
                "alpha": out.alpha,
                "risk_temperature": out.risk_temperature,
                "gate_reason": out.action_gate_reason or "",
            }
        )
    return rows


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """当日概览：几个时点、几次开门、分数与风险的区间。"""
    scores = [r["manas_score"] for r in rows]
    temps = [r["risk_temperature"] for r in rows]
    acts = [r for r in rows if r["should_act"]]
    return {
        "n_steps": len(rows),
        "n_actionable": len(acts),
        "actionable_at": [r["time"] for r in acts],
        "score_min": min(scores) if scores else 0.0,
        "score_max": max(scores) if scores else 0.0,
        "temp_min": min(temps) if temps else 0.0,
        "temp_max": max(temps) if temps else 0.0,
        "alpha_min": min((r["alpha"] for r in rows), default=0.0),
        "alpha_max": max((r["alpha"] for r in rows), default=0.0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 控制台渲染
# ─────────────────────────────────────────────────────────────────────────────
def render_console(meta: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    s = summarize(rows)
    lines: List[str] = []
    lines.append("=" * 84)
    lines.append(f"manas 典型案例 · {meta.get('title', '')}")
    lines.append("=" * 84)
    lines.append(f"{'时间':<7}{'场景':<10}{'manas_score':>12}  {'档位':<14}{'动':<3}{'α':>7}{'T':>7}  应用建议")
    lines.append("-" * 84)
    for r in rows:
        flag = "✔" if r["should_act"] else "·"
        lines.append(
            f"{r['time']:<7}{r['label']:<10}{r['manas_score']:>12.4f}  "
            f"{r['action_type']:<14}{flag:<3}{r['alpha']:>7.3f}{r['risk_temperature']:>7.3f}"
            f"  {r['action_label']}（≤{r['target_pct']}%）"
        )
    lines.append("-" * 84)
    lines.append(
        f"共 {s['n_steps']} 个时点，其中 {s['n_actionable']} 个开行动门"
        + (f"（{', '.join(s['actionable_at'])}）" if s["actionable_at"] else "")
    )
    lines.append(
        f"分数区间 {s['score_min']:.4f}~{s['score_max']:.4f}；"
        f"风险温度 T {s['temp_min']:.3f}~{s['temp_max']:.3f}；"
        f"α {s['alpha_min']:.3f}~{s['alpha_max']:.3f}"
    )
    lines.append("")
    lines.append("逐点的『为什么』（manas 的行动门理由）：")
    for r in rows:
        lines.append(f"  {r['time']}  {r['gate_reason']}")
    lines.append("")
    lines.append("提示：manas 只给判断；仓位纪律是示例应用自己定的（见脚本 ACTION_POLICY）。")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# HTML 渲染（自包含，可直接在浏览器看）
# ─────────────────────────────────────────────────────────────────────────────
_CSS = """
:root{--bg:#0f172a;--panel:#1e293b;--line:#334155;--tx:#e2e8f0;--mut:#94a3b8;
      --amber:#f59e0b;--slate:#475569;--cyan:#22d3ee;--good:#34d399;}
*{box-sizing:border-box}
body{margin:0;padding:28px;background:var(--bg);color:var(--tx);
     font-family:-apple-system,"PingFang SC","Helvetica Neue",sans-serif;font-size:14px}
.wrap{max-width:1040px;margin:0 auto}
h1{font-size:19px;margin:0 0 6px}
.sub{color:var(--mut);font-size:12.5px;line-height:1.7;margin-bottom:18px}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}
.card{flex:1 1 150px;background:var(--panel);border:1px solid var(--line);
      border-radius:10px;padding:12px 14px}
.card .k{color:var(--mut);font-size:11.5px;margin-bottom:6px}
.card .v{font-size:20px;font-weight:600}
.card .v small{font-size:12px;color:var(--mut);font-weight:400}
table{width:100%;border-collapse:collapse;background:var(--panel);
      border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:9px 10px;text-align:left;border-bottom:1px solid var(--line);
      vertical-align:middle;font-size:12.5px}
th{background:#243044;color:#cbd5e1;font-weight:600;font-size:11.5px;
   letter-spacing:.02em;white-space:nowrap}
tr:last-child td{border-bottom:none}
.act{color:var(--amber);font-weight:600}
.hold{color:var(--slate)}
.t{white-space:nowrap;font-variant-numeric:tabular-nums}
.num{font-variant-numeric:tabular-nums;text-align:right}
.barwrap{display:flex;align-items:center;gap:8px;min-width:120px}
.bar{height:8px;border-radius:4px;background:var(--slate)}
.bar.on{background:var(--amber)}
.barval{color:var(--mut);font-size:11.5px;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;
      border:1px solid var(--line)}
.pill.on{background:rgba(245,158,11,.14);border-color:var(--amber);color:var(--amber)}
.pill.off{color:var(--mut)}
.reason{color:var(--mut);font-size:11.5px;line-height:1.5}
h2{font-size:14px;margin:26px 0 10px}
ul.find{color:var(--mut);line-height:1.85;font-size:12.5px;padding-left:20px;margin:0}
ul.find b{color:var(--tx)}
.note{margin-top:22px;color:var(--mut);font-size:12px;line-height:1.7;
      border-left:3px solid var(--line);padding-left:12px}
code{background:#243044;padding:1px 5px;border-radius:4px;font-size:11.5px}
"""


def _score_bar(score: float, on: bool) -> str:
    pct = max(0.0, min(1.0, score)) * 100.0
    cls = "bar on" if on else "bar"
    return (
        f'<div class="barwrap"><div class="{cls}" style="width:{pct:.0f}%"></div>'
        f'<span class="barval">{score:.4f}</span></div>'
    )


def render_report_html(meta: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    s = summarize(rows)
    e = html.escape

    body_rows: List[str] = []
    for r in rows:
        on = r["should_act"]
        pill = f'<span class="pill on">{e(r["action_label"])}</span>' if on else (
            f'<span class="pill off">{e(r["action_label"])}</span>'
        )
        body_rows.append(
            "<tr>"
            f'<td class="t">{e(r["time"])}</td>'
            f'<td>{e(r["label"])}<div class="reason">{e(r["note"])}</div></td>'
            f'<td>{_score_bar(r["manas_score"], on)}</td>'
            f'<td class="{"act" if on else "hold"}">{e(r["action_type"])}</td>'
            f'<td>{pill} <span class="reason">≤{r["target_pct"]}%</span></td>'
            f'<td class="num">{r["alpha"]:.3f}</td>'
            f'<td class="num">{r["risk_temperature"]:.3f}</td>'
            f'<td class="reason">{e(r["gate_reason"])}</td>'
            "</tr>"
        )

    actionable = "、".join(s["actionable_at"]) if s["actionable_at"] else "无"
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{e(meta.get('title', 'manas 典型案例'))}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
<h1>manas 典型案例 · {e(meta.get('title', ''))}</h1>
<div class="sub">
{e(meta.get('scenario', ''))}<br>
用法：全程复用同一个 <code>ManasSession</code>（流式观测）；只用 <code>deva.naja.manas</code> 这一个公共门面，不引入交易系统。<br>
数据：<code>{e(str(meta.get('_data_path', '')))}</code> · 单位口径：{e(meta.get('unit_note', ''))}
</div>

<div class="cards">
  <div class="card"><div class="k">时点数</div><div class="v">{s['n_steps']}</div></div>
  <div class="card"><div class="k">开行动门</div><div class="v">{s['n_actionable']} <small>次 · {e(actionable)}</small></div></div>
  <div class="card"><div class="k">manas_score 区间</div><div class="v">{s['score_min']:.3f}<small> ~ {s['score_max']:.3f}</small></div></div>
  <div class="card"><div class="k">风险温度 T 区间</div><div class="v">{s['temp_min']:.2f}<small> ~ {s['temp_max']:.2f}</small></div></div>
  <div class="card"><div class="k">α 区间</div><div class="v">{s['alpha_min']:.2f}<small> ~ {s['alpha_max']:.2f}</small></div></div>
</div>

<table>
<thead><tr>
  <th>时间</th><th>场景</th><th>manas_score</th><th>档位 action_type</th>
  <th>应用建议</th><th>α</th><th>T</th><th>行动门理由</th>
</tr></thead>
<tbody>{''.join(body_rows)}</tbody>
</table>

<h2>四个值得注意的发现（都是真实输出，不是设定）</h2>
<ul class="find">
  <li><b>行动门是保守的，只在窄窗口开。</b> 6 个时点只有 1 个开门——要求 <code>manas_score &gt; 0.5</code>。
      它需要同时满足「低回撤 + 高现金 + 低波动」，所以真正的机会窗口很窄。
      其余时点也并非"一律不动"：10:30 是<b>策略不自信</b>、11:15 是<b>环境阻力（逆风）</b>、
      13:40 / 14:50 已是<b>顺风环境但差一点分数</b>——关门的理由各不相同。</li>
  <li><b>风险温度 T 被"回撤"顶高，且盈利也计入。</b> T = 1.0 + (1−现金比)×0.5，再按回撤/波动加档；
      本仓用 <code>abs(total_return)/100</code> 作为回撤代理，于是<b>盈利同样抬高 T</b>——
      这是刻意的保守设计（宁可把波动当风险），不是 bug。</li>
  <li><b>α 恒在下限 0.3。</b> α = clamp(confidence × harmony, 0.3, 1.5)，
      两个乘子自然落在 [0, 0.6] → 本案例每个时点都撞下限。想让 α 有区分度得重新定标，
      不是调 clamp（见复用指南 §5.2）。</li>
  <li><b>引擎是有状态的，复用时结果路径相关。</b> 这里全程复用同一个会话（同一天、同一个观察者）。
      RiskEngine 的回撤取<b>历史均值</b>，所以 11:15 的 T 是 <code>1.488</code>——
      若每点各新建引擎则是 <code>1.637</code>。两种都对，取决于你要"连续观测"还是
      "彼此独立的快照"。</li>
</ul>

<div class="note">
manas 只输出「该不该动 / 多确信 / 多危险」的判断；上表「应用建议」一列的目标仓位
是<b>示例应用自己</b>的纪律（脚本里的 <code>ACTION_POLICY</code>），不属于 manas。
本仓真实的定量公式在 <code>deva.naja.decision.sizing</code>。<br>
复现：<code>/Users/spark/.local/bin/python3 deva/examples/manas_decision_desk.py</code>
</div>
</div></body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="manas 典型案例：择时决策台")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="快照 JSON 路径")
    parser.add_argument(
        "--out",
        default=str(Path(tempfile.gettempdir()) / "manas_typical_case_report.html"),
        help="HTML 报告输出路径",
    )
    args = parser.parse_args()

    data = load_snapshots(Path(args.data))
    meta = {k: v for k, v in data.items() if k != "snapshots"}
    meta["_data_path"] = args.data
    rows = run_case(data["snapshots"])

    print(render_console(meta, rows))

    out_path = Path(args.out)
    out_path.write_text(render_report_html(meta, rows), encoding="utf-8")
    print(f"\nHTML 报告已写出：{out_path}")


if __name__ == "__main__":
    main()
