# -*- coding: utf-8 -*-
"""指令参数解析：日期归一、景点分类白名单。"""

from __future__ import annotations

import datetime as dt
from typing import Any

COMMAND_NAMES = {
    "飞猪", "flyai", "fly", "旅行",
    "机票", "flight",
    "火车", "train",
    "酒店", "hotel",
    "景点", "poi",
    "飞猪帮助", "flyhelp",
    "飞猪诊断",
}

POI_CATEGORIES = {
    "自然风光", "山湖田园", "森林丛林", "峡谷瀑布", "沙滩海岛", "沙漠草原",
    "人文古迹", "古镇古村", "历史古迹", "园林花园", "宗教场所", "公园乐园",
    "主题乐园", "水上乐园", "影视基地", "动物园", "植物园", "海洋馆",
    "体育场馆", "演出赛事", "剧院剧场", "博物馆", "纪念馆", "展览馆",
    "地标建筑", "市集", "文创街区", "城市观光", "户外活动", "滑雪",
    "漂流", "冲浪", "潜水", "露营", "温泉",
}

RELATIVE_DAYS = {"今天": 0, "今日": 0, "明天": 1, "明日": 1, "后天": 2, "大后天": 3}


def split_args(event: Any) -> list[str]:
    """从消息里取参数，兼容 AstrBot 是否保留指令名两种情况。"""
    text = str(getattr(event, "message_str", "") or "").strip()
    if not text:
        return []
    tokens = [t.strip().strip("\"'“”") for t in text.replace("\u3000", " ").split()]
    tokens = [t for t in tokens if t]
    if tokens and tokens[0].lstrip("/／").lower() in COMMAND_NAMES:
        tokens = tokens[1:]
    return tokens


def norm_date(token: str) -> str:
    """把各种日期写法归一成 YYYY-MM-DD，认不出来返回空串。"""
    token = (token or "").strip()
    if not token:
        return ""
    today = dt.date.today()

    if token in RELATIVE_DAYS:
        return (today + dt.timedelta(days=RELATIVE_DAYS[token])).isoformat()

    parts: list[str] = []
    for sep in ("-", "/", "."):
        if sep in token:
            parts = token.split(sep)
            break
    else:
        if token.isdigit() and len(token) == 8:
            return f"{token[:4]}-{token[4:6]}-{token[6:]}"
        return ""

    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return ""

    if len(nums) == 3:
        year, month, day = nums
        if year < 100:
            year += 2000
    elif len(nums) == 2:
        year, month, day = today.year, nums[0], nums[1]
    else:
        return ""

    try:
        return dt.date(year, month, day).isoformat()
    except ValueError:
        return ""


def split_dates(tokens: list[str], max_count: int = 2) -> tuple[list[str], list[str]]:
    """把 token 列表里长得像日期的挑出来（按出现顺序），其余原样返回。"""
    dates: list[str] = []
    rest: list[str] = []
    for token in tokens:
        normalized = norm_date(token)
        if normalized and len(dates) < max_count:
            dates.append(normalized)
        else:
            rest.append(token)
    return dates, rest


def as_price(token: str) -> int | None:
    """纯数字 token 当作价格上限解析，否则返回 None。"""
    cleaned = (token or "").replace(".", "").replace("元", "")
    if cleaned.isdigit() and len(cleaned) <= 7:
        return int(float(token.replace("元", "")))
    return None
