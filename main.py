# -*- coding: utf-8 -*-
"""飞猪旅行助手：在聊天里查机票、火车票、酒店和景点，数据实时来自飞猪。

设计要点：
1. 底层是飞猪官方开源的 flyai（阿里飞猪 2026-03 发布，MIT），不是爬虫；
2. 只做查询不代下单，结果自带飞猪短链，用户点开自己完成支付；
3. 语义搜索最慢（实测 15~40s），所以先回一句「稍等」再出结果；
4. 3 个 LLM 工具让模型自己判断什么时候该查飞猪，用户不用背指令。
"""

from __future__ import annotations

import datetime as dt
import shutil

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .core.cli import FlyAIClient, FlyAIError
from .core.render import render_payload
from .core.util import POI_CATEGORIES, as_price, split_args, split_dates
from .tools import build_tools

PLUGIN_NAME = "astrbot_plugin_flyai"

HELP_TEXT = """飞猪旅行助手 · 用法

/飞猪 <一句话需求>
   语义搜索，一次覆盖机票、酒店、景点、门票、演出、签证、邮轮
   例：/飞猪 五一杭州三天 人均2000 想住西湖附近

/机票 出发 到达 日期 [最高价]
   例：/机票 北京 成都 2026-11-25
   例：/机票 上海 东京 2026-12-01 1500

/火车 出发 到达 日期 [最高价]
   例：/火车 上海 杭州 2026-11-25

/酒店 城市 入住 离店 [关键词]
   例：/酒店 杭州 2026-11-25 2026-11-27 西湖

/景点 城市 [分类]
   例：/景点 西安 历史古迹
   例：/景点 三亚 亲子

日期支持 2026-11-25 / 11-25 / 今天 / 明天 / 后天。
结果里的链接点开即可跳飞猪下单。"""


class FlyAIPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        self.client = FlyAIClient(
            cli_mode=config.get("cli_mode", "auto"),
            cli_path=config.get("cli_path", ""),
            api_key=config.get("api_key", ""),
            timeout=config.get("timeout", 90),
        )
        self.max_items = int(config.get("max_items", 5) or 5)
        self.price_note = bool(config.get("show_price_note", True))

        if config.get("enable_llm_tool", True):
            self.context.add_llm_tools(*build_tools(self))
            logger.info(f"[{PLUGIN_NAME}] 已注册 3 个 LLM 工具")

        logger.info(f"[{PLUGIN_NAME}] 已加载，cli_mode={self.client.cli_mode}")

    # ------------------------------------------------------------------ 内部

    async def ask(self, sub: str, params: dict[str, object]) -> str:
        """执行一次 flyai 调用并渲染。异常由调用方处理。"""
        payload = await self.client.run(sub, params)
        return render_payload(payload, limit=self.max_items, price_note=self.price_note)

    # ------------------------------------------------------------------ 语义搜索

    @filter.command("飞猪", alias={"flyai", "fly", "旅行"})
    async def cmd_travel(self, event: AstrMessageEvent):
        """用一句话描述需求，搜索机票、酒店、景点等全品类旅行产品。"""
        query = " ".join(split_args(event))
        if not query:
            yield event.plain_result(HELP_TEXT)
            return

        yield event.plain_result("查一下，稍等…")
        try:
            text = await self.ask("ai-search", {"query": query})
        except FlyAIError as exc:
            yield event.plain_result(f"飞猪查询失败：{exc}")
            return
        yield event.plain_result(text)

    # ------------------------------------------------------------------ 机票

    @filter.command("机票", alias={"flight"})
    async def cmd_flight(self, event: AstrMessageEvent):
        """机票搜索：出发 到达 日期 [最高价]。"""
        tokens = split_args(event)
        if len(tokens) < 2:
            yield event.plain_result(
                "用法：/机票 出发 到达 日期 [最高价]\n例：/机票 北京 成都 2026-11-25"
            )
            return

        origin, destination = tokens[0], tokens[1]
        dates, rest = split_dates(tokens[2:], max_count=1)
        dep_date = dates[0] if dates else (dt.date.today() + dt.timedelta(days=7)).isoformat()

        params: dict[str, object] = {
            "origin": origin,
            "destination": destination,
            "dep_date": dep_date,
            "sort_type": 3,
        }
        for token in rest:
            price = as_price(token)
            if price:
                params["max_price"] = price
                break

        yield event.plain_result(f"查 {dep_date} {origin} → {destination} 的航班…")
        try:
            text = await self.ask("search-flight", params)
        except FlyAIError as exc:
            yield event.plain_result(f"机票查询失败：{exc}")
            return
        yield event.plain_result(text)

    # ------------------------------------------------------------------ 火车

    @filter.command("火车", alias={"train"})
    async def cmd_train(self, event: AstrMessageEvent):
        """火车票搜索：出发 到达 日期 [最高价]。"""
        tokens = split_args(event)
        if len(tokens) < 2:
            yield event.plain_result(
                "用法：/火车 出发 到达 日期 [最高价]\n例：/火车 上海 杭州 2026-11-25"
            )
            return

        origin, destination = tokens[0], tokens[1]
        dates, rest = split_dates(tokens[2:], max_count=1)
        dep_date = dates[0] if dates else (dt.date.today() + dt.timedelta(days=1)).isoformat()

        params: dict[str, object] = {
            "origin": origin,
            "destination": destination,
            "dep_date": dep_date,
            "sort_type": 3,
        }
        for token in rest:
            price = as_price(token)
            if price:
                params["max_price"] = price
                break

        yield event.plain_result(f"查 {dep_date} {origin} → {destination} 的车次…")
        try:
            text = await self.ask("search-train", params)
        except FlyAIError as exc:
            yield event.plain_result(f"火车票查询失败：{exc}")
            return
        yield event.plain_result(text)

    # ------------------------------------------------------------------ 酒店

    @filter.command("酒店", alias={"hotel"})
    async def cmd_hotel(self, event: AstrMessageEvent):
        """酒店搜索：城市 入住 离店 [关键词/周边地标]。"""
        tokens = split_args(event)
        if not tokens:
            yield event.plain_result(
                "用法：/酒店 城市 入住 离店 [关键词]\n例：/酒店 杭州 2026-11-25 2026-11-27 西湖"
            )
            return

        city = tokens[0]
        dates, rest = split_dates(tokens[1:])
        check_in = dates[0] if dates else (dt.date.today() + dt.timedelta(days=7)).isoformat()
        if len(dates) > 1:
            check_out = dates[1]
        else:
            check_out = (dt.date.fromisoformat(check_in) + dt.timedelta(days=2)).isoformat()
        keyword = " ".join(rest).strip()

        params: dict[str, object] = {
            "dest_name": city,
            "check_in_date": check_in,
            "check_out_date": check_out,
            "sort": "rate_desc",
        }
        if keyword:
            params["poi_name"] = keyword

        yield event.plain_result(f"查 {city} {check_in} 至 {check_out} 的酒店…")
        try:
            text = await self.ask("search-hotel", params)
        except FlyAIError as exc:
            yield event.plain_result(f"酒店查询失败：{exc}")
            return
        yield event.plain_result(text)

    # ------------------------------------------------------------------ 景点

    @filter.command("景点", alias={"poi"})
    async def cmd_poi(self, event: AstrMessageEvent):
        """景点玩乐搜索：城市 [分类或关键词]。"""
        tokens = split_args(event)
        if not tokens:
            yield event.plain_result("用法：/景点 城市 [分类]\n例：/景点 西安 历史古迹")
            return

        city = tokens[0]
        rest = " ".join(tokens[1:]).strip()
        params: dict[str, object] = {"city_name": city}
        if rest in POI_CATEGORIES:
            params["category"] = rest
        elif rest:
            params["keyword"] = rest

        prefix = f"{city} · {rest}" if rest else city
        yield event.plain_result(f"查 {prefix} 的景点…")
        try:
            text = await self.ask("search-poi", params)
        except FlyAIError as exc:
            yield event.plain_result(f"景点查询失败：{exc}")
            return
        yield event.plain_result(text)

    # ------------------------------------------------------------------ 帮助与诊断

    @filter.command("飞猪帮助", alias={"flyhelp"})
    async def cmd_help(self, event: AstrMessageEvent):
        """查看飞猪插件的全部指令。"""
        yield event.plain_result(HELP_TEXT)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("飞猪诊断")
    async def cmd_doctor(self, event: AstrMessageEvent):
        """检查飞猪 CLI 运行环境（仅管理员）。"""
        lines = [
            f"插件：{PLUGIN_NAME}",
            f"node：{shutil.which('node') or '未找到'}",
            f"npx：{shutil.which('npx') or '未找到'}",
            f"flyai：{shutil.which('flyai') or shutil.which('flyai.cmd') or '未找到'}",
            f"cli_mode：{self.client.cli_mode}",
            f"api_key：{'已配置' if self.client.api_key else '未配置（价格会打码）'}",
            f"timeout：{self.client.timeout}s · max_items：{self.max_items}",
        ]
        try:
            base = await self.client.resolve_base()
            lines.append(f"实际调用：{' '.join(base)}")
        except FlyAIError as exc:
            lines.append(f"实际调用：不可用 —— {exc}")
        yield event.plain_result("\n".join(lines))

    # ------------------------------------------------------------------ 生命周期

    async def terminate(self):
        logger.info(f"[{PLUGIN_NAME}] 已卸载")
