"""deva.core —— 异步流式处理底层平台。

本包只做**显式再导出**：每个符号都写明来自哪个子模块，不再用
`from .x import *`。好处是：

* 出现同名符号时来源一眼可查，不会被后导入的模块悄悄覆盖；
* `__all__` 可逐项校验 —— 旧版本里列了 reduce / distinct / http /
  from_iterable / IndexStream / FileLogStream 六个从未定义过的符号；
* 子模块之间不再经由本包互相引用，循环导入消失
  （store / sources / when / namespace 现在直接 `from .stream import Stream`）。

模块划分：

    stream.py           Stream 基类与流基础设施
    operators.py        Sink / sink / to_textfile / map / starmap / filter / run_future
    http_stream.py      httpx / crawler
    loop.py             sync / Deva
    logging_adapter.py  日志 record 归一化与默认 handler
    store.py            DBStream 时序存储
    when.py             定时 / 调度 / 事件触发
    sources.py          各类数据源
    compute/            计算算子与流图可视化
    pipe/               管道 DSL
    namespace.py        命名空间（NS / NT / NB / NW / NWT）

注意：下面的导入顺序**就是符号的生效顺序**（后者覆盖前者），
改动时不要随意调换。
"""

from __future__ import absolute_import, division, print_function

# --- 流内核 / 算子 / HTTP / 事件循环 / 日志（原 core.py 拆分而来）---
from .core import (
    Stream,
    Sink,
    identity,
    OrderedSet,
    OrderedWeakrefSet,
    sink,
    to_textfile,
    map,
    starmap,
    filter,
    run_future,
    httpx,
    crawler,
    sync,
    Deva,
    thread_state,
    no_default,
    LEVEL_ORDER,
    should_emit_level,
    normalize_record,
    format_line,
    DevaFormatter,
    setup_deva_logging,
)

# --- 管道 DSL ---
from .pipe import (
    P,
    Pipe,
    tail,
    skip,
    all,
    any,
    average,
    count,
    as_dict,
    as_set,
    permutations,
    netcat,
    netwrite,
    traverse,
    concat,
    as_list,
    as_tuple,
    stdout,
    lineout,
    tee,
    add,
    first,
    chain,
    take_while,
    attr,
    skip_while,
    aggregate,
    groupby,
    sort,
    reverse,
    chain_with,
    islice,
    izip,
    passed,
    index,
    strip,
    lstrip,
    rstrip,
    run_with,
    append,
    to_type,
    transpose,
    dedup,
    uniq,
    to_dataframe,
    pmap,
    pfilter,
    post_to,
    head,
    read,
    tcp_write,
    write_to_file,
    size,
    ls,
    range,
    sum,
    split,
    sample,
    extract,
    readlines,
    last,
    abs,
    type,
    ll,
    pslice,
    truncate,
    dir,
    help,
    mean,
    eval,
    hash,
    id,
    input,
    iter,
    len,
    max,
    min,
    print,
    get_instances_by_class,
    to_json,
    cm,
    call_method,
    sw,
    read_from,
)

# --- 日志流与总线 ---
from .bus import (
    log,
    warn,
    debug,
    bus,
    get_bus_runtime_status,
    get_bus_clients,
    get_bus_recent_messages,
    send_bus_message,
    configure_log_behavior,
)

# --- 定时 / 调度 / 事件触发 ---
from .when import (
    When,
    EventTrigger,
    Timer,
    Scheduler,
    when,
    timer,
    scheduler,
    exit,
    emit_exit_event,
)

# --- 数据源 ---
from .sources import (
    Source,
    Topic,
    TCPStream,
    TCPTopic,
    StreamTCPServer,
    StreamTCPClient,
    PeriodicCallback,
    PollingSource,
    RedisStream,
    filenames,
    from_command,
    from_http_request,
    from_http_server,
    from_kafka,
    from_mail,
    from_periodic,
    from_process,
    from_redis,
    from_tcp_port,
    from_textfile,
    gen_block_test,
    http_topic,
)

# --- 计算算子与流图可视化 ---
from .compute import (
    accumulate,
    buffer,
    collect,
    combine_latest,
    delay,
    flatten,
    latest,
    partition,
    pluck,
    rate_limit,
    slice,
    sliding_window,
    timed_window,
    union,
    unique,
    zip,
    zip_latest,
    create_edge_label_graph,
    create_graph,
    readable_graph,
    to_graphviz,
    visualize,
)

# --- 命名空间 ---
from .namespace import (
    NS,
    NT,
    NB,
    NW,
    NWT,
    Namespace,
)

# --- 时序存储 ---
from .store import DBStream

from deva.utils.ioloop import get_io_loop

__all__ = [
    'Stream',
    'Sink',
    'map',
    'filter',
    'starmap',
    'sink',
    'to_textfile',
    'run_future',
    'accumulate',
    'flatten',
    'unique',
    'union',
    'zip',
    'zip_latest',
    'combine_latest',
    'latest',
    'partition',
    'sliding_window',
    'timed_window',
    'buffer',
    'rate_limit',
    'delay',
    'collect',
    'pluck',
    'slice',
    'httpx',
    'crawler',
    'sync',
    'Deva',
    'P',
    'Pipe',
    'bus',
    'NS',
    'NT',
    'NB',
    'NW',
    'NWT',
    'Namespace',
    'store',
    'DBStream',
    'get_io_loop',
    'setup_deva_logging',
    'LEVEL_ORDER',
    'should_emit_level',
    'normalize_record',
    'format_line',
    'DevaFormatter',
]
