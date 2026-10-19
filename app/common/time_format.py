"""时间显示格式工具。"""

from __future__ import annotations

from datetime import datetime

# 界面统一使用的显示格式，与状态栏时钟、报告中的检测时间保持一致。
DISPLAY_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def format_display_time(value: object) -> str:
    """把数据库中的 ISO 时间字符串整理成界面统一的时间文字。

    数据库里保存的是带 T 分隔符和微秒的 ISO 字符串，例如
    ``2026-09-26T14:05:00.123456``。直接显示既长又难读，因此统一转成
    ``2026-09-26 14:05:00``。遇到无法解析的内容时原样返回，避免一条异常
    记录影响整个列表的显示。
    """
    text = str(value)
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return parsed.strftime(DISPLAY_TIME_FORMAT)
