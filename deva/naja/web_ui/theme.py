"""主题管理"""

_request_theme = None


def get_request_theme():
    """获取请求中的主题（从 Cookie 读取）"""
    global _request_theme
    return _request_theme


def set_request_theme(theme_name: str):
    """设置请求中的主题"""
    global _request_theme
    _request_theme = theme_name
