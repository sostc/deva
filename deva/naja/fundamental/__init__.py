"""基本面层：季频财报的落地仓 + 拉取服务。

与 :mod:`deva.naja.structural_growth` 的分工
------------------------------------------
``structural_growth`` 是**产业研究**（S0-S4 状态机、三 Agent 链），回答
「这个行业走到哪一步了」；本包是**个股裁决的数据底座**，回答「这只票的
财报数字是多少、有多旧」，供 T 轮动的抄底许可与仓位档位使用。

三条硬约束（沿用本项目的血泪）
------------------------------
* ``None ≠ 0``：拿不到就写 ``missing``，不写 0；
* 季频数据落库而非内存缓存：重启不丢，能看修订历史；
* 只存**原始数字**，不存结论 —— 打分是纯函数，随时可重算、可回测。
"""

from .service import FundamentalService, get_fundamental_service
from .store import FundamentalStore

__all__ = ["FundamentalService", "FundamentalStore", "get_fundamental_service"]
