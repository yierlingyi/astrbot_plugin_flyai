"""飞猪 FlyAI CLI 的异步调用封装。

只依赖标准库：用 asyncio 子进程调 `flyai`，解析它输出到 stdout 的单行 JSON。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from typing import Any

CLI_PACKAGE = "@fly-ai/flyai-cli"


class FlyAIError(Exception):
    """飞猪查询过程中的可预期错误（超时、CLI 缺失、接口返回非 0 状态等）。"""


class FlyAIClient:
    """调用 flyai CLI。

    cli_mode:
        auto  —— 优先用 PATH 里的 flyai，找不到就用 npx 拉取
        flyai —— 只允许本地已安装的 flyai
        npx   —— 强制用 npx -y @fly-ai/flyai-cli
    """

    def __init__(
        self,
        *,
        cli_mode: str = "auto",
        cli_path: str = "",
        api_key: str = "",
        timeout: int = 90,
    ) -> None:
        self.cli_mode = (cli_mode or "auto").strip().lower()
        self.cli_path = (cli_path or "").strip()
        self.api_key = (api_key or "").strip()
        try:
            self.timeout = max(10, int(timeout))
        except (TypeError, ValueError):
            self.timeout = 90
        self._base_cmd: list[str] | None = None

    # ---------------------------------------------------------------- 命令拼装

    @staticmethod
    def _flag(key: str) -> str:
        return "--" + key.replace("_", "-")

    @staticmethod
    def _wrap_windows(cmd: list[str]) -> list[str]:
        """Windows 下 .cmd/.bat 不能直接 CreateProcess，需要 cmd /c。"""
        if sys.platform == "win32" and cmd and cmd[0].lower().endswith((".cmd", ".bat")):
            return ["cmd", "/c", *cmd]
        return cmd

    async def resolve_base(self) -> list[str]:
        if self._base_cmd is not None:
            return self._base_cmd

        base: list[str] = []
        if self.cli_path:
            base = [self.cli_path]
        elif self.cli_mode in ("auto", "flyai"):
            exe = shutil.which("flyai") or shutil.which("flyai.cmd")
            if exe:
                base = [exe]
            elif self.cli_mode == "flyai":
                raise FlyAIError(
                    "没找到 flyai 命令。请先执行 `npm i -g @fly-ai/flyai-cli`，"
                    "或把配置项 cli_mode 改成 npx。"
                )

        if not base:
            npx = shutil.which("npx")
            if not npx:
                raise FlyAIError(
                    "当前环境没有 node/npx，无法调用飞猪 CLI。"
                    "请在宿主机或容器内安装 Node.js 18+ 后执行 `npm i -g @fly-ai/flyai-cli`。"
                )
            base = [npx, "-y", CLI_PACKAGE]

        self._base_cmd = self._wrap_windows(base)
        return self._base_cmd

    def _build(self, base: list[str], sub: str, params: dict[str, Any] | None) -> list[str]:
        cmd = [*base, sub]
        for key, value in (params or {}).items():
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            cmd.extend([self._flag(key), text])
        return cmd

    # ---------------------------------------------------------------- 执行

    @staticmethod
    def _parse(text: str) -> dict[str, Any]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise FlyAIError(f"飞猪返回了无法解析的内容：{text[:200]}") from None
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                raise FlyAIError(f"飞猪返回的 JSON 解析失败：{exc}") from exc
        if not isinstance(data, dict):
            raise FlyAIError("飞猪返回结构异常（顶层不是对象）")
        return data

    async def run(self, sub: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        base = await self.resolve_base()
        cmd = self._build(base, sub, params)

        env = os.environ.copy()
        if self.api_key:
            env["FLYAI_API_KEY"] = self.api_key

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            raise FlyAIError(f"无法启动 `{cmd[0]}`：{exc}") from exc
        except OSError as exc:
            raise FlyAIError(f"启动飞猪 CLI 失败：{exc}") from exc

        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            raise FlyAIError(
                f"查询超时（{self.timeout} 秒）。飞猪的 ai-search 接口本身较慢，可调大插件配置里的 timeout。"
            ) from None

        stdout = out.decode("utf-8", "replace").strip()
        stderr = err.decode("utf-8", "replace").strip()

        if not stdout:
            detail = stderr[:300] or f"退出码 {proc.returncode}，无输出"
            raise FlyAIError(detail)

        payload = self._parse(stdout)
        status = payload.get("status")
        if status not in (0, "0", None):
            message = payload.get("message") or payload.get("systemMessage") or "未知错误"
            raise FlyAIError(str(message)[:300])
        return payload
