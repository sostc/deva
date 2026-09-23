"""
IMA 知识库适配器

封装腾讯 IMA 知识库的 OpenAPI 调用，作为 Naja 的外部知识底座。

能力：
- search(query, limit): 语义检索知识库片段
- import_doc(title, content, folder_id): 写入笔记/文档

设计原则：
- 失败安全：网络/凭证/配额问题返回空结果，不抛异常中断主流程
- 凭证优先级：环境变量 > ~/.config/ima/ 标准凭证文件
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)


# IMA API 基础地址
IMA_API_BASE = "https://ima.qq.com/openapi"
# 默认知识库 ID：naja 专用知识库（与用户原有知识库隔离）
DEFAULT_KB_ID = "4hAFNbEqg_xUwIHQyX9hZtkHtZByi6yKmsRvNYoQuBg="
# 用户原有知识库（决战 2050），可选用于检索已有研报
EXISTING_KB_ID = "cP5JYg2B-mVAzee2TMF6FoKQnSSnK6rgttsDETpj7To="

# 检索超时（秒）
SEARCH_TIMEOUT = 10
# 写入超时（秒）
IMPORT_TIMEOUT = 15

# 标准凭证目录（IMA skill 约定）
IMA_CONFIG_DIR = Path.home() / ".config" / "ima"


def _load_credentials() -> tuple[str, str]:
    """
    加载 IMA 凭证。

    优先级：
    1. 环境变量 IMA_OPENAPI_CLIENTID / IMA_OPENAPI_APIKEY
    2. 标准凭证文件 ~/.config/ima/client_id 和 ~/.config/ima/api_key
    """
    client_id = os.environ.get("IMA_OPENAPI_CLIENTID", "").strip()
    api_key = os.environ.get("IMA_OPENAPI_APIKEY", "").strip()

    if client_id and api_key:
        return client_id, api_key

    # 兜底：从标准凭证文件读取
    try:
        if not client_id and (IMA_CONFIG_DIR / "client_id").exists():
            client_id = (IMA_CONFIG_DIR / "client_id").read_text(encoding="utf-8").strip()
        if not api_key and (IMA_CONFIG_DIR / "api_key").exists():
            api_key = (IMA_CONFIG_DIR / "api_key").read_text(encoding="utf-8").strip()
    except OSError as e:
        log.warning(f"[ImaClient] 读取凭证文件失败: {e}")

    return client_id, api_key


IMA_CLIENT_ID, IMA_API_KEY = _load_credentials()


@dataclass
class ImaSnippet:
    """IMA 检索结果片段"""
    title: str
    content: str          # 纯文本内容（highlight 清理后）
    media_id: str
    media_type: str = ""  # doc / folder / image / ...

    def is_usable(self) -> bool:
        """是否为可用的文本内容（跳过文件夹、图片等）"""
        skip_types = {"folder", "image", "audio", "video"}
        if self.media_type in skip_types:
            return False
        return bool(self.content.strip())


class ImaClient:
    """IMA 知识库客户端"""

    def __init__(
        self,
        client_id: str = IMA_CLIENT_ID,
        api_key: str = IMA_API_KEY,
        knowledge_base_id: str = DEFAULT_KB_ID,
    ):
        self.client_id = client_id
        self.api_key = api_key
        self.knowledge_base_id = knowledge_base_id

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.api_key)

    @classmethod
    def for_naja(cls) -> "ImaClient":
        """创建操作 naja 知识库的客户端（Naja 自身知识积累）"""
        return cls(knowledge_base_id=DEFAULT_KB_ID)

    @classmethod
    def for_user_research(cls) -> "ImaClient":
        """创建操作用户原有知识库的客户端（决战 2050，用户已有研报）"""
        return cls(knowledge_base_id=EXISTING_KB_ID)

    def _headers(self) -> Dict[str, str]:
        return {
            "ima-openapi-clientid": self.client_id,
            "ima-openapi-apikey": self.api_key,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    #  检索
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 5) -> List[ImaSnippet]:
        """
        检索知识库

        Args:
            query: 检索关键词
            limit: 返回数量上限

        Returns:
            可用的文本片段列表（已过滤文件夹/图片，按 media_id 去重）
        """
        if not self.is_configured:
            log.debug("[ImaClient] IMA 未配置，跳过检索")
            return []

        if not query or not query.strip():
            return []

        try:
            resp = requests.post(
                f"{IMA_API_BASE}/wiki/v1/search_knowledge",
                headers=self._headers(),
                json={
                    "query": query,
                    "knowledge_base_id": self.knowledge_base_id,
                    "cursor": "",
                },
                timeout=SEARCH_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") not in (0, None) and data.get("err") not in (0, None):
                log.warning(f"[ImaClient] search_knowledge API 错误: {data.get('msg', data)}")
                return []

            items = data.get("data", {}).get("info_list", []) or []
            seen_ids: set = set()
            snippets: List[ImaSnippet] = []

            for item in items:
                media_id = item.get("media_id", "")
                if not media_id or media_id in seen_ids:
                    continue
                seen_ids.add(media_id)

                media_type = str(item.get("media_type", "")).lower()
                highlight = item.get("highlight_content", "") or ""
                title = item.get("title", "") or ""

                # 清理 HTML 高亮标签
                content = re.sub(r"<[^>]+>", "", highlight).strip()
                # 兜底：若 highlight 为空，用标题构造
                if not content and title:
                    content = title

                snippet = ImaSnippet(
                    title=title,
                    content=content,
                    media_id=media_id,
                    media_type=media_type,
                )
                if snippet.is_usable():
                    snippets.append(snippet)
                    if len(snippets) >= limit:
                        break

            log.info(f"[ImaClient] 检索 '{query}' → {len(snippets)} 条可用片段")
            return snippets

        except Exception as e:
            log.warning(f"[ImaClient] 检索失败 query='{query}': {e}")
            return []

    def search_multi(
        self,
        queries: List[str],
        per_query_limit: int = 3,
        total_limit: int = 8,
    ) -> List[ImaSnippet]:
        """
        多关键词检索并去重合并

        用于用多个主题词召回更多相关内容。
        """
        if not queries:
            return []

        seen_ids: set = set()
        merged: List[ImaSnippet] = []

        for q in queries:
            if not q or not q.strip():
                continue
            for s in self.search(q.strip(), limit=per_query_limit):
                if s.media_id in seen_ids:
                    continue
                seen_ids.add(s.media_id)
                merged.append(s)
                if len(merged) >= total_limit:
                    return merged

        return merged

    # ------------------------------------------------------------------
    #  写入
    # ------------------------------------------------------------------

    def import_doc(
        self,
        title: str,
        content: str,
        folder_id: str = "",
    ) -> Optional[str]:
        """
        导入文档到知识库

        两步流程：
        1. import_doc 创建笔记（content_format=1 MARKDOWN）→ note_id
        2. add_knowledge 将笔记添加到知识库（media_type=11）→ media_id

        Args:
            title: 文档标题
            content: 文档内容（Markdown）
            folder_id: 目标文件夹 ID（可选）

        Returns:
            成功返回 media_id，失败返回 None
        """
        if not self.is_configured:
            log.debug("[ImaClient] IMA 未配置，跳过写入")
            return None

        if not title or not content:
            return None

        try:
            # 第一步：创建笔记
            resp = requests.post(
                f"{IMA_API_BASE}/note/v1/import_doc",
                headers=self._headers(),
                json={
                    "content_format": 1,  # MARKDOWN
                    "content": content,
                },
                timeout=IMPORT_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") not in (0, None):
                log.warning(f"[ImaClient] import_doc API 错误: {data.get('msg', data)}")
                return None

            note_id = data.get("data", {}).get("note_id", "")
            if not note_id:
                log.warning("[ImaClient] import_doc 未返回 note_id")
                return None

            # 第二步：将笔记添加到知识库
            add_payload: Dict[str, Any] = {
                "media_type": 11,  # 笔记
                "title": title,
                "knowledge_base_id": self.knowledge_base_id,
                "note_info": {"content_id": note_id},
            }
            if folder_id:
                add_payload["folder_id"] = folder_id

            resp = requests.post(
                f"{IMA_API_BASE}/wiki/v1/add_knowledge",
                headers=self._headers(),
                json=add_payload,
                timeout=IMPORT_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") not in (0, None):
                log.warning(f"[ImaClient] add_knowledge API 错误: {data.get('msg', data)}")
                return None

            media_id = data.get("data", {}).get("media_id", "")
            log.info(f"[ImaClient] 写入文档 '{title}' → note_id={note_id}, media_id={media_id}")
            return media_id or None

        except Exception as e:
            log.warning(f"[ImaClient] 写入文档失败 title='{title}': {e}")
            return None


# 单例便捷访问
_default_client: Optional[ImaClient] = None


def get_ima_client() -> ImaClient:
    """获取默认 IMA 客户端单例"""
    global _default_client
    if _default_client is None:
        _default_client = ImaClient()
    return _default_client
