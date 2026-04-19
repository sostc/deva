"""
OpenRouter 监控 - 数据获取器

负责从 OpenRouter 网站获取 TOKEN 消耗数据
"""

import asyncio
import re
import httpx
from typing import Optional, Dict, List, TypedDict


class WeeklyDataPoint(TypedDict):
    """单周数据点"""
    date: str  # ISO 日期格式 "YYYY-MM-DD"
    models: dict[str, int]  # model_id -> token_count


class OpenRouterDataFetcher:
    """OpenRouter 数据获取器"""

    BASE_URL = "https://openrouter.ai"
    RANKINGS_URL = f"{BASE_URL}/rankings"

    async def get_weekly_token_usage(self) -> list[WeeklyDataPoint]:
        """
        获取每周 Token 使用量时间序列数据

        Returns:
            list[WeeklyDataPoint]: 每周数据列表，按日期升序排列
        """
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                }
            ) as client:
                response = await client.get(self.RANKINGS_URL)
                response.raise_for_status()

                return self._parse_weekly_data(response.text)
        except Exception as e:
            print(f"[OpenRouter DataFetcher] 数据获取失败: {e}")
            return []

    def _parse_weekly_data(self, html_content: str) -> list[WeeklyDataPoint]:
        """
        解析 HTML 中的 RSC payload，提取每周 token 使用量数据
        """
        result = []
        pattern = r'\\"x\\":\\"(\d{4}-\d{2}-\d{2})\\",\\"ys\\":\{([^}]+)\}'
        matches = re.findall(pattern, html_content)

        for date_str, models_data in matches:
            models: dict[str, int] = {}
            model_pattern = r'\\"([^\\"]+)\\":\s*(\d+)'
            model_matches = re.findall(model_pattern, models_data)

            for model_id, token_count in model_matches:
                models[model_id] = int(token_count)

            if models:
                result.append(WeeklyDataPoint(date=date_str, models=models))

        return result

    async def fetch_weekly_data(self) -> Optional[List[Dict]]:
        """获取 OpenRouter 每周 TOKEN 数据"""
        try:
            weekly_data = await self.get_weekly_token_usage()

            if not weekly_data:
                return None

            return [
                {
                    "date": w["date"],
                    "total": sum(w["models"].values()),
                    "models": w["models"]
                }
                for w in weekly_data
            ]

        except Exception as e:
            print(f"[OpenRouter DataFetcher] 数据获取失败: {e}")
            return None
