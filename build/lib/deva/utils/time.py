from typing import Union

def convert_interval(interval: Union[str, int, float]) -> float:
    """将不同格式的时间间隔转换为秒数

    Args:
        interval: 时间间隔，可以是字符串格式（如'1h'）或数字（秒）

    Returns:
        float: 转换后的秒数
    """
    if isinstance(interval, str):
        import pandas as pd
        interval = pd.Timedelta(interval).total_seconds()
    return float(interval)