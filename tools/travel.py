# -*- coding: utf-8 -*-
"""查询类工具：语义搜索、机票、酒店。"""

from __future__ import annotations

from typing import Any

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

from .base import Field, FlyAITool, dataclass, prop, schema


@dataclass
class TravelSearchTool(FlyAITool):
    name: str = "flyai_travel_search"
    description: str = (
        "用飞猪实时数据做全品类旅行搜索，一次覆盖景点玩乐、门票、演出赛事、机酒套餐、"
        "签证、邮轮、租车、电话卡。返回带价格的结果和飞猪下单短链。"
        "适用场景：用户问『某地有什么好玩的』『这趟怎么安排』『附近住哪』这类开放问题，"
        "或者用户没给出发地/日期等结构化条件时。"
        "如果用户明确说了出发地、目的地和日期，请改用 flyai_flight_search 或 flyai_hotel_search，"
        "那两条返回的是可比价的结构化列表。"
    )
    parameters: dict = Field(
        default_factory=lambda: schema(
            {
                "query": prop(
                    "用户的旅行需求原话，尽量保留口语条件，例如"
                    "『五一杭州三天 人均2000 想住西湖附近』『三亚亲子游 带孩子』"
                )
            },
            ["query"],
        )
    )

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        query = str(kwargs.get("query") or "").strip()
        if not query:
            return "缺少 query 参数，请把用户的旅行需求原话传进来。"
        return await self.search("ai-search", {"query": query})


@dataclass
class FlightSearchTool(FlyAITool):
    name: str = "flyai_flight_search"
    description: str = (
        "查询实时航班报价。用户提到『机票』『航班』『几点的飞机』并给出出发地和目的地时必须用这个。"
        "支持单程；返回航班号、起降机场与时刻、飞行时长、舱位和票价，票价默认从低到高排序，"
        "每条带飞猪下单短链。"
    )
    parameters: dict = Field(
        default_factory=lambda: schema(
            {
                "origin": prop("出发城市，例如 北京"),
                "destination": prop("到达城市，例如 成都"),
                "dep_date": prop("出发日期，必须 YYYY-MM-DD"),
                "max_price": prop("可选，最高票价（人民币，纯数字）"),
            },
            ["origin", "destination", "dep_date"],
        )
    )

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        origin = str(kwargs.get("origin") or "").strip()
        destination = str(kwargs.get("destination") or "").strip()
        dep_date = str(kwargs.get("dep_date") or "").strip()
        if not (origin and destination and dep_date):
            return "缺参数：origin、destination、dep_date 三个都必填。"

        params: dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "dep_date": dep_date,
            "sort_type": 3,
        }
        max_price = str(kwargs.get("max_price") or "").strip()
        if max_price:
            params["max_price"] = max_price
        return await self.search("search-flight", params)


@dataclass
class HotelSearchTool(FlyAITool):
    name: str = "flyai_hotel_search"
    description: str = (
        "查询实时酒店。用户提到『酒店』『住哪』『民宿』『客栈』时必须用这个。"
        "可按城市搜、按周边地标搜（例如西湖附近），返回酒店名、档次/星级、位置、"
        "周边地标、价格区间和飞猪详情短链，默认按评分排序。"
    )
    parameters: dict = Field(
        default_factory=lambda: schema(
            {
                "dest_name": prop("目的地城市或区县，例如 杭州"),
                "check_in_date": prop("可选，入住日期 YYYY-MM-DD，不确定就留空"),
                "check_out_date": prop("可选，退房日期 YYYY-MM-DD"),
                "poi_name": prop("可选，附近地标或景点名，例如 西湖、迪士尼"),
            },
            ["dest_name"],
        )
    )

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        dest_name = str(kwargs.get("dest_name") or "").strip()
        if not dest_name:
            return "缺参数：dest_name 必填。"

        params: dict[str, Any] = {"dest_name": dest_name, "sort": "rate_desc"}
        for key in ("check_in_date", "check_out_date"):
            value = str(kwargs.get(key) or "").strip()
            if value:
                params[key] = value
        poi_name = str(kwargs.get("poi_name") or "").strip()
        if poi_name:
            params["poi_name"] = poi_name
        return await self.search("search-hotel", params)


ALL_TOOLS = [TravelSearchTool, FlightSearchTool, HotelSearchTool]
