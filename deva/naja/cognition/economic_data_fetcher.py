"""
EconomicDataFetcher - 经济数据获取器

数据源：
1. FRED API（美联储经济数据）
2. 财经日历
3. 市场数据（通胀预期、利差等）

使用示例：
```python
fetcher = EconomicDataFetcher(fred_api_key="your_key")
data = await fetcher.fetch_latest_data()
clock_engine = get_merrill_clock_engine()
signal = clock_engine.on_economic_data(data)
```
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

from deva.naja.cognition.merrill_clock_engine import EconomicData

log = logging.getLogger(__name__)


@dataclass
class FREDData:
    """FRED API 数据结构"""
    series_id: str
    observations: List[Dict[str, str]]


class EconomicDataFetcher:
    """
    经济数据获取器
    
    支持数据源：
    1. FRED（美联储经济数据）- 需要 API Key
    2. 模拟数据（用于测试）
    """
    
    # FRED 系列 ID
    FRED_SERIES = {
        "gdp": "GDPC1",                  # 实际GDP（季度水平值，用于计算同比增速）
        "pmi": "MANEMP",                 # 制造业就业人数（千）
        "unemployment": "UNRATE",        # 失业率
        "nonfarm": "PAYEMS",             # 非农就业（千人）
        "cpi": "CPIAUCSL",               # CPI 水平值
        "core_cpi": "CPILFESL",          # 核心 CPI 水平值
        "pce": "PCEPILFE",               # 核心 PCE 水平值
        "tips_10y": "DFII10",            # 10 年 TIPS 实际收益率
        "treasury_10y": "DGS10",         # 10 年期国债收益率
        "treasury_2y": "DGS2",           # 2 年期国债收益率
    }
    
    def __init__(self, fred_api_key: Optional[str] = None, use_mock: bool = False):
        """
        初始化数据获取器
        
        Args:
            fred_api_key: FRED API Key（https://fred.stlouisfed.org/docs/api/api_key.html）
            use_mock: 是否使用模拟数据（测试用）
        """
        self._fred_api_key = fred_api_key
        self._use_mock = use_mock
        self._session = None
        
        if not fred_api_key and not use_mock:
            log.warning("[EconomicDataFetcher] 未提供 FRED API Key，将使用模拟数据")
            self._use_mock = True
    
    async def fetch_latest_data(self) -> EconomicData:
        """
        获取最新经济数据
        
        Returns:
            EconomicData: 经济数据包
        """
        if self._use_mock:
            return self._fetch_mock_data()
        
        return await self._fetch_fred_data()
    
    async def _fetch_fred_data(self) -> EconomicData:
        """从 FRED API 获取数据"""
        if not HAS_AIOHTTP:
            log.error("[EconomicDataFetcher] aiohttp 未安装，无法获取 FRED 数据")
            return self._fetch_mock_data()
        
        base_url = "https://api.stlouisfed.org/fred/series/observations"
        
        async with aiohttp.ClientSession() as session:
            self._session = session
            
            # 每个系列需要的观测数（用于计算同比）
            limits = {
                "gdp": 5,        # 季度数据，需当前+4季度前 → 计算同比
                "cpi": 13,       # 月度数据，需当前+12月前 → 计算同比
                "core_cpi": 13,
                "pce": 13,
            }
            
            # 并发获取所有系列数据
            async def fetch_with_limit(name, sid):
                limit = limits.get(name, 1)
                return await self._fetch_series(session, base_url, sid, limit=limit)
            
            tasks = {
                series_name: fetch_with_limit(series_name, series_id)
                for series_name, series_id in self.FRED_SERIES.items()
            }
            
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            data_dict = dict(zip(tasks.keys(), results))
            
            # 解析数据
            return self._parse_fred_data(data_dict)
    
    async def _fetch_series(self, session: aiohttp.ClientSession, 
                           base_url: str, series_id: str,
                           limit: int = 1) -> Optional[List[float]]:
        """获取单个系列数据（返回最新N条，降序排列）"""
        params = {
            "series_id": series_id,
            "api_key": self._fred_api_key,
            "file_type": "json",
            "limit": limit,
            "sort_order": "desc",
        }
        
        try:
            async with session.get(base_url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    observations = data.get("observations", [])
                    values = []
                    for obs in observations:
                        v = obs.get("value")
                        if v and v != ".":
                            values.append(float(v))
                    return values if values else None
        except Exception as e:
            log.error(f"[EconomicDataFetcher] 获取 {series_id} 失败：{e}")
        
        return None
    
    def _parse_fred_data(self, data_dict: Dict[str, Optional[List[float]]]) -> EconomicData:
        """解析 FRED 数据"""
        now = time.time()
        
        def _v(vals, idx, default=None):
            """安全取值，超界返回默认值"""
            try:
                v = vals[idx]
                return v if v is not None else default
            except (IndexError, TypeError):
                return default
        
        def _yoy(vals, current_idx, year_ago_idx):
            """计算同比增速（%）"""
            try:
                current = vals[current_idx]
                year_ago = vals[year_ago_idx]
                if current and year_ago and year_ago > 0:
                    return ((current / year_ago) - 1) * 100
            except (IndexError, TypeError, ZeroDivisionError):
                pass
            return None
        
        # ---- 增长类指标 ----
        
        gdp_vals = data_dict.get("gdp")
        gdp_growth = _yoy(gdp_vals, 0, 4)   # GDPC1: 季度同比需差4个季度
        
        pmi_vals = data_dict.get("pmi")
        pmi = _v(pmi_vals, 0)
        
        unemployment_vals = data_dict.get("unemployment")
        unemployment = _v(unemployment_vals, 0)
        
        nonfarm_vals = data_dict.get("nonfarm")
        nonfarm = _v(nonfarm_vals, 0)  # FRED PAYEMS 单位已是千人
        
        # ---- 通胀类指标（同比） ----
        
        cpi_vals = data_dict.get("cpi")
        cpi_yoy = _yoy(cpi_vals, 0, 12)   # 月度同比差12个月
        
        core_cpi_vals = data_dict.get("core_cpi")
        core_cpi_yoy = _yoy(core_cpi_vals, 0, 12)
        
        pce_vals = data_dict.get("pce")
        core_pce_yoy = _yoy(pce_vals, 0, 12)
        
        # ---- 金融条件 ----
        
        tips_10y_vals = data_dict.get("tips_10y")
        treasury_10y_vals = data_dict.get("treasury_10y")
        tips_breakeven = None
        t10 = _v(treasury_10y_vals, 0)
        tips10 = _v(tips_10y_vals, 0)
        if t10 is not None and tips10 is not None:
            tips_breakeven = t10 - tips10
        
        treasury_2y_vals = data_dict.get("treasury_2y")
        yield_curve_spread = None
        t2 = _v(treasury_2y_vals, 0)
        if t10 is not None and t2 is not None:
            yield_curve_spread = (t10 - t2) * 100  # bps
        
        return EconomicData(
            timestamp=now,
            gdp_growth=gdp_growth,
            pmi=pmi,
            unemployment_rate=unemployment,
            nonfarm_payrolls=nonfarm,
            cpi_yoy=cpi_yoy,
            core_cpi_yoy=core_cpi_yoy,
            pce_yoy=core_pce_yoy,
            core_pce_yoy=core_pce_yoy,
            tips_breakeven=tips_breakeven,
            yield_curve_spread=yield_curve_spread,
        )
    
    def _fetch_mock_data(self) -> EconomicData:
        """
        获取模拟数据（用于测试）
        
        模拟当前美国经济状态：温和增长 + 温和通胀（复苏/过热边缘）
        """
        import random
        
        now = time.time()
        
        # 模拟数据：温和增长
        gdp_growth = 2.5 + random.uniform(-0.5, 0.5)  # GDP 增速 2-3%
        pmi = 52.0 + random.uniform(-2, 2)            # PMI 50-54（扩张区间）
        unemployment = 3.8 + random.uniform(-0.2, 0.2)  # 失业率 3.6-4.0%
        nonfarm = 200 + random.uniform(-50, 50)       # 非农 150-250k
        
        # 模拟数据：温和通胀
        cpi = 3.0 + random.uniform(-0.5, 0.5)         # CPI 2.5-3.5%
        core_cpi = 3.5 + random.uniform(-0.3, 0.3)    # 核心 CPI 3.2-3.8%
        pce = 2.8 + random.uniform(-0.3, 0.3)         # PCE 2.5-3.1%
        core_pce = 3.0 + random.uniform(-0.2, 0.2)    # 核心 PCE 2.8-3.2%
        
        # 通胀预期
        tips_breakeven = 2.3 + random.uniform(-0.2, 0.2)
        
        # 收益率曲线（轻微倒挂）
        yield_curve_spread = -20 + random.uniform(-10, 10)
        
        return EconomicData(
            timestamp=now,
            gdp_growth=gdp_growth,
            pmi=pmi,
            unemployment_rate=unemployment,
            nonfarm_payrolls=nonfarm,
            cpi_yoy=cpi,
            core_cpi_yoy=core_cpi,
            pce_yoy=pce,
            core_pce_yoy=core_pce,
            tips_breakeven=tips_breakeven,
            yield_curve_spread=yield_curve_spread,
        )
    
    async def close(self):
        """关闭会话"""
        if self._session:
            await self._session.close()


# ========== 测试脚本 ==========

async def test_fetcher():
    """测试数据获取器"""
    print("=" * 60)
    print("经济数据获取器测试")
    print("=" * 60)
    
    # 使用模拟数据测试
    fetcher = EconomicDataFetcher(use_mock=True)
    
    try:
        data = await fetcher.fetch_latest_data()
        
        print(f"\n数据时间戳：{data.timestamp}")
        print(f"\n经济增长指标:")
        print(f"  GDP 增速：{data.gdp_growth:.1f}%" if data.gdp_growth else "  GDP: 无数据")
        print(f"  PMI: {data.pmi:.1f}" if data.pmi else "  PMI: 无数据")
        print(f"  失业率：{data.unemployment_rate:.1f}%" if data.unemployment_rate else "  失业率：无数据")
        print(f"  非农就业：{data.nonfarm_payrolls:.0f}k" if data.nonfarm_payrolls else "  非农：无数据")
        
        print(f"\n通胀指标:")
        print(f"  CPI: {data.cpi_yoy:.1f}%" if data.cpi_yoy else "  CPI: 无数据")
        print(f"  核心 CPI: {data.core_cpi_yoy:.1f}%" if data.core_cpi_yoy else "  核心 CPI: 无数据")
        print(f"  PCE: {data.pce_yoy:.1f}%" if data.pce_yoy else "  PCE: 无数据")
        print(f"  核心 PCE: {data.core_pce_yoy:.1f}%" if data.core_pce_yoy else "  核心 PCE: 无数据")
        
        print(f"\n市场预期:")
        print(f"  TIPS 盈亏平衡：{data.tips_breakeven:.2f}%" if data.tips_breakeven else "  TIPS: 无数据")
        print(f"  收益率曲线利差：{data.yield_curve_spread:.0f}bps" if data.yield_curve_spread else "  利差：无数据")
        
        # 测试美林时钟引擎
        print(f"\n" + "=" * 60)
        print("美林时钟引擎测试")
        print("=" * 60)
        
        from deva.naja.cognition.merrill_clock_engine import get_merrill_clock_engine
        
        clock_engine = get_merrill_clock_engine()
        signal = clock_engine.on_economic_data(data)
        
        if signal:
            print(f"\n周期阶段：{signal.phase.value}")
            print(f"置信度：{signal.confidence:.0%}")
            print(f"增长评分：{signal.growth_score:.2f}")
            print(f"通胀评分：{signal.inflation_score:.2f}")
            print(f"\n资产配置建议:")
            print(f"  排序：{' > '.join(signal.asset_ranking)}")
            print(f"  超配：{', '.join(signal.overweight)}")
            print(f"  低配：{', '.join(signal.underweight)}")
            print(f"\n判断理由：{signal.reason}")
        else:
            print("\n数据不足，无法判断周期阶段")
        
        print(f"\n" + "=" * 60)
        
    except Exception as e:
        print(f"测试失败：{e}")
        import traceback
        traceback.print_exc()
    finally:
        await fetcher.close()


if __name__ == "__main__":
    asyncio.run(test_fetcher())
