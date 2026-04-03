"""
定时任务：获取经济数据并更新美林时钟

功能：
1. 定期获取经济数据（日频/周频）
2. 更新美林时钟周期判断
3. 存储历史数据供回测使用

建议执行频率：
- 日频：每天美股收盘后（凌晨 4-5 点）
- 周频：每周一早上（获取上周数据）
"""

import logging
import time
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


def execute() -> Dict[str, Any]:
    """
    定时任务执行函数
    
    Returns:
        执行结果字典
    """
    log.info("[EconomicDataTask] 开始获取经济数据并更新美林时钟...")
    
    try:
        # 1. 初始化数据获取器
        from deva.naja.cognition.economic_data_fetcher import EconomicDataFetcher
        
        # FRED API Key（https://fred.stlouisfed.org）
        fred_api_key = "f48d2328888b60cb2d188c148da31f63"
        fetcher = EconomicDataFetcher(fred_api_key=fred_api_key, use_mock=False)
        
        # 2. 获取经济数据
        import asyncio
        import nest_asyncio
        nest_asyncio.apply()
        
        async def _fetch():
            data = await fetcher.fetch_latest_data()
            await fetcher.close()
            return data
        
        data = asyncio.run(_fetch())
        
        log.info(f"[EconomicDataTask] 获取经济数据成功：{data.timestamp}")
        
        # 3. 更新美林时钟
        from deva.naja.cognition.merrill_clock_engine import get_merrill_clock_engine
        
        clock_engine = get_merrill_clock_engine()
        signal = clock_engine.on_economic_data(data)
        
        if signal:
            log.info(f"[EconomicDataTask] 周期阶段更新：{signal.phase.value}, 置信度：{signal.confidence:.0%}")
            
            result = {
                "success": True,
                "phase": signal.phase.value,
                "confidence": round(signal.confidence, 3),
                "growth_score": round(signal.growth_score, 3),
                "inflation_score": round(signal.inflation_score, 3),
                "asset_ranking": signal.asset_ranking,
                "reason": signal.reason[:100],  # 截断避免过长
            }
        else:
            log.warning("[EconomicDataTask] 数据不足，无法更新周期判断")
            result = {
                "success": False,
                "message": "数据不足",
            }
        
        # 4. 存储历史数据（可选）
        _store_historical_data(data, signal)
        
        return result
        
    except Exception as e:
        log.error(f"[EconomicDataTask] 执行失败：{e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": str(e),
        }


def _store_historical_data(data: Any, signal: Optional[Any]):
    """存储历史数据供回测使用"""
    try:
        from deva import NB
        
        db = NB("naja_economic_data_history")
        
        timestamp = data.timestamp
        key = f"{int(timestamp)}"
        
        db[key] = {
            "timestamp": timestamp,
            "economic_data": {
                "gdp_growth": data.gdp_growth,
                "pmi": data.pmi,
                "unemployment_rate": data.unemployment_rate,
                "nonfarm_payrolls": data.nonfarm_payrolls,
                "cpi_yoy": data.cpi_yoy,
                "core_cpi_yoy": data.core_cpi_yoy,
                "pce_yoy": data.pce_yoy,
                "core_pce_yoy": data.core_pce_yoy,
                "tips_breakeven": data.tips_breakeven,
                "yield_curve_spread": data.yield_curve_spread,
            },
            "clock_signal": signal.to_dict() if signal else None,
        }
        
        log.debug(f"[EconomicDataTask] 历史数据已存储：{key}")
        
    except Exception as e:
        log.error(f"[EconomicDataTask] 存储历史数据失败：{e}")


# ========== 手动测试 ==========

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("美林时钟定时任务测试")
    print("=" * 60)
    
    result = execute()
    
    print(f"\n执行结果：")
    for key, value in result.items():
        print(f"  {key}: {value}")
    
    print(f"\n" + "=" * 60)
