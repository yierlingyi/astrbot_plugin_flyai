"""把飞猪返回的三种不同 JSON 结构渲染成适合聊天窗口阅读的纯文本。

实测到的三种结构（2026-11，@fly-ai/flyai-cli）：

1. ai-search        -> data 直接是一个 Markdown 字符串
2. search-flight /
   search-train     -> data.itemList[i] = {journeys, jumpUrl, ticketPrice|price, tags, totalDuration}
3. search-hotel /
   search-poi       -> data.itemList[i] = {name, address, price|ticketInfo, detailUrl|jumpUrl, star|poiLevel}
4. keyword-search   -> data.itemList[i] = {info: {title, price, jumpUrl, picUrl}}
"""

from __future__ import annotations

import re
from typing import Any

MASKED_RE = re.compile(r"[xX]")
MAX_TEXT_CHARS = 1800
PRICE_NOTE = "\n\n价格为区间价（未配置 API Key 时飞猪会自动打码），点击链接可看实价并下单。"


def _clean_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r"\1\n   \2", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS].rstrip() + "\n…（内容较长已截断）"
    return text


def _hm(value: Any) -> str:
    """'2026-11-25 21:20:00' -> '11-25 21:20'"""
    if not isinstance(value, str) or len(value) < 16:
        return str(value or "")
    return f"{value[5:10]} {value[11:16]}"


def _duration(value: Any) -> str:
    try:
        minutes = int(str(value).strip())
    except (TypeError, ValueError):
        return ""
    if minutes <= 0:
        return ""
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}小时{mins}分"
    if hours:
        return f"{hours}小时"
    return f"{mins}分"


def _place(city: Any, short: Any, full: Any) -> str:
    """拼「城市+场站」，避免「上海上海松江」这种重复。"""
    city_s = str(city or "").strip()
    station = str(short or "").strip() or str(full or "").strip()
    if not station:
        return city_s
    if city_s and station.startswith(city_s):
        return station
    return f"{city_s}{station}"


def _money(value: Any) -> str:
    """350.00 -> ¥350；¥8xx / 1xxx 这类打码价原样保留。"""
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.lstrip("¥").strip()
    if re.fullmatch(r"\d+\.00", text):
        text = text[:-3]
    return f"¥{text}"


def _pick(d: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = d.get(key)
        if value not in (None, "", [], {}):
            return str(value).strip()
    return ""


def _extract_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("itemList", "items", "list", "resultList"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _render_transport(item: dict[str, Any]) -> tuple[str, str, str] | None:
    journeys = item.get("journeys")
    if not isinstance(journeys, list) or not journeys:
        return None
    journey = journeys[0]
    segments = journey.get("segments") or []
    if not segments:
        return None

    first, last = segments[0], segments[-1]
    dep = (
        f"{_hm(first.get('depDateTime'))} "
        f"{_place(first.get('depCityName'), first.get('depStationShortName'), first.get('depStationName'))}"
    )
    arr = (
        f"{_hm(last.get('arrDateTime'))} "
        f"{_place(last.get('arrCityName'), last.get('arrStationShortName'), last.get('arrStationName'))}"
    )
    head = f"{dep} → {arr}"

    parts: list[str] = []
    journey_type = _pick(journey, "journeyType")
    if journey_type:
        parts.append(journey_type)
    carriers = _pick(first, "marketingTransportName")
    numbers = [x for x in (_pick(s, "marketingTransportNo") for s in segments) if x]
    if numbers:
        parts.append(f"{carriers} {'/'.join(numbers)}".strip())
    seat = _pick(first, "seatClassName")
    if seat:
        parts.append(seat)
    duration = _duration(item.get("totalDuration") or journey.get("totalDuration"))
    if duration:
        parts.append(duration)
    price = _pick(item, "ticketPrice", "price")
    if price:
        parts.append(_money(price))

    tags = item.get("tags")
    if isinstance(tags, list) and tags:
        parts.append("·".join(str(t) for t in tags[:2]))

    link = _pick(item, "jumpUrl", "detailUrl")
    return head, " · ".join(p for p in parts if p), link


def _render_place(item: dict[str, Any]) -> tuple[str, str, str] | None:
    name = _pick(item, "name")
    if not name:
        return None

    badges: list[str] = []
    level = _pick(item, "poiLevel")
    if level:
        badges.append(f"{level}A")
    star = _pick(item, "star")
    if star:
        badges.append(star)
    rank = _pick(item, "listRank")
    if rank:
        badges.append(rank)
    rate = _pick(item, "rate")
    if rate:
        badges.append(f"评分{rate}")
    head = name + (f"（{' · '.join(badges)}）" if badges else "")

    parts: list[str] = []
    price = _pick(item, "price")
    ticket = item.get("ticketInfo")
    if not price and isinstance(ticket, dict):
        price = _pick(ticket, "price")
        ticket_name = _pick(ticket, "ticketName")
        if price and ticket_name:
            price = f"{price} {ticket_name}"
    if price:
        parts.append(_money(price))

    near = _pick(item, "interestsPoi")
    if near:
        parts.append(near)
    address = _pick(item, "address")
    if address:
        parts.append(address)
    brand = _pick(item, "brandName")
    if brand:
        parts.append(brand)

    link = _pick(item, "detailUrl", "jumpUrl")
    return head, " · ".join(parts), link


def _render_product(item: dict[str, Any]) -> tuple[str, str, str] | None:
    info = item.get("info")
    if not isinstance(info, dict):
        return None
    title = _pick(info, "title")
    if not title:
        return None
    parts: list[str] = []
    price = _pick(info, "price")
    if price:
        parts.append(_money(price))
    score = _pick(info, "scoreDesc")
    if score:
        parts.append(score)
    star = _pick(info, "star")
    if star:
        parts.append(star)
    return title, " · ".join(parts), _pick(info, "jumpUrl")


def _render_item(index: int, item: dict[str, Any]) -> tuple[str, str, str] | None:
    for renderer in (_render_product, _render_transport, _render_place):
        try:
            result = renderer(item)
        except (AttributeError, TypeError, ValueError):
            result = None
        if result:
            head, detail, link = result
            return f"{index}. {head}", detail, link
    return None


def render_payload(
    payload: dict[str, Any],
    *,
    limit: int = 5,
    price_note: bool = True,
) -> str:
    """把一次 flyai 调用的返回体渲染成纯文本。"""
    data = payload.get("data")

    if isinstance(data, str):
        text = _clean_markdown(data)
        return text or "飞猪没有返回内容，换个问法试试。"

    items = _extract_items(data)
    if not items:
        system_message = payload.get("systemMessage")
        hint = f"\n提示：{system_message}" if system_message else ""
        return f"没查到结果。换个城市、换个日期，或者用更宽的条件再试一次。{hint}"

    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        limit = 5

    blocks: list[str] = []
    masked = False
    for index, item in enumerate(items[:limit], 1):
        rendered = _render_item(index, item)
        if not rendered:
            continue
        head, detail, link = rendered
        block = head
        if detail:
            block += f"\n   {detail}"
        if link:
            block += f"\n   {link}"
        if MASKED_RE.search(detail):
            masked = True
        blocks.append(block)

    if not blocks:
        return "查到了数据，但解析不出可展示的内容。可以试试换更具体的城市名。"

    total = len(items)
    footer = f"\n\n共 {total} 条，展示前 {len(blocks)} 条。"
    text = "\n\n".join(blocks) + footer
    if masked and price_note:
        text += PRICE_NOTE
    return text
