"""命令语法规则（预编译正则模式）。

定义所有语音命令的正则表达式模式，供 CommandParser 使用。
所有模式在模块加载时预编译，避免运行时重复编译。

引用:
- `parser/color_map.py` — 颜色映射（用于颜色槽位匹配）
"""

from __future__ import annotations

import re
from typing import Dict, Pattern

# ---------------------------------------------------------------------------
# 预编译正则模式
# ---------------------------------------------------------------------------

# 工具选择
# 匹配: "用.*画笔/铅笔/橡皮/线条" 或 ".*笔" 或单独的工具名
TOOL_PATTERNS: Dict[str, Pattern[str]] = {
    "pen": re.compile(
        r"(用[的]?)?(铅笔|画笔|笔)[^(（]*$", re.IGNORECASE
    ),
    "eraser": re.compile(
        r"(用[的]?)?(橡皮|擦除|橡皮擦)[^(（]*$", re.IGNORECASE
    ),
    "line": re.compile(
        r"(用[的]?)?(线条|直线|画线)[^(（]*$", re.IGNORECASE
    ),
}

# 颜色选择
# 匹配: ".*红色/蓝色/颜色#FF0000" 等
COLOR_PATTERN: Pattern[str] = re.compile(
    r"(颜色|色的)?(#{1}[0-9A-Fa-f]{6}|[a-zA-Z]*[红蓝绿黄黑白紫橙青粉棕灰]+)",
)

# 粗细调节
SIZE_PATTERN: Pattern[str] = re.compile(
    r"(粗|细|大小|粗细|尺寸)([的]?)(\d+)?",
)

# 形状绘制
SHAPE_PATTERNS: Dict[str, Pattern[str]] = {
    "circle": re.compile(
        r"画[^(（]*(圆|圆形|圈圈|圆圈)[^(（]*$", re.IGNORECASE
    ),
    "rectangle": re.compile(
        r"画[^(（]*(矩形|方形|正方|长方形|方框|框)[^(（]*$", re.IGNORECASE
    ),
    "triangle": re.compile(
        r"画[^(（]*(三角|三角形)[^(（]*$", re.IGNORECASE
    ),
    "star": re.compile(
        r"画[^(（]*(星|星星|五角星)[^(（]*$", re.IGNORECASE
    ),
    "line_draw": re.compile(
        r"画[^(（]*(线|直线)[^(（]*$", re.IGNORECASE
    ),
    "freehand": re.compile(
        r"(画[个只]?[的])?随便?[线線]?(条)?[^(（]*$",
    ),
}

# 相对定位
POSITION_PATTERNS: Dict[str, Pattern[str]] = {
    "center": re.compile(r"(移[到]?|从|往|到)[^(（]*(中心|中间|正中|当中)[^(（]*$"),
    "top_left": re.compile(r"(移[到]?|从|往|到)[^(（]*(左上|顶左)[^(（]*$"),
    "top_right": re.compile(r"(移[到]?|从|往|到)[^(（]*(右上|顶右)[^(（]*$"),
    "bottom_left": re.compile(r"(移[到]?|从|往|到)[^(（]*(左下|底左)[^(（]*$"),
    "bottom_right": re.compile(r"(移[到]?|从|往|到)[^(（]*(右下|底右)[^(（]*$"),
    "mid_top": re.compile(r"(移[到]?|从|往|到)[^(（]*(上中|顶上中)[^(（]*$"),
    "mid_bottom": re.compile(r"(移[到]?|从|往|到)[^(（]*(下中|底中)[^(（]*$"),
    "mid_left": re.compile(r"(移[到]?|从|往|到)[^(（]*(左中|左正中)[^(（]*$"),
    "mid_right": re.compile(r"(移[到]?|从|往|到)[^(（]*(右中|右正中)[^(（]*$"),
}

# 相对定位（从 X 到 Y 的双点模式）
POSITION_RANGE_PATTERN: Pattern[str] = re.compile(
    r"从[^(（]*(左上|左下|右上|右下|中心|中间|上中|下中|左中|右中)[^(（]*(到至|往|到|到)*[^(（]*(左上|左下|右上|右下|中心|中间|上中|下中|左中|右中)[^(（]*$"
)

# 相对位置移动（"在直线的左上方"）
RELATIVE_MOVE_PATTERN: Pattern[str] = re.compile(
    r"[在向往][到向]?(?:到)?[^(（]*(?:直线|圆|圆圈|圆形|三角|三角形|星|星星|矩形|方形|正方|长方形|它|这个|图形|对象)[^(（]*(左上方|右上方|左下方|右下方|左边|右边|上边|下边|左上|右上|左下|右下)[^(（]*$",
    re.IGNORECASE,
)

# 以已有图形为参照定位绘制（"在圆的正上方画个三角形"）
ANCHOR_SHAPE_PATTERN: Pattern[str] = re.compile(
    r"在[^(（]*(?:直线|圆|圆圈|圆形|三角|三角形|星|星星|矩形|方形|正方|长方形|它|这个|图形|对象)[^(（]*(正上|正下|左边|右边|里面)[^(（]*",
    re.IGNORECASE,
)

# 系统命令
SYSTEM_PATTERNS: Dict[str, Pattern[str]] = {
    "undo": re.compile(r"(撤销|撤回|undo|回去|返[回还])", re.IGNORECASE),
    "redo": re.compile(r"(重做|重画|redo|再[一一次]|重新)[^(（]*$", re.IGNORECASE),
    "clear": re.compile(r"(清空|清除|擦掉|全部删除|全部清除|reset)", re.IGNORECASE),
    "save": re.compile(r"(保存|存[档图]|save)", re.IGNORECASE),
    "listen_start": re.compile(r"(开始监听|开始听|打开麦克风|开始录音)", re.IGNORECASE),
    "listen_stop": re.compile(r"(停止监听|停止听|关闭麦克风|停止录音|停[止止])", re.IGNORECASE),
}

# AI 生成
AI_PATTERN: Pattern[str] = re.compile(
    r"(生成|画[一][幅张]?(张|幅)?[的]?[个]?(图|图片|画|照片|插画|海报))",
)

# 数值提取（用于大小/粗细数字）
NUMBER_PATTERN: Pattern[str] = re.compile(
    r"(\d+)"
)

# 工具 → 颜色 + 形状组合
# 匹配: "用红色画笔画个圆"
COMBO_PATTERN: Pattern[str] = re.compile(
    r"用[^(（]*(红|蓝|绿|黄|黑|白|紫|橙|青|粉|棕|灰|深蓝|浅蓝|天蓝|湖蓝|深绿|浅绿|草绿|墨绿|深红|浅红|玫红|酒红|深黄|浅黄|深紫|浅紫|深橙|浅橙|深棕|浅棕|深灰|浅灰|银|金|栗|褐|珊瑚|樱桃|柠檬|土|杏|咖啡|巧克|炭|铁|洋红|品红|粉蓝|粉绿|粉紫|粉橙|粉棕|粉灰|青紫|茶|驼|卡其|军绿|橄榄|薄荷|薰衣草|丁香|丁香|丁香|丁香)[^(（]*画笔?[^(（]*(画[个只]?[的]?)?[^(（]*(圆|圆形|矩形|方形|正方|三角形|三角|星星|星|五角星|线|直线)?[^(（]*$",
)

# 通用工具+颜色前缀
TOOL_COLOR_PREFIX: Pattern[str] = re.compile(
    r"用[^(（]*(红|蓝|绿|黄|黑|白|紫|橙|青|粉|棕|灰|深蓝|浅蓝|天蓝|湖蓝|深绿|浅绿|草绿|墨绿|深红|浅红|玫红|酒红|深黄|浅黄|深紫|浅紫|深橙|浅橙|深棕|浅棕|深灰|浅灰|银|金|栗|褐|珊瑚|樱桃|柠檬|土|杏|咖啡|巧克|炭|铁|洋红|品红|粉蓝|粉绿|粉紫|粉橙|粉棕|粉灰|青紫|茶|驼|卡其|军绿|橄榄|薄荷|薰衣草|丁香)[^(（]*画笔?[^(（]*",
)

# 颜色+形状
COLOR_SHAPE: Pattern[str] = re.compile(
    r"用[^(（]*(红|蓝|绿|黄|黑|白|紫|橙|青|粉|棕|灰|深蓝|浅蓝|天蓝|湖蓝|深绿|浅绿|草绿|墨绿|深红|浅红|玫红|酒红|深黄|浅黄|深紫|浅紫|深橙|浅橙|深棕|浅棕|深灰|浅灰|银|金|栗|褐|珊瑚|樱桃|柠檬|土|杏|咖啡|巧克|炭|铁|洋红|品红|粉蓝|粉绿|粉紫|粉橙|粉棕|粉灰|青紫|茶|驼|卡其|军绿|橄榄|薄荷|薰衣草|丁香)[^(（]*画笔?[^(（]*(画[个只]?[的]?)?[^(（]*(圆|圆形|矩形|方形|正方|三角形|三角|星星|星|五角星|线|直线)?",
)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def match_tool(text: str) -> str | None:
    """匹配工具名。

    Returns:
        工具名（"pen"/"eraser"/"line"）或 None。
    """
    for tool, pattern in TOOL_PATTERNS.items():
        if pattern.search(text):
            return tool
    return None


def match_color(text: str) -> str | None:
    """匹配颜色名。

    Returns:
        颜色名称或 None。
    """
    m = COLOR_PATTERN.search(text)
    if m:
        return m.group(2)  # 颜色名部分（不含 #）
    return None


def match_size(text: str) -> int | None:
    """匹配粗细数字。

    Returns:
        粗细数值或 None。
    """
    m = SIZE_PATTERN.search(text)
    if m and m.group(3):
        return int(m.group(3))
    # 从全文中提取第一个数字
    num = NUMBER_PATTERN.search(text)
    if num:
        val = int(num.group(1))
        return max(1, min(50, val))  # 限制在 1-50
    return None


def match_shape(text: str) -> str | None:
    """匹配形状名。

    Returns:
        形状键（"circle"/"rectangle"/"triangle"/"star"/"line_draw"/"freehand"）
        或 None。
    """
    for shape, pattern in SHAPE_PATTERNS.items():
        if pattern.search(text):
            return shape
    return None


def match_system(text: str) -> str | None:
    """匹配系统命令。

    Returns:
        命令键（"undo"/"redo"/"clear"/"save"/"listen_start"/"listen_stop"）
        或 None。
    """
    for cmd, pattern in SYSTEM_PATTERNS.items():
        if pattern.search(text):
            return cmd
    return None


def is_ai_command(text: str) -> bool:
    """判断是否是 AI 生成命令。"""
    return AI_PATTERN.search(text) is not None
