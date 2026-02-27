"""事件流图工具模块

该模块提供了用于可视化和分析事件流（EventStreams）的图形工具。
主要用于生成和操作流处理拓扑图。

主要功能：
- 创建流处理拓扑图
- 清理节点标签文本
- 支持上下游节点关系可视化
- 生成适合Graphviz的图形结构

示例用法：
>>> from deva import Stream
>>> from deva.graph import create_graph
>>> import networkx as nx

>>> # 创建流处理拓扑
>>> s1 = Stream()
>>> s2 = s1.map(lambda x: x * 2)
>>> s3 = s2.filter(lambda x: x > 10)

>>> # 生成图形
>>> graph = nx.DiGraph()
>>> create_graph(s3, graph)

注意事项：
- 需要安装networkx库
- 生成的图形可以直接用于Graphviz渲染
"""
from __future__ import absolute_import, division, print_function

from functools import partial
import os
import re


def _clean_text(text, match=None):
    """清理文本，移除非法字符
    
    该函数用于清理文本中的非法字符，使其适合作为图形节点标签。
    默认会保留字母、数字、下划线和冒号，其他字符将被替换为空格。
    连续的非法字符会被压缩为单个空格，冒号会被替换为分号。
    
    参数:
        text (str): 需要清理的原始文本
        match (str, 可选): 自定义的正则表达式匹配模式，默认为'[^a-zA-Z0-9_:]+'
    
    返回:
        str: 清理后的文本
    
    示例:
        >>> _clean_text("Node: 123_abc!@#")
        'Node; 123_abc'
    """
    if match is None:
        match = '[^a-zA-Z0-9_:]+'
    # 替换非法字符为空格
    text = re.sub(match, ' ', text)
    # 将冒号替换为分号
    text = re.sub(":", ";", text)
    return text

def create_graph(node, graph, prior_node=None, pc=None):
    """从单个节点创建图形，并沿上下游链进行搜索

    该函数用于从流处理拓扑中的单个节点开始，递归地创建图形表示。
    会遍历节点的上下游关系，构建完整的处理流程拓扑图。

    参数
    ----------
    node : Stream
        流处理节点实例，作为图形创建的起点
    graph : networkx.DiGraph
        用于存储图形的DiGraph实例
    prior_node : Stream, 可选
        前驱节点，用于确定节点间的连接关系
    pc : str, 可选
        连接方向，'downstream'表示下游，其他表示上游

    示例
    --------
    >>> from deva import Stream
    >>> import networkx as nx

    >>> # 创建简单流处理拓扑
    >>> s1 = Stream()
    >>> s2 = s1.map(lambda x: x * 2)
    >>> s3 = s2.filter(lambda x: x > 10)

    >>> # 生成图形
    >>> graph = nx.DiGraph()
    >>> create_graph(s3, graph)

    注意事项
    --------
    - 节点使用hash值作为唯一标识
    - 图形属性包括label、shape、orientation等
    - 会自动处理循环引用，避免重复添加边
    """
    if node is None:
        return
    t = hash(node)
    graph.add_node(t,
                   label=_clean_text(str(node)),
                   shape=node._graphviz_shape,
                   orientation=str(node._graphviz_orientation),
                   style=node._graphviz_style,
                   fillcolor=node._graphviz_fillcolor)
    if prior_node:
        tt = hash(prior_node)
        if graph.has_edge(t, tt):
            return
        if pc == 'downstream':
            graph.add_edge(tt, t)
        else:
            graph.add_edge(t, tt)

    for nodes, pc in zip([list(node.downstreams), list(node.upstreams)],
                         ['downstream', 'upstreams']):
        for node2 in nodes:
            if node2 is not None:
                create_graph(node2, graph, node, pc=pc)

def create_edge_label_graph(node, graph, prior_node=None, pc=None, i=None):
    """从单个节点创建带边标签的图形，沿上下游链搜索

    该函数用于创建带边标签的有向图，能够表示流处理拓扑中节点之间的关系。
    支持上下游关系的遍历，并为边添加标签。

    参数
    ----------
    node : Stream实例
        当前处理的流节点
    graph : networkx.DiGraph实例
        用于存储图形的有向图对象
    prior_node : Stream, 可选
        前驱节点，用于确定节点间的连接关系
    pc : str, 可选
        连接方向，'downstream'表示下游，其他表示上游
    i : int/str, 可选
        边标签的索引值，用于区分多个连接

    示例
    --------
    >>> from deva import Stream
    >>> import networkx as nx

    >>> # 创建简单流处理拓扑
    >>> s1 = Stream()
    >>> s2 = s1.map(lambda x: x * 2)
    >>> s3 = s2.filter(lambda x: x > 10)

    >>> # 生成带边标签的图形
    >>> graph = nx.DiGraph()
    >>> create_edge_label_graph(s3, graph)

    注意事项
    --------
    - 节点使用hash值作为唯一标识
    - 图形属性包括label、shape、orientation等
    - 会自动处理循环引用，避免重复添加边
    - 当存在多个连接时，会为边添加索引标签
    """
    if node is None:
        return
    t = hash(node)
    graph.add_node(t,
                   label=_clean_text(str(node)),
                   shape=node._graphviz_shape,
                   orientation=str(node._graphviz_orientation),
                   style=node._graphviz_style,
                   fillcolor=node._graphviz_fillcolor)
    if prior_node:
        tt = hash(prior_node)
        if graph.has_edge(t, tt):
            return
        if i is None:
            i = ''
        if pc == 'downstream':
            graph.add_edge(tt, t, label=str(i))
        else:
            graph.add_edge(t, tt)

    for nodes, pc in zip([list(node.downstreams), list(node.upstreams)],
                         ['downstream', 'upstreams']):
        for i, node2 in enumerate(nodes):
            if node2 is not None:
                if len(nodes) > 1:
                    create_edge_label_graph(node2, graph, node, pc=pc, i=i)
                else:
                    create_edge_label_graph(node2, graph, node, pc=pc)

def readable_graph(node, source_node=False):
    """创建可读的任务图表示

    将流处理拓扑图转换为更易读的NetworkX图表示，节点标签经过清理和去重处理。

    参数
    ----------
    node : Stream实例
        任务图中的节点
    source_node : bool, 可选
        是否作为源节点处理，默认为False

    返回
    -------
    networkx.DiGraph
        重新标记后的有向图对象

    示例
    --------
    >>> from deva import Stream
    >>> s = Stream()
    >>> g = readable_graph(s)
    >>> print(g.nodes)
    """
    import networkx as nx
    g = nx.DiGraph()
    if source_node:
        create_edge_label_graph(node, g)
    else:
        create_graph(node, g)
    mapping = {k: '{}'.format(g.node[k]['label']) for k in g}
    idx_mapping = {}
    for k, v in mapping.items():
        if v in idx_mapping.keys():
            idx_mapping[v] += 1
            mapping[k] += '-{}'.format(idx_mapping[v])
        else:
            idx_mapping[v] = 0

    gg = {k: v for k, v in mapping.items()}
    rg = nx.relabel_nodes(g, gg, copy=True)
    return rg


def to_graphviz(graph, **graph_attr):
    """将NetworkX图转换为Graphviz图对象

    参数
    ----------
    graph : networkx.DiGraph
        要转换的NetworkX图
    **graph_attr : dict
        传递给Graphviz的图形属性

    返回
    -------
    graphviz.Digraph
        Graphviz图对象
    """
    import graphviz
    gvz = graphviz.Digraph(graph_attr=graph_attr)
    for node, attrs in graph.node.items():
        gvz.node(node, **attrs)
    for edge, attrs in graph.edges().items():
        gvz.edge(edge[0], edge[1], **attrs)
    return gvz


def visualize(node, filename='mystream.png', source_node=False, **kwargs):
    """可视化任务图

    使用Graphviz渲染任务图，支持多种输出格式和IPython显示。

    参数
    ----------
    node : Stream实例
        要显示的流对象
    filename : str或None, 可选
        输出文件名（不带扩展名），默认为'mystream.png'
    source_node : bool, 可选
        是否作为源节点处理，默认为False
    **kwargs : dict
        传递给Graphviz的图形属性

    返回
    -------
    None或IPython.display.Image或IPython.display.SVG
        根据输出格式返回相应的显示对象

    异常
    -----
    RuntimeError
        当Graphviz无法生成图像时抛出

    示例
    --------
    >>> from deva import Stream
    >>> s = Stream()
    >>> visualize(s)  # 在IPython中显示图像
    >>> visualize(s, filename='mygraph')  # 保存为mygraph.png
    """
    rg = readable_graph(node, source_node=source_node)
    g = to_graphviz(rg, **kwargs)

    fmts = ['.png', '.pdf', '.dot', '.svg', '.jpeg', '.jpg']
    if filename is None:
        format = 'png'
    elif any(filename.lower().endswith(fmt) for fmt in fmts):
        filename, format = os.path.splitext(filename)
        format = format[1:].lower()
    else:
        format = 'png'

    data = g.pipe(format=format)
    if not data:
        raise RuntimeError("Graphviz无法生成图像。这可能是因为您的Graphviz安装缺少png支持。"
                         "详情请见: https://github.com/ContinuumIO/anaconda-issues/issues/485")

    display_cls = _get_display_cls(format)

    if not filename:
        return display_cls(data=data)

    full_filename = '.'.join([filename, format])
    with open(full_filename, 'wb') as f:
        f.write(data)

    return display_cls(filename=full_filename)


IPYTHON_IMAGE_FORMATS = frozenset(['jpeg', 'png'])
IPYTHON_NO_DISPLAY_FORMATS = frozenset(['dot', 'pdf'])


def _get_display_cls(format):
    """获取指定格式的IPython显示类

    参数
    ----------
    format : str
        图像格式，如'png', 'svg'等

    返回
    -------
    function
        返回相应的IPython显示类，如果IPython不可用则返回空函数

    异常
    -----
    ValueError
        当传入未知格式时抛出
    """
    dummy = lambda *args, **kwargs: None
    try:
        import IPython.display as display
    except ImportError:
        return dummy

    if format in IPYTHON_NO_DISPLAY_FORMATS:
        return dummy
    elif format in IPYTHON_IMAGE_FORMATS:
        return partial(display.Image, format=format)
    elif format == 'svg':
        return display.SVG
    else:
        raise ValueError("未知格式'%s'传递给`dot_graph`" % format)
