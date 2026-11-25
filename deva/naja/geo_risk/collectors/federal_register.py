"""
Federal Register 采集器（公开 JSON API，无 key）

文档：https://www.federalregister.gov/developers/documentation/api/v1
只读、按日更设计；不做分页循环，由 jobs 层决定页数。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .base import RawItem, http_get_json

API_URL = "https://www.federalregister.gov/api/v1/documents.json"

#: 只要这些字段，降低传输与解析成本
FIELDS = (
    "document_number",
    "title",
    "abstract",
    "publication_date",
    "html_url",
    "agencies",
    "type",
)


def build_params(*, term: str = "", agencies: Sequence[str] = (), since: str = "",
                 per_page: int = 20, page: int = 1) -> Dict[str, Any]:
    """构造查询参数（纯函数，便于单测）。"""
    params: Dict[str, Any] = {
        "per_page": per_page,
        "page": page,
        "order": "newest",
        "fields[]": list(FIELDS),
    }
    if term:
        params["conditions[term]"] = term
    if agencies:
        params["conditions[agencies][]"] = list(agencies)
    if since:
        params["conditions[publication_date][gte]"] = since
    return params


def parse_documents(payload: Mapping[str, Any]) -> List[RawItem]:
    """把 API 返回的 results 转成 RawItem。"""
    items: List[RawItem] = []
    for doc in payload.get("results") or []:
        doc_no = str(doc.get("document_number") or "").strip()
        title = str(doc.get("title") or "").strip()
        if not doc_no or not title:
            continue
        agency_names = []
        for a in doc.get("agencies") or []:
            name = a.get("raw_name") or a.get("name") or ""
            if name:
                agency_names.append(str(name))
        body = " | ".join(x for x in [str(doc.get("abstract") or "").strip(), "; ".join(agency_names)] if x)
        items.append(RawItem(
            source="federal_register",
            url=str(doc.get("html_url") or f"https://www.federalregister.gov/d/{doc_no}"),
            title=title,
            published_at=str(doc.get("publication_date") or ""),
            body=body,
            external_id=doc_no,
            event_hint=f"policy_{doc.get('type') or 'document'}",
        ))
    return items


def fetch_documents(*, term: str = "", agencies: Sequence[str] = (), since: str = "",
                    per_page: int = 20, page: int = 1,
                    timeout: float = 15.0) -> List[RawItem]:
    """真实抓取（只读）。失败直接抛给调用方，由 jobs 层决定是否重试。"""
    payload = http_get_json(
        API_URL,
        build_params(term=term, agencies=agencies, since=since,
                     per_page=per_page, page=page),
        timeout=timeout,
    )
    return parse_documents(payload)
