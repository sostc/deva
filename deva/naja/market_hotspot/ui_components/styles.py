"""热点系统 UI 公共样式常量与工具函数

将散布在 cards / flow / timeline / admin / intelligence / us_market 中
高频重复的内联 CSS 值抽取到此处，便于统一维护和后续主题切换。
"""

from typing import Dict, Any

# ─── 颜色常量 ────────────────────────────────────────────────────────

# 文字
COLOR_TEXT_PRIMARY = "#1e293b"      # 主文字色（56次跨5文件）
COLOR_TEXT_SECONDARY = "#64748b"    # 次要文字（极高频）
COLOR_TEXT_MUTED = "#94a3b8"        # 弱化文字
COLOR_TEXT_DISABLED = "#cbd5e1"     # 禁用态

# 语义色
COLOR_SUCCESS = "#22c55e"
COLOR_SUCCESS_DARK = "#16a34a"
COLOR_SUCCESS_DEEPER = "#166534"
COLOR_WARNING = "#f59e0b"
COLOR_WARNING_DARK = "#b45309"
COLOR_WARNING_TEXT = "#92400e"
COLOR_DANGER = "#ef4444"
COLOR_DANGER_DARK = "#dc2626"
COLOR_INFO = "#3b82f6"
COLOR_INFO_DARK = "#1d4ed8"
COLOR_INFO_DEEPER = "#1e40af"
COLOR_PURPLE = "#8b5cf6"
COLOR_PURPLE_DARK = "#6d28d9"
COLOR_CYAN = "#06b6d4"
COLOR_PINK_DARK = "#9d174d"

# 背景 / 边框
COLOR_BG_LIGHT = "#f8fafc"
COLOR_BG_SUBTLE = "#f1f5f9"
COLOR_BG_MUTED = "#e2e8f0"
COLOR_BORDER_LIGHT = "#e2e8f0"
COLOR_BORDER_SUCCESS = "#86efac"
COLOR_BORDER_WARNING = "#f59e0b"
COLOR_BORDER_INFO = "#93c5fd"

# 状态背景色（浅底）
COLOR_BG_SUCCESS_LIGHT = "#f0fdf4"
COLOR_BG_SUCCESS_LIGHTER = "#dcfce7"
COLOR_BG_WARNING_LIGHT = "#fef3c7"
COLOR_BG_WARNING_LIGHTER = "#fde68a"
COLOR_BG_INFO_LIGHT = "#dbeafe"
COLOR_BG_INFO_LIGHTER = "#bfdbfe"
COLOR_BG_DANGER_LIGHT = "#fee2e2"
COLOR_BG_DANGER_LIGHTER = "#fecaca"
COLOR_BG_ORANGE_LIGHT = "#ffedd5"
COLOR_BG_ORANGE_LIGHTER = "#fed7aa"
COLOR_BG_PINK_LIGHT = "#fce7f3"
COLOR_BG_PINK_LIGHTER = "#fbcfe8"
COLOR_BG_PURPLE_LIGHT = "#f3e8ff"
COLOR_BG_PURPLE_LIGHTER = "#e9d5ff"
COLOR_BG_GREEN_LIGHTER = "#bbf7d0"

# 深色主题
COLOR_DARK_BG = "#0f172a"
COLOR_DARK_BG_SECONDARY = "#1e293b"
COLOR_US_MARKET_BG = "#1e3a5f"
COLOR_US_MARKET_BG_DARK = "#0d1b2a"


# ─── 渐变背景（45+ 处重复，最大优化点）──────────────────────────────

# 深色主题
GRADIENT_DARK = "linear-gradient(135deg, #1e293b 0%, #0f172a 100%)"
GRADIENT_DARK_REVERSE = "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)"
GRADIENT_US_MARKET = "linear-gradient(135deg, #1e3a5f 0%, #0d1b2a 100%)"

# 语义渐变（135deg 方向，用于面板/卡片背景）
GRADIENT_SUCCESS = f"linear-gradient(135deg, {COLOR_BG_SUCCESS_LIGHT}, {COLOR_BG_SUCCESS_LIGHTER})"
GRADIENT_WARNING = f"linear-gradient(135deg, {COLOR_BG_WARNING_LIGHT}, {COLOR_BG_WARNING_LIGHTER})"
GRADIENT_INFO = f"linear-gradient(135deg, {COLOR_BG_INFO_LIGHT}, {COLOR_BG_INFO_LIGHTER})"
GRADIENT_DANGER = f"linear-gradient(135deg, {COLOR_BG_DANGER_LIGHT}, {COLOR_BG_DANGER_LIGHTER})"
GRADIENT_PINK = f"linear-gradient(135deg, {COLOR_BG_PINK_LIGHT}, {COLOR_BG_PINK_LIGHTER})"
GRADIENT_PURPLE = f"linear-gradient(135deg, {COLOR_BG_PURPLE_LIGHT}, {COLOR_BG_PURPLE_LIGHTER})"
GRADIENT_ORANGE = f"linear-gradient(135deg, {COLOR_BG_ORANGE_LIGHT}, {COLOR_BG_ORANGE_LIGHTER})"

# 中性灰渐变
GRADIENT_NEUTRAL = f"linear-gradient(135deg, {COLOR_BG_LIGHT}, {COLOR_BG_SUBTLE})"
GRADIENT_NEUTRAL_DARK = f"linear-gradient(135deg, {COLOR_BG_SUBTLE}, {COLOR_BG_MUTED})"

# 热度等级渐变（90deg 方向，用于进度条/热度标签）
GRADIENT_HEAT_EXTREME = f"linear-gradient(90deg, {COLOR_BG_DANGER_LIGHT}, {COLOR_BG_DANGER_LIGHTER})"
GRADIENT_HEAT_HIGH = f"linear-gradient(90deg, {COLOR_BG_ORANGE_LIGHT}, {COLOR_BG_ORANGE_LIGHTER})"
GRADIENT_HEAT_MEDIUM = f"linear-gradient(90deg, {COLOR_BG_WARNING_LIGHT}, {COLOR_BG_WARNING_LIGHTER})"
GRADIENT_HEAT_LOW = f"linear-gradient(90deg, {COLOR_BG_SUCCESS_LIGHTER}, {COLOR_BG_GREEN_LIGHTER})"


# ─── 圆角常量（219 处，统一为标准值）─────────────────────────────────

RADIUS_SM = "6px"
RADIUS_MD = "8px"
RADIUS_LG = "10px"
RADIUS_XL = "12px"
RADIUS_2XL = "14px"
RADIUS_FULL = "9999px"    # 药丸形


# ─── 字体 ────────────────────────────────────────────────────────────

FONT_MONO = "font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;"


# ─── 公共组件样式生成函数 ─────────────────────────────────────────────

def card_style(
    gradient: str = GRADIENT_NEUTRAL,
    border_color: str = COLOR_BORDER_LIGHT,
    radius: str = RADIUS_XL,
    padding: str = "16px",
    margin_bottom: str = "16px",
    extra: str = "",
) -> str:
    """生成通用卡片容器样式"""
    parts = [
        f"background: {gradient}",
        f"border: 1px solid {border_color}",
        f"border-radius: {radius}",
        f"padding: {padding}",
        f"margin-bottom: {margin_bottom}",
    ]
    if extra:
        parts.append(extra)
    return "; ".join(parts) + ";"


def status_badge_style(
    bg: str,
    color: str,
    font_size: str = "11px",
    extra: str = "",
) -> str:
    """生成状态徽章样式"""
    parts = [
        f"display: inline-block",
        f"padding: 2px 8px",
        f"border-radius: {RADIUS_FULL}",
        f"background: {bg}",
        f"color: {color}",
        f"font-size: {font_size}",
        f"font-weight: 600",
    ]
    if extra:
        parts.append(extra)
    return "; ".join(parts) + ";"


def panel_header_style(color: str = COLOR_TEXT_PRIMARY) -> str:
    """面板标题样式"""
    return f"font-weight: 600; margin-bottom: 16px; color: {color};"


def metric_card_style(
    gradient: str = GRADIENT_NEUTRAL_DARK,
    radius: str = RADIUS_MD,
    padding: str = "12px",
    text_align: str = "center",
) -> str:
    """指标卡片样式（用于数字展示面板）"""
    return (
        f"background: {gradient}; "
        f"padding: {padding}; "
        f"border-radius: {radius}; "
        f"text-align: {text_align};"
    )


def info_panel_style(
    gradient: str,
    border_color: str,
    text_color: str,
    radius: str = RADIUS_LG,
    padding: str = "12px 14px",
    margin_bottom: str = "14px",
    font_size: str = "13px",
) -> str:
    """信息提示面板样式（成功/警告/信息/错误）"""
    return (
        f"margin-bottom:{margin_bottom};"
        f"padding:{padding};"
        f"border-radius:{radius};"
        f"background:{gradient};"
        f"border:1px solid {border_color};"
        f"color:{text_color};"
        f"font-size:{font_size};"
    )


def summary_card_style(
    gradient: str,
    border_color: str,
    radius: str = RADIUS_XL,
    padding: str = "16px",
) -> str:
    """概览卡片样式（4 宫格用）"""
    return (
        f"background: {gradient}; "
        f"border: 2px solid {border_color}; "
        f"border-radius: {radius}; "
        f"padding: {padding}; "
        f"text-align: center;"
    )


# ─── 热度等级工具 ─────────────────────────────────────────────────────

def heat_level(weight: float) -> tuple:
    """根据权重返回 (颜色, 状态文字, 背景渐变)

    用于 cards.py render_hot_blocks_and_stocks 等处。
    """
    if weight > 0.7:
        return COLOR_DANGER_DARK, "🔥 极高", GRADIENT_HEAT_EXTREME
    elif weight > 0.5:
        return "#ea580c", "⚡ 高", GRADIENT_HEAT_HIGH
    elif weight > 0.3:
        return "#ca8a04", "👁️ 中", GRADIENT_HEAT_MEDIUM
    else:
        return COLOR_SUCCESS_DARK, "💤 低", GRADIENT_HEAT_LOW


# ─── 市场时段格式化（合并自 cards / flow / admin 的重复定义）─────────

def format_market_line(label: str, info: Dict[str, Any], *, html: bool = False) -> str:
    """格式化市场时段行

    Parameters
    ----------
    label : str
        市场标签，如 "🇨🇳 A股" 或 "🇺🇸 美股"
    info : dict
        来自 get_market_phase_summary() 的市场信息字典
    html : bool
        True 时输出带 <span> 标签和颜色的 HTML（admin 面板用）；
        False 时输出纯文本（cards / flow 用）。
    """
    phase_name = info.get('phase_name', '未知')
    next_phase = info.get('next_phase_name', '')
    next_time = info.get('next_change_time', '')

    if html:
        next_info = f' → {next_phase} {next_time}' if next_phase else ''
        color = COLOR_SUCCESS if phase_name in ('交易中', '集合竞价') else COLOR_WARNING
        return (
            f'<span style="color:{color};font-weight:bold;">{label}:</span> '
            f'<span style="font-size:11px;">{phase_name}{next_info}</span>'
        )
    else:
        if info.get('phase') == 'closed' and next_time:
            return f"{label}{phase_name} →{next_phase} {next_time}"
        return f"{label}{phase_name}"
