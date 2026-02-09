"""Failover orchestration manager."""

from __future__ import annotations

import asyncio
from typing import Any, List, Sequence


class FailoverManager:
    """Route execution through primary -> secondary -> optional tertiary."""

    def __init__(self, adapter: Any, sanitizer: Any, config: dict[str, Any]) -> None:
        self.adapter = adapter
        self.sanitizer = sanitizer
        self.config = config

    def _format_response(self, content: str, routing: Sequence[str]) -> str:
        return f"{content}\n\n--- [Routing Log] ---\n" + "\n".join(routing)

    def _format_error(self, routing: Sequence[str], msg: str) -> str:
        return f"[Task Execution Failed]\n{msg}\n\n--- [Routing Log] ---\n" + "\n".join(routing)

    async def _run_adapter(
        self, service_name: str, args: Sequence[str], input_text: str
    ) -> tuple[bool, str]:
        run_async = getattr(self.adapter, "run_async", None)
        if callable(run_async):
            return await run_async(service_name, args, input_text)
        return self.adapter.run(service_name, args, input_text)

    def execute(
        self,
        primary: str,
        secondary: str,
        prompt: str,
        mode: str,
        force_primary: bool = False,
        allow_tertiary: bool = True,
    ) -> str:
        return asyncio.run(
            self.execute_async(
                primary=primary,
                secondary=secondary,
                prompt=prompt,
                mode=mode,
                force_primary=force_primary,
                allow_tertiary=allow_tertiary,
            )
        )

    async def execute_async(
        self,
        primary: str,
        secondary: str,
        prompt: str,
        mode: str,
        force_primary: bool = False,
        allow_tertiary: bool = True,
    ) -> str:
        ok, sec_msg = self.sanitizer.inspect(prompt, mode=mode)
        if not ok:
            return sec_msg

        routing_log: List[str] = []

        routing_log.append(f"[1] Primary ({primary}): Trying...")
        success, output = await self._run_adapter(primary, [], prompt)
        if success:
            routing_log.append("    [SUCCESS]")
            return self._format_response(output, routing_log)

        routing_log.append("    [FAILED]")
        if force_primary:
            return self._format_error(
                routing_log, f"Forced Primary ({primary}) failed.\nError: {output}"
            )

        failover_prompt = f"[Context: {primary} failed] {prompt}"
        routing_log.append(f"[2] Secondary ({secondary}): Trying...")
        success, output = await self._run_adapter(secondary, [], failover_prompt)
        if success:
            routing_log.append("    [SUCCESS]")
            return self._format_response(output, routing_log)

        routing_log.append("    [FAILED]")

        if allow_tertiary and primary != "ollama":
            backup_model = self.config["models"]["ollama_final_backup_model"]
            routing_log.append("[3] Ollama: Trying...")
            success, output = await self._run_adapter("ollama", [backup_model], failover_prompt)
            if success:
                routing_log.append("    [SUCCESS]")
                return self._format_response(output, routing_log)
            routing_log.append("    [FAILED]")

        return self._format_error(routing_log, f"All services failed. Last Error: {output}")
