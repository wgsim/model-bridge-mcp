"""Failover orchestration manager."""

from __future__ import annotations

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

    def execute(
        self,
        primary: str,
        secondary: str,
        prompt: str,
        mode: str,
        force_primary: bool = False,
    ) -> str:
        ok, sec_msg = self.sanitizer.inspect(prompt, mode=mode)
        if not ok:
            return sec_msg

        routing_log: List[str] = []

        routing_log.append(f"[1] Primary ({primary}): Trying...")
        success, output = self.adapter.run(primary, [], prompt)
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
        success, output = self.adapter.run(secondary, [], failover_prompt)
        if success:
            routing_log.append("    [SUCCESS]")
            return self._format_response(output, routing_log)

        routing_log.append("    [FAILED]")

        if primary != "ollama":
            backup_model = self.config["models"]["ollama_final_backup_model"]
            routing_log.append("[3] Ollama: Trying...")
            success, output = self.adapter.run("ollama", [backup_model], failover_prompt)
            if success:
                routing_log.append("    [SUCCESS]")
                return self._format_response(output, routing_log)
            routing_log.append("    [FAILED]")

        return self._format_error(routing_log, f"All services failed. Last Error: {output}")

