"""FutuPortfolioSyncer - 富途持仓同步器

功能：
1. 从 Futu OpenD 获取真实持仓
2. 同步到 Bandit 持仓表 (naja_bandit_positions)
3. 支持定时同步

用法：
    syncer = FutuPortfolioSyncer()
    syncer.sync()

调度示例（每5分钟同步）：
    from deva import scheduler
    scheduler.every(300).seconds.do(lambda: FutuPortfolioSyncer().sync())
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from deva import NB
from deva.naja.register import SR

log = logging.getLogger(__name__)

UNIFIED_POSITIONS_TABLE = "naja_bandit_positions"
FUTU_ACCOUNTS_TABLE = "naja_bandit_futu_accounts"


class FutuPortfolioSyncer:
    """富途持仓同步器

    将富途账户的真实持仓同步到 Bandit 系统。

    默认使用 SIMULATE 模拟盘，如需同步真实持仓：
        syncer = FutuPortfolioSyncer(trd_env="REAL")
    """

    def __init__(
        self,
        account_name: str = "FutuSim",
        trd_env: str = "SIMULATE",
        market: str = "US",
        security_firm: str = "FUTUSECURITIES",
    ):
        self.account_name = account_name
        self.trd_env = trd_env
        self.market = market
        self.security_firm = security_firm
        self._ctx = None

    def _ensure_futu_api(self):
        """确保 futu-api 已安装"""
        try:
            import futu
            return True
        except ImportError:
            log.error("futu-api 未安装，请运行: pip install futu-api")
            return False

    def _create_trade_context(self):
        """创建交易上下文"""
        if not self._ensure_futu_api():
            return None

        try:
            from futu import OpenSecTradeContext
            from futu import SecurityFirm

            host = "127.0.0.1"
            port = 11111

            firm = getattr(SecurityFirm, self.security_firm, SecurityFirm.FUTUSECURITIES)

            ctx = OpenSecTradeContext(
                host=host,
                port=port,
                security_firm=firm,
            )
            return ctx
        except Exception as e:
            log.error(f"创建交易上下文失败: {e}")
            return None

    def _close_context(self):
        """关闭上下文"""
        if self._ctx:
            try:
                self._ctx.close()
            except Exception:
                pass
            self._ctx = None

    def _get_futu_trd_env(self):
        """获取 Futu 交易环境枚举"""
        try:
            from futu import TrdEnv
            return TrdEnv.SIMULATE if self.trd_env == "SIMULATE" else TrdEnv.REAL
        except Exception:
            return 0

    def get_accounts(self) -> List[Dict[str, Any]]:
        """获取富途账户列表"""
        if not self._ensure_futu_api():
            return []

        accounts = []
        try:
            from futu import OpenSecTradeContext, SecurityFirm

            for firm_name in ["FUTUSECURITIES", "FUTUINC", "FUTUSG", "FUTUAU", "FUTUCA", "FUTUJP", "FUTUMY"]:
                try:
                    firm = getattr(SecurityFirm, firm_name)
                    ctx = OpenSecTradeContext(host="127.0.0.1", port=11111, security_firm=firm)
                    ret, data = ctx.get_acc_list()
                    ctx.close()

                    if ret == 0 and data is not None and len(data) > 0:
                        for i in range(len(data)):
                            row = data.iloc[i]
                            accounts.append({
                                "acc_id": int(row.get("acc_id", 0)),
                                "acc_type": str(row.get("acc_type", "")),
                                "trd_env": str(row.get("trd_env", "")),
                                "security_firm": firm_name,
                            })
                except Exception as e:
                    log.debug(f"{firm_name} 获取失败: {e}")
        except Exception as e:
            log.error(f"获取账户列表失败: {e}")

        log.info(f"[FutuSyncer] 发现 {len(accounts)} 个富途账户")
        return accounts

    def get_portfolio(self, acc_id: Optional[int] = None) -> Dict[str, Any]:
        """获取富途持仓

        Returns:
            {
                "funds": {...},  # 账户资金
                "positions": [...]  # 持仓列表
            }
        """
        for attempt in range(3):
            self._ctx = self._create_trade_context()
            if not self._ctx:
                log.warning(f"[FutuSyncer] 创建交易上下文失败，重试 {attempt + 1}/3")
                time.sleep(1)
                continue

            try:
                time.sleep(1.0)
                trd_env = self.trd_env

                # 获取正确的 acc_id
                if acc_id is None:
                    ret, acc_list = self._ctx.get_acc_list()
                    if ret == 0 and acc_list is not None and len(acc_list) > 0:
                        for i in range(len(acc_list)):
                            row = acc_list.iloc[i]
                            if str(row.get("trd_env", "")).upper() == trd_env.upper():
                                acc_id = row.get("acc_id")
                                log.info(f"[FutuSyncer] 使用账户 acc_id={acc_id}, trd_env={trd_env}")
                                break
                    if acc_id is None:
                        log.warning(f"[FutuSyncer] 未找到 {trd_env} 环境的账户")

                ret, acc_data = self._ctx.accinfo_query(trd_env=trd_env, acc_id=acc_id)
                funds = {}
                if ret == 0 and acc_data is not None and len(acc_data) > 0:
                    row = acc_data.iloc[0]
                    funds = {
                        "total_assets": float(row.get("total_assets", 0) or 0),
                        "cash": float(row.get("cash", 0) or 0),
                        "market_val": float(row.get("market_val", 0) or 0),
                        "power": float(row.get("power", 0) or 0),
                        "currency": str(row.get("currency", "USD")),
                    }

                time.sleep(0.3)

                ret, pos_data = self._ctx.position_list_query(trd_env=trd_env, acc_id=acc_id)
                positions = []
                if ret == 0 and pos_data is not None and len(pos_data) > 0:
                    for i in range(len(pos_data)):
                        row = pos_data.iloc[i]
                        positions.append({
                            "code": str(row.get("code", "")),
                            "name": str(row.get("stock_name", "")),
                            "qty": float(row.get("qty", 0) or 0),
                            "average_cost": float(row.get("average_cost", 0) or 0),
                            "nominal_price": float(row.get("nominal_price", 0) or 0),
                            "market_val": float(row.get("market_val", 0) or 0),
                            "unrealized_pl": float(row.get("unrealized_pl", 0) or 0),
                            "pl_ratio": float(row.get("pl_ratio_avg_cost", 0) or 0),
                        })

                log.info(f"[FutuSyncer] 获取持仓成功: {len(positions)} 个持仓")
                return {"funds": funds, "positions": positions}

            except Exception as e:
                log.warning(f"[FutuSyncer] 获取持仓失败 (尝试 {attempt + 1}/3): {e}")
            finally:
                self._close_context()

        log.error(f"[FutuSyncer] 获取持仓失败，已重试3次")
        return {"funds": {}, "positions": []}

    def sync(self, acc_id: Optional[int] = None) -> bool:
        """同步富途持仓到 Bandit 系统

        Args:
            acc_id: 账户 ID，不指定则使用默认

        Returns:
            是否同步成功
        """
        log.info(f"[FutuSyncer] 开始同步持仓 from {self.account_name}...")

        portfolio_data = self.get_portfolio(acc_id)
        if not portfolio_data.get("positions") and not portfolio_data.get("funds"):
            log.warning(f"[FutuSyncer] 未获取到持仓数据")
            return False

        self._sync_to_bandit(portfolio_data)
        self._save_futu_accounts(portfolio_data)

        log.info(f"[FutuSyncer] 同步完成: {len(portfolio_data['positions'])} 个持仓")
        return True

    def _sync_to_bandit(self, portfolio_data: Dict[str, Any]):
        """同步到 Bandit 持仓表"""
        nb = NB(UNIFIED_POSITIONS_TABLE)

        accounts_data = nb.get("accounts", {})
        if self.account_name not in accounts_data:
            accounts_data[self.account_name] = {
                "account_type": "futu",
                "equity": portfolio_data["funds"].get("total_assets", 0),
            }

        positions_dict = {}
        for pos in portfolio_data.get("positions", []):
            code = pos.get("code", "")
            if not code:
                continue

            position_id = f"US_{self.account_name}_{code}"

            from .portfolio_manager import USStockPosition

            position = USStockPosition(
                position_id=position_id,
                account_name=self.account_name,
                stock_code=code,
                stock_name=pos.get("name", code),
                entry_price=pos.get("average_cost", 0),
                current_price=pos.get("nominal_price", 0),
                quantity=pos.get("qty", 0),
                entry_time=time.time(),
                last_update_time=time.time(),
                status="OPEN",
                prev_close=pos.get("prev_close", 0),
            )

            positions_dict[position_id] = {
                "position_id": position.position_id,
                "account_name": position.account_name,
                "stock_code": position.stock_code,
                "stock_name": position.stock_name,
                "entry_price": position.entry_price,
                "current_price": position.current_price,
                "quantity": position.quantity,
                "entry_time": position.entry_time,
                "last_update_time": position.last_update_time,
                "status": position.status,
                "prev_close": position.prev_close,
            }

        accounts_data[self.account_name]["positions"] = positions_dict
        accounts_data[self.account_name]["equity"] = portfolio_data["funds"].get("total_assets", 0)
        nb["accounts"] = accounts_data

        try:
            pm = SR("portfolio_manager")
            if pm:
                account = pm.register_futu_account(self.account_name)
                if account:
                    account._positions = {}
                    for pos_id, pos_data in positions_dict.items():
                        from .portfolio_manager import USStockPosition
                        account._positions[pos_id] = USStockPosition(**pos_data)
                    account._equity = portfolio_data["funds"].get("total_assets", 0)
                    log.debug(f"[FutuSyncer] 更新 PortfolioManager 缓存")
        except Exception as e:
            log.debug(f"[FutuSyncer] 更新缓存跳过: {e}")

    def _save_futu_accounts(self, portfolio_data: Dict[str, Any]):
        """保存富途账户信息"""
        nb = NB(FUTU_ACCOUNTS_TABLE)
        nb["last_sync_time"] = time.time()
        nb["last_account_name"] = self.account_name
        nb["funds"] = portfolio_data.get("funds", {})


_singleton: Optional[FutuPortfolioSyncer] = None


def get_futu_syncer() -> FutuPortfolioSyncer:
    """获取 FutuPortfolioSyncer 单例"""
    global _singleton
    if _singleton is None:
        _singleton = FutuPortfolioSyncer()
    return _singleton


if __name__ == "__main__":
    syncer = FutuPortfolioSyncer()

    accounts = syncer.get_accounts()
    print(f"发现 {len(accounts)} 个富途账户:")
    for acc in accounts:
        print(f"  - {acc}")

    print("\n同步持仓...")
    if syncer.sync():
        portfolio = syncer.get_portfolio()
        print(f"\n账户资金: {portfolio['funds']}")
        print(f"持仓数量: {len(portfolio['positions'])}")
        for pos in portfolio['positions']:
            print(f"  {pos['code']} {pos['name']}: {pos['qty']}股 @ ${pos['average_cost']:.2f}")
