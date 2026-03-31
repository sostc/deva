"""
SupplyChainKnowledgeGraph - 产业链知识图谱系统

提供：
1. 公司 → 技术 → 产品 → 材料 的完整产业链关系
2. 上下游依赖关系查询
3. 供应链瓶颈分析
4. 基于产业链的选股推荐
"""

from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum


class NodeType(Enum):
    """知识图谱节点类型"""
    COMPANY = "company"           # 公司/上市公司
    PRODUCT = "product"           # 产品
    TECHNOLOGY = "technology"     # 技术
    MATERIAL = "material"         # 原材料/材料
    COMPONENT = "component"       # 组件/零部件
    EQUIPMENT = "equipment"       # 设备/机械
    INFRASTRUCTURE = "infrastructure"  # 基础设施


class RelationType(Enum):
    """知识图谱关系类型"""
    PRODUCES = "produces"         # 生产/制造
    USES = "uses"                 # 使用/依赖
    COMPETES_WITH = "competes_with"  # 竞争
    SUPPLIES_TO = "supplies_to"   # 供应给
    BUYS_FROM = "buys_from"       # 从...购买
    DEVELOPS = "develops"         # 研发/开发
    OWNS = "owns"                 # 拥有/持有


@dataclass
class GraphNode:
    """知识图谱节点"""
    id: str
    name: str
    type: NodeType
    metadata: Dict = field(default_factory=dict)

    # 公司特有的属性
    stock_code: Optional[str] = None      # 股票代码
    sector: Optional[str] = None          # 行业板块
    market_cap: Optional[str] = None      # 市值规模

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "metadata": self.metadata,
            "stock_code": self.stock_code,
            "sector": self.sector,
            "market_cap": self.market_cap,
        }


@dataclass
class GraphEdge:
    """知识图谱边/关系"""
    from_id: str
    to_id: str
    type: RelationType
    weight: float = 1.0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "from": self.from_id,
            "to": self.to_id,
            "type": self.type.value,
            "weight": self.weight,
            "metadata": self.metadata,
        }


@dataclass
class SupplyChainAnalysis:
    """供应链分析结果"""
    central_company: str
    upstream_companies: List[str]
    downstream_companies: List[str]
    bottleneck_nodes: List[str]
    competitive_landscape: List[str]


@dataclass
class SupplyChainRisk:
    """供应链风险"""
    node_id: str
    node_name: str
    risk_type: str
    risk_level: str
    description: str
    mitigation_suggestion: str


@dataclass
class SupplyChainRiskReport:
    """供应链风险报告"""
    company: str
    overall_risk_level: str
    upstream_risks: List[SupplyChainRisk]
    downstream_risks: List[SupplyChainRisk]
    concentration_risks: List[SupplyChainRisk]
    bottleneck_risks: List[SupplyChainRisk]
    recommendations: List[str]


class SupplyChainKnowledgeGraph:
    """
    产业链知识图谱

    核心功能：
    1. 构建完整的产业链知识图谱
    2. 查询公司的上下游关系
    3. 分析供应链瓶颈
    4. 基于产业链的选股推荐
    """

    def __init__(self):
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: List[GraphEdge] = []
        self._outgoing_edges: Dict[str, List[GraphEdge]] = {}
        self._incoming_edges: Dict[str, List[GraphEdge]] = {}

        self._init_ai_chip_supply_chain()

    def add_node(self, node: GraphNode):
        """添加节点"""
        self._nodes[node.id] = node
        if node.id not in self._outgoing_edges:
            self._outgoing_edges[node.id] = []
        if node.id not in self._incoming_edges:
            self._incoming_edges[node.id] = []

    def add_edge(self, edge: GraphEdge):
        """添加边"""
        self._edges.append(edge)
        self._outgoing_edges[edge.from_id].append(edge)
        self._incoming_edges[edge.to_id].append(edge)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """获取节点"""
        return self._nodes.get(node_id)

    def get_stock_node(self, stock_code: str) -> Optional[GraphNode]:
        """通过股票代码获取公司节点"""
        stock_code_lower = stock_code.lower()
        for node in self._nodes.values():
            if node.stock_code and node.stock_code.lower() == stock_code_lower:
                return node
        return None

    def get_upstream(self, node_id: str, max_depth: int = 3) -> List[GraphNode]:
        """
        获取上游节点（供应商、依赖）

        Args:
            node_id: 起始节点ID
            max_depth: 最大深度

        Returns:
            上游节点列表
        """
        visited = set()
        result = []

        def dfs(current_id: str, depth: int):
            if depth > max_depth or current_id in visited:
                return
            visited.add(current_id)

            for edge in self._incoming_edges.get(current_id, []):
                if edge.type in [RelationType.SUPPLIES_TO, RelationType.PRODUCES]:
                    upstream_node = self.get_node(edge.from_id)
                    if upstream_node:
                        result.append(upstream_node)
                        dfs(edge.from_id, depth + 1)

        dfs(node_id, 0)
        seen = set()
        unique_result = []
        for item in result:
            if item.id not in seen:
                seen.add(item.id)
                unique_result.append(item)
        return unique_result

    def get_downstream(self, node_id: str, max_depth: int = 3) -> List[GraphNode]:
        """
        获取下游节点（客户、应用）

        Args:
            node_id: 起始节点ID
            max_depth: 最大深度

        Returns:
            下游节点列表
        """
        visited = set()
        result = []

        def dfs(current_id: str, depth: int):
            if depth > max_depth or current_id in visited:
                return
            visited.add(current_id)

            for edge in self._outgoing_edges.get(current_id, []):
                if edge.type in [RelationType.SUPPLIES_TO, RelationType.USES]:
                    downstream_node = self.get_node(edge.to_id)
                    if downstream_node:
                        result.append(downstream_node)
                        dfs(edge.to_id, depth + 1)

        dfs(node_id, 0)
        seen = set()
        unique_result = []
        for item in result:
            if item.id not in seen:
                seen.add(item.id)
                unique_result.append(item)
        return unique_result

    def get_competitors(self, node_id: str) -> List[GraphNode]:
        """获取竞争对手"""
        competitors = []
        for edge in self._outgoing_edges.get(node_id, []):
            if edge.type == RelationType.COMPETES_WITH:
                competitor = self.get_node(edge.to_id)
                if competitor:
                    competitors.append(competitor)
        for edge in self._incoming_edges.get(node_id, []):
            if edge.type == RelationType.COMPETES_WITH:
                competitor = self.get_node(edge.from_id)
                if competitor:
                    competitors.append(competitor)
        seen = set()
        unique_result = []
        for item in competitors:
            if item.id not in seen:
                seen.add(item.id)
                unique_result.append(item)
        return unique_result

    def get_upstream_companies(self, stock_code: str) -> List[GraphNode]:
        """获取某只股票的上游公司（供应商）"""
        node = self.get_stock_node(stock_code)
        if not node:
            return []

        upstream = self.get_upstream(node.id)
        return [n for n in upstream if n.type == NodeType.COMPANY and n.stock_code]

    def get_downstream_companies(self, stock_code: str) -> List[GraphNode]:
        """获取某只股票的下游公司（客户）"""
        node = self.get_stock_node(stock_code)
        if not node:
            return []

        downstream = self.get_downstream(node.id)
        return [n for n in downstream if n.type == NodeType.COMPANY and n.stock_code]

    def analyze_supply_chain(self, stock_code: str) -> Optional[SupplyChainAnalysis]:
        """
        分析某只股票的供应链

        Args:
            stock_code: 股票代码

        Returns:
            供应链分析结果
        """
        node = self.get_stock_node(stock_code)
        if not node:
            return None

        upstream_companies = self.get_upstream_companies(stock_code)
        downstream_companies = self.get_downstream_companies(stock_code)
        competitors = self.get_competitors(node.id)

        return SupplyChainAnalysis(
            central_company=stock_code,
            upstream_companies=[c.stock_code for c in upstream_companies if c.stock_code],
            downstream_companies=[c.stock_code for c in downstream_companies if c.stock_code],
            bottleneck_nodes=[],
            competitive_landscape=[c.stock_code for c in competitors if c.stock_code],
        )

    def analyze_supply_chain_risk(self, stock_code: str) -> Optional[SupplyChainRiskReport]:
        """
        分析某只股票的供应链风险

        Args:
            stock_code: 股票代码

        Returns:
            供应链风险报告
        """
        node = self.get_stock_node(stock_code)
        if not node:
            return None

        upstream_risks = []
        downstream_risks = []
        concentration_risks = []
        bottleneck_risks = []
        recommendations = []

        upstream = self.get_upstream(node.id, max_depth=2)
        downstream = self.get_downstream(node.id, max_depth=2)

        single_source_upstream = {}
        for up_node in upstream:
            if up_node.type == NodeType.COMPANY:
                suppliers = [n for n in upstream if n.type == NodeType.COMPANY]
                if len(suppliers) == 1:
                    single_source_upstream[up_node.id] = up_node
                    risk = SupplyChainRisk(
                        node_id=up_node.id,
                        node_name=up_node.name,
                        risk_type="单一供应商依赖",
                        risk_level="HIGH",
                        description=f"该供应商是唯一的 [{up_node.name}]，存在单点故障风险",
                        mitigation_suggestion=f"建议寻找替代供应商，分散采购风险"
                    )
                    upstream_risks.append(risk)

        bottleneck_nodes_in_chain = [
            n for n in upstream + downstream
            if n.type in [NodeType.EQUIPMENT, NodeType.TECHNOLOGY]
            and any(e.type == RelationType.SUPPLIES_TO for e in self._outgoing_edges.get(n.id, []))
        ]
        for bn in bottleneck_nodes_in_chain:
            risk = SupplyChainRisk(
                node_id=bn.id,
                node_name=bn.name,
                risk_type="供应链瓶颈",
                risk_level="MEDIUM",
                description=f"[{bn.name}] 是关键瓶颈节点，供应中断将影响整个链条",
                mitigation_suggestion="建议备货或寻找替代技术路线"
            )
            bottleneck_risks.append(risk)

        if len(upstream) == 1:
            concentration_risk = SupplyChainRisk(
                node_id="concentration",
                node_name="供应商集中度",
                risk_type="供应商集中度过高",
                risk_level="MEDIUM",
                description="该公司的供应商非常集中，抗风险能力弱",
                mitigation_suggestion="建议拓展供应商网络"
            )
            concentration_risks.append(concentration_risk)

        if not downstream or len(downstream) == 0:
            downstream_risk = SupplyChainRisk(
                node_id="downstream",
                node_name="下游客户",
                risk_type="下游客户缺失",
                risk_level="LOW",
                description="该公司在知识图谱中暂无明确的下游客户关系",
                mitigation_suggestion="建议补充下游客户数据"
            )
            downstream_risks.append(downstream_risk)

        if node.metadata.get("market") == "A":
            if node.sector in ["ai_chip", "semiconductor"]:
                recommendation = "A 股 AI 芯片公司依赖海外先进制程风险较高，建议关注国产替代进程"
                recommendations.append(recommendation)

            if node.id in ["688981", "688041"]:
                recommendation = "中芯国际/寒武纪 受美国出口管制影响，供应链不确定性较高"
                recommendations.append(recommendation)

        if node.sector == "semiconductor":
            recommendation = "半导体行业周期性较强，建议关注库存周期和产能利用率"
            recommendations.append(recommendation)

        risk_level = "HIGH" if len(upstream_risks) > 2 else "MEDIUM" if upstream_risks else "LOW"

        return SupplyChainRiskReport(
            company=stock_code,
            overall_risk_level=risk_level,
            upstream_risks=upstream_risks,
            downstream_risks=downstream_risks,
            concentration_risks=concentration_risks,
            bottleneck_risks=bottleneck_risks,
            recommendations=recommendations,
        )

    def get_bottleneck_nodes(self, stock_code: str) -> List[GraphNode]:
        """
        识别供应链中的瓶颈节点

        Args:
            stock_code: 股票代码

        Returns:
            瓶颈节点列表
        """
        node = self.get_stock_node(stock_code)
        if not node:
            return []

        bottleneck = []
        upstream = self.get_upstream(node.id, max_depth=3)

        for up_node in upstream:
            outgoing = self._outgoing_edges.get(up_node.id, [])
            incoming = self._incoming_edges.get(up_node.id, [])

            if len(outgoing) > 3 or len(incoming) > 3:
                if up_node.type in [NodeType.EQUIPMENT, NodeType.TECHNOLOGY, NodeType.COMPONENT]:
                    bottleneck.append(up_node)

        return bottleneck

    def get_recommended_stocks(self, theme: str, market: Optional[str] = None) -> List[str]:
        """
        根据主题获取推荐股票

        Args:
            theme: 主题（如 "ai_chip", "gpu", "semiconductor", "china_chip"）
            market: 市场筛选 ("US", "A", None表示全部)

        Returns:
            推荐股票代码列表
        """
        theme_map = {
            "ai_chip": ["nvda", "amd", "688041", "300474"],
            "ai_chip_us": ["nvda", "amd", "intc", "tsm", "asml"],
            "ai_chip_china": ["688041", "300474", "688008", "603986"],
            "gpu": ["nvda", "amd", "300474"],
            "semiconductor": ["nvda", "amd", "intc", "tsm", "asml", "mu", "688981", "002371"],
            "semiconductor_china": ["688981", "002371", "688012", "002185", "600584"],
            "memory": ["mu", "skx", "688008", "603986"],
            "ai_infrastructure": ["smci", "msft", "googl", "amzn", "688111", "002230"],
            "chip_design": ["nvda", "amd", "688041", "300474", "688008", "603986", "002049"],
            "chip_manufacturing": ["tsm", "688981"],
            "chip_equipment": ["asml", "002371", "688012"],
            "chip_packaging": ["002185", "600584", "002156"],
            "hbm": ["mu", "skx"],
            "euv": ["asml", "002371"],
            "npu": ["688041"],
        }

        result = theme_map.get(theme, [])

        if market:
            filtered = []
            for code in result:
                node = self.get_stock_node(code)
                if node and node.metadata.get("market") == market:
                    filtered.append(code)
            return filtered

        return result

    def get_stocks_by_sector(self, sector: str, market: Optional[str] = None) -> List[GraphNode]:
        """
        获取特定行业的所有股票

        Args:
            sector: 行业（如 "ai_chip", "semiconductor"）
            market: 市场筛选 ("US", "A")

        Returns:
            公司节点列表
        """
        result = []
        for node in self._nodes.values():
            if node.type == NodeType.COMPANY and node.sector == sector:
                if market is None or node.metadata.get("market") == market:
                    result.append(node)
        return result

    def get_all_a_share_stocks(self) -> List[GraphNode]:
        """获取所有 A 股上市公司"""
        return [
            node for node in self._nodes.values()
            if node.type == NodeType.COMPANY and node.metadata.get("market") == "A"
        ]

    def get_all_us_stocks(self) -> List[GraphNode]:
        """获取所有美股上市公司"""
        return [
            node for node in self._nodes.values()
            if node.type == NodeType.COMPANY and node.metadata.get("market") == "US"
        ]

    def _init_ai_chip_supply_chain(self):
        """初始化 AI/芯片 产业链知识图谱（美股 + A 股）"""

        # ========== 美股公司节点 ==========

        us_companies = [
            GraphNode(
                id="nvda", name="英伟达", type=NodeType.COMPANY,
                stock_code="nvda", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "AI芯片设计领导者", "market": "US"}
            ),
            GraphNode(
                id="amd", name="超威半导体", type=NodeType.COMPANY,
                stock_code="amd", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "CPU/GPU 设计", "market": "US"}
            ),
            GraphNode(
                id="intc", name="英特尔", type=NodeType.COMPANY,
                stock_code="intc", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "CPU设计与制造", "market": "US"}
            ),
            GraphNode(
                id="tsm", name="台积电", type=NodeType.COMPANY,
                stock_code="tsm", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "晶圆代工", "market": "US"}
            ),
            GraphNode(
                id="asml", name="ASML", type=NodeType.COMPANY,
                stock_code="asml", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "EUV光刻机", "market": "US"}
            ),
            GraphNode(
                id="mu", name="美光科技", type=NodeType.COMPANY,
                stock_code="mu", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "HBM3e内存", "market": "US"}
            ),
            GraphNode(
                id="smci", name="超微电脑", type=NodeType.COMPANY,
                stock_code="smci", sector="ai_infrastructure", market_cap="large_cap",
                metadata={"description": "AI服务器", "market": "US"}
            ),
            GraphNode(
                id="msft", name="微软", type=NodeType.COMPANY,
                stock_code="msft", sector="cloud_computing", market_cap="large_cap",
                metadata={"description": "云服务/AI", "market": "US"}
            ),
            GraphNode(
                id="googl", name="谷歌", type=NodeType.COMPANY,
                stock_code="googl", sector="cloud_computing", market_cap="large_cap",
                metadata={"description": "云服务/AI", "market": "US"}
            ),
            GraphNode(
                id="amzn", name="亚马逊", type=NodeType.COMPANY,
                stock_code="amzn", sector="cloud_computing", market_cap="large_cap",
                metadata={"description": "云服务/AWS", "market": "US"}
            ),
            GraphNode(
                id="crwv", name="CoreWeave", type=NodeType.COMPANY,
                stock_code="crwv", sector="cloud_computing", market_cap="mid_cap",
                metadata={"description": "GPU云算力", "market": "US"}
            ),
            GraphNode(
                id="lumentum", name="Lumentum", type=NodeType.COMPANY,
                stock_code="lumentum", sector="semiconductor", market_cap="mid_cap",
                metadata={"description": "光通信元器件", "market": "US"}
            ),
            GraphNode(
                id="cgnx", name="Cognex", type=NodeType.COMPANY,
                stock_code="cgnx", sector="semiconductor", market_cap="mid_cap",
                metadata={"description": "机器视觉/AEC", "market": "US"}
            ),
            GraphNode(
                id="skx", name="SK海力士", type=NodeType.COMPANY,
                stock_code="skx", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "HBM4内存", "market": "US"}
            ),
        ]

        for company in us_companies:
            self.add_node(company)

        # ========== A 股公司节点 ==========

        a_share_companies = [
            GraphNode(
                id="688041", name="寒武纪", type=NodeType.COMPANY,
                stock_code="688041", sector="ai_chip", market_cap="mid_cap",
                metadata={"description": "AI芯片设计（ASIC/GPU/NPU）", "market": "A"}
            ),
            GraphNode(
                id="002371", name="北方华创", type=NodeType.COMPANY,
                stock_code="002371", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "半导体设备（刻蚀/沉积/清洗）", "market": "A"}
            ),
            GraphNode(
                id="688012", name="中微公司", type=NodeType.COMPANY,
                stock_code="688012", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "刻蚀设备/MOCVD", "market": "A"}
            ),
            GraphNode(
                id="688981", name="中芯国际", type=NodeType.COMPANY,
                stock_code="688981", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "晶圆代工", "market": "A"}
            ),
            GraphNode(
                id="002185", name="华天科技", type=NodeType.COMPANY,
                stock_code="002185", sector="semiconductor", market_cap="mid_cap",
                metadata={"description": "封装测试", "market": "A"}
            ),
            GraphNode(
                id="600584", name="长电科技", type=NodeType.COMPANY,
                stock_code="600584", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "封装测试", "market": "A"}
            ),
            GraphNode(
                id="688396", name="华润微", type=NodeType.COMPANY,
                stock_code="688396", sector="semiconductor", market_cap="mid_cap",
                metadata={"description": "功率半导体", "market": "A"}
            ),
            GraphNode(
                id="688256", name="寒武纪(关联)", type=NodeType.COMPANY,
                stock_code="688256", sector="ai_chip", market_cap="mid_cap",
                metadata={"description": "AI芯片", "market": "A"}
            ),
            GraphNode(
                id="300782", name="卓胜微", type=NodeType.COMPANY,
                stock_code="300782", sector="semiconductor", market_cap="mid_cap",
                metadata={"description": "射频芯片", "market": "A"}
            ),
            GraphNode(
                id="688008", name="澜起科技", type=NodeType.COMPANY,
                stock_code="688008", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "内存接口芯片/服务器芯片", "market": "A"}
            ),
            GraphNode(
                id="688099", name="晶晨股份", type=NodeType.COMPANY,
                stock_code="688099", sector="semiconductor", market_cap="mid_cap",
                metadata={"description": "多媒体芯片", "market": "A"}
            ),
            GraphNode(
                id="603986", name="兆易创新", type=NodeType.COMPANY,
                stock_code="603986", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "存储芯片/MCU", "market": "A"}
            ),
            GraphNode(
                id="002049", name="紫光国微", type=NodeType.COMPANY,
                stock_code="002049", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "安全芯片/FPGA", "market": "A"}
            ),
            GraphNode(
                id="300223", name="北京君正", type=NodeType.COMPANY,
                stock_code="300223", sector="semiconductor", market_cap="mid_cap",
                metadata={"description": "嵌入式处理器芯片", "market": "A"}
            ),
            GraphNode(
                id="688220", name="翱捷科技", type=NodeType.COMPANY,
                stock_code="688220", sector="semiconductor", market_cap="mid_cap",
                metadata={"description": "基带芯片/手机芯片", "market": "A"}
            ),
            GraphNode(
                id="301367", name="怡安比分", type=NodeType.COMPANY,
                stock_code="301367", sector="ai_infrastructure", market_cap="small_cap",
                metadata={"description": "AI服务器/算力", "market": "A"}
            ),
            GraphNode(
                id="300474", name="景嘉微", type=NodeType.COMPANY,
                stock_code="300474", sector="ai_chip", market_cap="mid_cap",
                metadata={"description": "GPU/图形处理器", "market": "A"}
            ),
            GraphNode(
                id="002156", name="通富微电", type=NodeType.COMPANY,
                stock_code="002156", sector="semiconductor", market_cap="mid_cap",
                metadata={"description": "封装测试", "market": "A"}
            ),
            GraphNode(
                id="600745", name="闻泰科技", type=NodeType.COMPANY,
                stock_code="600745", sector="semiconductor", market_cap="large_cap",
                metadata={"description": "半导体业务/安世半导体", "market": "A"}
            ),
            GraphNode(
                id="002230", name="科大讯飞", type=NodeType.COMPANY,
                stock_code="002230", sector="ai_software", market_cap="large_cap",
                metadata={"description": "AI语音/大模型", "market": "A"}
            ),
            GraphNode(
                id="300124", name="汇川技术", type=NodeType.COMPANY,
                stock_code="300124", sector="ai_infrastructure", market_cap="large_cap",
                metadata={"description": "工业自动化/伺服系统", "market": "A"}
            ),
            GraphNode(
                id="688111", name="金山办公", type=NodeType.COMPANY,
                stock_code="688111", sector="ai_software", market_cap="large_cap",
                metadata={"description": "办公软件/AI", "market": "A"}
            ),
            GraphNode(
                id="002405", name="四维图新", type=NodeType.COMPANY,
                stock_code="002405", sector="ai_software", market_cap="mid_cap",
                metadata={"description": "自动驾驶/高精地图", "market": "A"}
            ),
            GraphNode(
                id="300033", name="同花顺", type=NodeType.COMPANY,
                stock_code="300033", sector="ai_software", market_cap="mid_cap",
                metadata={"description": "金融AI/智能投研", "market": "A"}
            ),
        ]

        for company in a_share_companies:
            self.add_node(company)

        # ========== 产品/技术节点 ==========

        products = [
            GraphNode(id="h100", name="H100 AI加速芯片", type=NodeType.PRODUCT),
            GraphNode(id="b100", name="Blackwell B100", type=NodeType.PRODUCT),
            GraphNode(id="mi300x", name="AMD MI300X", type=NodeType.PRODUCT),
            GraphNode(id="euv_lithography", name="EUV光刻机", type=NodeType.EQUIPMENT),
            GraphNode(id="hbm3e", name="HBM3e高带宽内存", type=NodeType.COMPONENT),
            GraphNode(id="hbm4", name="HBM4高带宽内存", type=NodeType.COMPONENT),
            GraphNode(id="ai_server", name="AI服务器", type=NodeType.PRODUCT),
            GraphNode(id="optical_module", name="800G光模块", type=NodeType.COMPONENT),
            GraphNode(id="coWoS", name="coWoS先进封装", type=NodeType.TECHNOLOGY),
            GraphNode(id="tsmc_3nm", name="台积电3nm工艺", type=NodeType.TECHNOLOGY),
            GraphNode(id="tsmc_2nm", name="台积电2nm工艺", type=NodeType.TECHNOLOGY),
            GraphNode(id="smic_14nm", name="中芯国际14nm工艺", type=NodeType.TECHNOLOGY),
            GraphNode(id="smic_7nm", name="中芯国际7nm工艺", type=NodeType.TECHNOLOGY),
            GraphNode(id="npu", name="NPU神经网络处理器", type=NodeType.TECHNOLOGY),
            GraphNode(id="gpu", name="GPU图形处理器", type=NodeType.TECHNOLOGY),
            GraphNode(id="fpga", name="FPGA可编程芯片", type=NodeType.TECHNOLOGY),
            GraphNode(id="asic", name="ASIC专用芯片", type=NodeType.TECHNOLOGY),
        ]

        for product in products:
            self.add_node(product)

        # ========== 美股关系定义 ==========

        # 英伟达的产品
        self.add_edge(GraphEdge("nvda", "h100", RelationType.PRODUCES, 1.0))
        self.add_edge(GraphEdge("nvda", "b100", RelationType.PRODUCES, 1.0))

        # 英伟达使用的技术
        self.add_edge(GraphEdge("nvda", "coWoS", RelationType.USES, 0.9))
        self.add_edge(GraphEdge("nvda", "tsmc_3nm", RelationType.USES, 0.9))
        self.add_edge(GraphEdge("nvda", "hbm3e", RelationType.USES, 0.8))

        # AMD 产品
        self.add_edge(GraphEdge("amd", "mi300x", RelationType.PRODUCES, 1.0))
        self.add_edge(GraphEdge("amd", "gpu", RelationType.PRODUCES, 1.0))
        self.add_edge(GraphEdge("amd", "fpga", RelationType.PRODUCES, 0.5))

        # 英伟达的供应商
        self.add_edge(GraphEdge("tsm", "nvda", RelationType.SUPPLIES_TO, 1.0, {"description": "晶圆代工"}))
        self.add_edge(GraphEdge("asml", "tsm", RelationType.SUPPLIES_TO, 1.0, {"description": "EUV光刻机"}))
        self.add_edge(GraphEdge("mu", "nvda", RelationType.SUPPLIES_TO, 0.8, {"description": "HBM3e内存"}))
        self.add_edge(GraphEdge("skx", "nvda", RelationType.SUPPLIES_TO, 0.7, {"description": "HBM4内存"}))
        self.add_edge(GraphEdge("lumentum", "nvda", RelationType.SUPPLIES_TO, 0.3, {"description": "光通信元器件"}))

        # AI服务器
        self.add_edge(GraphEdge("smci", "ai_server", RelationType.PRODUCES, 1.0))
        self.add_edge(GraphEdge("h100", "ai_server", RelationType.USES, 1.0))
        self.add_edge(GraphEdge("mi300x", "ai_server", RelationType.USES, 0.9))

        # 云服务商
        self.add_edge(GraphEdge("ai_server", "msft", RelationType.SUPPLIES_TO, 0.9))
        self.add_edge(GraphEdge("ai_server", "googl", RelationType.SUPPLIES_TO, 0.8))
        self.add_edge(GraphEdge("ai_server", "crwv", RelationType.SUPPLIES_TO, 0.7))
        self.add_edge(GraphEdge("ai_server", "amzn", RelationType.SUPPLIES_TO, 0.6))

        # 光模块
        self.add_edge(GraphEdge("lumentum", "optical_module", RelationType.PRODUCES, 1.0))
        self.add_edge(GraphEdge("optical_module", "ai_server", RelationType.USES, 0.6))

        # 竞争对手
        self.add_edge(GraphEdge("nvda", "amd", RelationType.COMPETES_WITH, 0.8))
        self.add_edge(GraphEdge("intc", "amd", RelationType.COMPETES_WITH, 0.7))
        self.add_edge(GraphEdge("mu", "skx", RelationType.COMPETES_WITH, 0.6))

        # 台积电的客户
        self.add_edge(GraphEdge("tsm", "amd", RelationType.SUPPLIES_TO, 0.9))
        self.add_edge(GraphEdge("tsm", "intc", RelationType.SUPPLIES_TO, 0.5))

        # ========== A 股关系定义 ==========

        # 寒武纪 - AI芯片
        self.add_edge(GraphEdge("688041", "npu", RelationType.PRODUCES, 1.0))
        self.add_edge(GraphEdge("688041", "asic", RelationType.PRODUCES, 0.8))
        self.add_edge(GraphEdge("688041", "gpu", RelationType.PRODUCES, 0.6))
        self.add_edge(GraphEdge("688041", "688981", RelationType.BUYS_FROM, 0.5, {"description": "晶圆代工"}))
        self.add_edge(GraphEdge("688041", "002371", RelationType.BUYS_FROM, 0.4, {"description": "半导体设备"}))

        # 景嘉微 - GPU
        self.add_edge(GraphEdge("300474", "gpu", RelationType.PRODUCES, 1.0))
        self.add_edge(GraphEdge("300474", "688981", RelationType.BUYS_FROM, 0.5, {"description": "晶圆代工"}))

        # 北方华创 - 半导体设备（国产替代ASML）
        self.add_edge(GraphEdge("002371", "euv_lithography", RelationType.PRODUCES, 0.3, {"description": "国产替代EUV"}))
        self.add_edge(GraphEdge("002371", "688981", RelationType.SUPPLIES_TO, 0.7, {"description": "向中芯国际供货"}))
        self.add_edge(GraphEdge("002371", "688012", RelationType.SUPPLIES_TO, 0.5, {"description": "向中微公司供货"}))

        # 中微公司 - 刻蚀设备
        self.add_edge(GraphEdge("688012", "688981", RelationType.SUPPLIES_TO, 0.8, {"description": "向中芯国际供货"}))
        self.add_edge(GraphEdge("688012", "euv_lithography", RelationType.PRODUCES, 0.2, {"description": "刻蚀相关设备"}))

        # 中芯国际 - 晶圆代工（国产替代台积电）
        self.add_edge(GraphEdge("688981", "smic_14nm", RelationType.PRODUCES, 1.0))
        self.add_edge(GraphEdge("688981", "smic_7nm", RelationType.PRODUCES, 0.5))
        self.add_edge(GraphEdge("688981", "688041", RelationType.SUPPLIES_TO, 0.4, {"description": "向寒武纪供货"}))
        self.add_edge(GraphEdge("688981", "002371", RelationType.BUYS_FROM, 0.7, {"description": "采购北方华创设备"}))
        self.add_edge(GraphEdge("688981", "688012", RelationType.BUYS_FROM, 0.6, {"description": "采购中微公司设备"}))
        self.add_edge(GraphEdge("tsm", "688981", RelationType.COMPETES_WITH, 0.9, {"description": "与台积电竞争"}))

        # 封装测试
        self.add_edge(GraphEdge("002185", "688981", RelationType.BUYS_FROM, 0.6, {"description": "采购中芯国际晶圆"}))
        self.add_edge(GraphEdge("600584", "688981", RelationType.BUYS_FROM, 0.7, {"description": "采购中芯国际晶圆"}))
        self.add_edge(GraphEdge("002156", "688981", RelationType.BUYS_FROM, 0.5, {"description": "采购中芯国际晶圆"}))

        # 芯片设计公司 → 中芯国际代工
        self.add_edge(GraphEdge("688008", "688981", RelationType.BUYS_FROM, 0.8, {"description": "内存接口芯片代工"}))
        self.add_edge(GraphEdge("688099", "688981", RelationType.BUYS_FROM, 0.6, {"description": "多媒体芯片代工"}))
        self.add_edge(GraphEdge("603986", "688981", RelationType.BUYS_FROM, 0.7, {"description": "存储芯片代工"}))
        self.add_edge(GraphEdge("002049", "688981", RelationType.BUYS_FROM, 0.5, {"description": "安全芯片代工"}))
        self.add_edge(GraphEdge("300223", "688981", RelationType.BUYS_FROM, 0.4, {"description": "嵌入式芯片代工"}))
        self.add_edge(GraphEdge("688220", "688981", RelationType.BUYS_FROM, 0.5, {"description": "基带芯片代工"}))
        self.add_edge(GraphEdge("300782", "688981", RelationType.BUYS_FROM, 0.4, {"description": "射频芯片代工"}))

        # 闻泰科技 - 安世半导体
        self.add_edge(GraphEdge("600745", "688981", RelationType.BUYS_FROM, 0.3, {"description": "功率半导体代工"}))

        # AI软件公司
        self.add_edge(GraphEdge("002230", "688041", RelationType.BUYS_FROM, 0.3, {"description": "采购寒武纪芯片"}))
        self.add_edge(GraphEdge("002230", "npu", RelationType.USES, 0.5, {"description": "使用NPU技术"}))
        self.add_edge(GraphEdge("688111", "688041", RelationType.BUYS_FROM, 0.2, {"description": "采购AI芯片"}))
        self.add_edge(GraphEdge("002405", "688041", RelationType.BUYS_FROM, 0.3, {"description": "采购AI芯片"}))
        self.add_edge(GraphEdge("002405", "300474", RelationType.BUYS_FROM, 0.3, {"description": "采购GPU"}))

    def to_dict(self) -> Dict:
        """导出为字典"""
        return {
            "nodes": [node.to_dict() for node in self._nodes.values()],
            "edges": [edge.to_dict() for edge in self._edges],
        }

    def visualize_supply_chain(self, stock_code: str, max_depth: int = 3) -> str:
        """
        生成供应链可视化文本图（用于调试/日志）

        Args:
            stock_code: 股票代码
            max_depth: 最大深度

        Returns:
            可视化文本
        """
        node = self.get_stock_node(stock_code)
        if not node:
            return f"未找到股票: {stock_code}"

        lines = []
        lines.append("=" * 60)
        lines.append(f"供应链可视化: {node.name} ({stock_code})")
        lines.append("=" * 60)

        lines.append(f"\n🏭 上游供应商 (深度={max_depth}):")
        upstream = self.get_upstream(node.id, max_depth)
        if upstream:
            for i, up_node in enumerate(upstream, 1):
                prefix = "  " * (max_depth - 1)
                market_tag = f"[{up_node.metadata.get('market', '?')}]" if up_node.metadata.get('market') else ""
                lines.append(f"  {i}. {prefix}{up_node.name} {market_tag} ({up_node.type.value})")
        else:
            lines.append("  (无)")

        lines.append(f"\n💼 下游客户 (深度={max_depth}):")
        downstream = self.get_downstream(node.id, max_depth)
        if downstream:
            for i, down_node in enumerate(downstream, 1):
                market_tag = f"[{down_node.metadata.get('market', '?')}]" if down_node.metadata.get('market') else ""
                lines.append(f"  {i}. {down_node.name} {market_tag} ({down_node.type.value})")
        else:
            lines.append("  (无)")

        lines.append(f"\n🏃 竞争对手:")
        competitors = self.get_competitors(node.id)
        if competitors:
            for i, comp in enumerate(competitors, 1):
                market_tag = f"[{comp.metadata.get('market', '?')}]" if comp.metadata.get('market') else ""
                lines.append(f"  {i}. {comp.name} {market_tag}")
        else:
            lines.append("  (无)")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)

    def export_to_mermaid(self, stock_code: Optional[str] = None, max_depth: int = 2) -> str:
        """
        导出为 Mermaid 格式的流程图

        Args:
            stock_code: 如果指定，只导出该股票的上下游关系；否则导出整个图
            max_depth: 最大深度

        Returns:
            Mermaid 格式的图表代码
        """
        lines = ["flowchart TB"]

        if stock_code:
            center_node = self.get_stock_node(stock_code)
            if not center_node:
                return f"未找到股票: {stock_code}"

            nodes_to_show = {center_node.id: center_node}

            for up in self.get_upstream(center_node.id, max_depth):
                nodes_to_show[up.id] = up
            for down in self.get_downstream(center_node.id, max_depth):
                nodes_to_show[down.id] = down

            edges_to_show = []
            for edge in self._edges:
                if edge.from_id in nodes_to_show and edge.to_id in nodes_to_show:
                    edges_to_show.append(edge)
        else:
            nodes_to_show = self._nodes
            edges_to_show = self._edges

        node_styles = {
            NodeType.COMPANY: "((💼))",
            NodeType.PRODUCT: "(🥽)",
            NodeType.TECHNOLOGY: "[🔧]",
            NodeType.COMPONENT: "[⚙️]",
            NodeType.EQUIPMENT: "[🏭]",
            NodeType.MATERIAL: "[📦]",
            NodeType.INFRASTRUCTURE: "[🏢]",
        }

        for node_id, node in nodes_to_show.items():
            shape = node_styles.get(node.type, "[?]")
            market = node.metadata.get('market', '')
            market_icon = '🇺🇸' if market == 'US' else '🇨🇳' if market == 'A' else ''
            label = f"{node.name}{market_icon}"
            lines.append(f'    {node_id}{shape}"{label}"')

        for edge in edges_to_show:
            edge_type_map = {
                RelationType.PRODUCES: "-->",
                RelationType.SUPPLIES_TO: "==>",
                RelationType.USES: "-->",
                RelationType.BUYS_FROM: "==>",
                RelationType.COMPETES_WITH: "-.->",
                RelationType.DEVELOPS: "-->",
            }
            arrow = edge_type_map.get(edge.type, "---")
            weight_info = f"[{edge.weight}]" if edge.weight < 1.0 else ""
            lines.append(f'    {edge.from_id} {arrow}{weight_info} {edge.to_id}')

        return "\n".join(lines)

    def export_to_graphviz(self, stock_code: Optional[str] = None, max_depth: int = 2) -> str:
        """
        导出为 Graphviz DOT 格式

        Args:
            stock_code: 如果指定，只导出该股票的上下游关系
            max_depth: 最大深度

        Returns:
            Graphviz DOT 格式的代码
        """
        lines = ["digraph SupplyChain {", "    rankdir=LR;", "    node [shape=box];"]

        if stock_code:
            center_node = self.get_stock_node(stock_code)
            if center_node:
                nodes_to_show = {center_node.id: center_node}
                for up in self.get_upstream(center_node.id, max_depth):
                    nodes_to_show[up.id] = up
                for down in self.get_downstream(center_node.id, max_depth):
                    nodes_to_show[down.id] = down
            else:
                nodes_to_show = {}
        else:
            nodes_to_show = self._nodes

        color_map = {
            "US": "lightblue",
            "A": "lightyellow",
        }

        for node_id, node in nodes_to_show.items():
            market = node.metadata.get('market', '')
            color = color_map.get(market, 'white')
            label = f'{node.name}\\n({node.stock_code or node.id})'
            lines.append(f'    {node_id} [label="{label}" fillcolor={color} style=filled];')

        for edge in self._edges:
            if edge.from_id in nodes_to_show and edge.to_id in nodes_to_show:
                edge_type_map = {
                    RelationType.PRODUCES: "solid",
                    RelationType.SUPPLIES_TO: "bold",
                    RelationType.USES: "dashed",
                    RelationType.BUYS_FROM: "bold",
                    RelationType.COMPETES_WITH: "dotted",
                }
                style = edge_type_map.get(edge.type, "solid")
                lines.append(f'    {edge.from_id} -> {edge.to_id} [style={style}];')

        lines.append("}")
        return "\n".join(lines)


_supply_chain_graph: Optional[SupplyChainKnowledgeGraph] = None


def get_supply_chain_graph() -> SupplyChainKnowledgeGraph:
    """获取产业链知识图谱（单例）"""
    global _supply_chain_graph
    if _supply_chain_graph is None:
        _supply_chain_graph = SupplyChainKnowledgeGraph()
    return _supply_chain_graph
