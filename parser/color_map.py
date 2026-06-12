"""颜色名称到 HEX 的映射表。

支持中文颜色名和常见英文名，用于语音识别后的命令解析。

覆盖 30+ 基础颜色 + 常见深浅变体。
"""

from __future__ import annotations

from typing import Dict

# 中文颜色名 → HEX（优先级从高到低，重复名后覆盖）
COLOR_MAP: Dict[str, str] = {
    # --- 基础色 ---
    "红": "#FF0000",
    "红色": "#FF0000",
    "蓝": "#0000FF",
    "蓝色": "#0000FF",
    "绿": "#008000",
    "绿色": "#008000",
    "黄": "#FFFF00",
    "黄色": "#FFFF00",
    "黑": "#000000",
    "黑色": "#000000",
    "白": "#FFFFFF",
    "白色": "#FFFFFF",
    "紫": "#800080",
    "紫色": "#800080",
    "橙": "#FFA500",
    "橙色": "#FFA500",
    "青": "#00FFFF",
    "青色": "#00FFFF",
    "粉": "#FFC0CB",
    "粉色": "#FFC0CB",
    "棕": "#8B4513",
    "棕色": "#8B4513",
    "灰": "#808080",
    "灰色": "#808080",

    # --- 常见深浅变体 ---
    "深蓝": "#000080",
    "浅蓝": "#ADD8E6",
    "天蓝": "#87CEEB",
    "湖蓝": "#0099FF",
    "宝蓝": "#00416A",
    "深蓝": "#00008B",
    "藏青": "#002080",

    "深绿": "#006400",
    "浅绿": "#90EE90",
    "草绿": "#7CFC00",
    "墨绿": "#004E00",
    "橄榄绿": "#808000",
    "薄荷绿": "#98FF98",

    "深红": "#8B0000",
    "浅红": "#FFB6C1",
    "玫红": "#FF007F",
    "酒红": "#800000",
    "珊瑚红": "#FF7F50",
    "樱桃红": "#DE3163",

    "深黄": "#DAA520",
    "柠檬黄": "#FFF44F",
    "金黄": "#FFD700",
    "土黄": "#D2691E",
    "鹅黄": "#FFFF80",

    "深紫": "#4B0082",
    "浅紫": "#DDA0DD",
    "薰衣草": "#E6E6FA",
    "紫罗兰": "#7F00FF",

    "深橙": "#FF4500",
    "浅橙": "#FFA07A",
    "杏色": "#FFE4C4",

    "深棕": "#654321",
    "浅棕": "#D2B48C",
    "米色": "#F5F5DC",
    "咖啡色": "#6F4E37",
    "巧克力": "#7B3F00",

    "深灰": "#A9A9A9",
    "浅灰": "#D3D3D3",
    "炭灰": "#36454F",
    "银灰": "#C0C0C0",
    "铁灰": "#696969",

    "褐": "#A52A2A",
    "褐色": "#A52A2A",
    "栗色": "#601D05",

    # --- 英文名 ---
    "cyan": "#00FFFF",
    "magenta": "#FF00FF",
    "lime": "#00FF00",
    "teal": "#008080",
    "navy": "#000080",
    "maroon": "#800000",
    "olive": "#808000",
    "silver": "#C0C0C0",
    "gold": "#FFD700",
    "turquoise": "#40E0D0",
    "salmon": "#FA8072",
    "indigo": "#4B0082",
    "crimson": "#DC143C",
    "coral": "#FF7F50",
    "ivory": "#FFFFF0",
    "beige": "#F5F5DC",
    "maroon": "#800000",
    "orchid": "#DA70D6",
    "violet": "#EE82EE",
    "plum": "#DDA0DD",
    "sienna": "#A0522D",
    "khaki": "#F0E68C",
    "tomato": "#FF6347",
    "sienna": "#A0522D",
    "tan": "#D2B48C",
    "thistle": "#D8BFD8",
}


def get_color(hex_or_name: str) -> str:
    """根据颜色名或 HEX 获取 HEX 值。

    如果输入本身是有效的 HEX 格式则直接返回；
    否则在映射表中查找（不区分大小写）。

    Args:
        hex_or_name: 颜色名或 HEX 字符串。

    Returns:
        HEX 颜色字符串，找不到则返回 "#000000"（黑色）。
    """
    hex_or_name = hex_or_name.strip()

    # 检查是否已经是 HEX
    if hex_or_name.startswith("#") or (len(hex_or_name) == 6 and all(c in "0123456789ABCDEFabcdef" for c in hex_or_name)):
        return hex_or_name

    # 在映射表中查找（不区分大小写）
    return COLOR_MAP.get(hex_or_name.lower(), "#000000")


def is_known_color(name: str) -> bool:
    """检查名称是否是已知颜色。"""
    name = name.strip()
    if name.startswith("#"):
        return True
    return name.lower() in COLOR_MAP
