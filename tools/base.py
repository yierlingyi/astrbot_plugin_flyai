# -*- coding: utf-8 -*-
"""LLM 工具基类与公共辅助。"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

from ..core.cli import FlyAIError
from ..core.render import render_payload


def schema(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required or []}


def prop(desc: str, type_: str = "string", **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"type": type_, "description": desc}
    out.update(extra)
    return out


class FlyAITool(FunctionTool[AstrAgentContext]):
    """飞猪工具的公共基类。

    插件实例通过 ``plugin_ref`` 注入，不声明成 dataclass 字段，
    避免 pydantic 把插件对象当成需要校验/序列化的数据。
    """

    plugin_ref: ClassVar[Any] = None

    @property
    def client(self) -> Any:
        return getattr(self.plugin_ref, "client", None)

    async def search(self, sub: str, params: dict[str, Any]) -> str:
        """调用一个 flyai 子命令并把结果渲染成聊天可读文本。"""
        client = self.client
        if client is None:
            return "飞猪插件尚未初始化完成，请稍后再试。"
        try:
            payload = await client.run(sub, params)
        except FlyAIError as exc:
            return f"飞猪查询失败：{exc}"
        return render_payload(
            payload,
            limit=int(getattr(self.plugin_ref, "max_items", 5) or 5),
            price_note=bool(getattr(self.plugin_ref, "price_note", True)),
        )


__all__ = [
    "FlyAITool",
    "ContextWrapper",
    "FunctionTool",
    "ToolExecResult",
    "AstrAgentContext",
    "Field",
    "dataclass",
    "schema",
    "prop",
]
