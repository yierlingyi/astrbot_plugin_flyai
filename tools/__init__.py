# -*- coding: utf-8 -*-
"""工具注册入口：一次性构建全部 LLM 工具。"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger

from .travel import ALL_TOOLS as TRAVEL_TOOLS

TOOL_CLASSES: list[Any] = [*TRAVEL_TOOLS]

EXPECTED_TOOL_NAMES: frozenset[str] = frozenset(
    {"flyai_travel_search", "flyai_flight_search", "flyai_hotel_search"}
)


def build_tools(plugin: Any) -> list[Any]:
    """每次调用都返回全新实例，避免热重载时复用旧对象。"""
    tools = []
    for cls in TOOL_CLASSES:
        tool = cls()
        tool.plugin_ref = plugin
        tools.append(tool)

    names = [tool.name for tool in tools]
    if len(set(names)) != len(names):
        raise RuntimeError(f"LLM 工具重名：{names}")

    missing = EXPECTED_TOOL_NAMES - set(names)
    if missing:
        logger.warning(f"[astrbot_plugin_flyai] 工具未注册齐全：{sorted(missing)}")

    return tools


__all__ = ["build_tools", "TOOL_CLASSES", "EXPECTED_TOOL_NAMES"]
