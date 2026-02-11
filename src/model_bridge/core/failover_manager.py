"""Failover orchestration manager."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, List, Protocol, Sequence

from model_bridge.adapters.base import CLIAdapter


class SanitizerProtocol(Protocol):
    """Protocol for prompt sanitizer implementations."""

    @staticmethod
    def inspect(prompt: str, mode: str = "execution") -> tuple[bool, str]:
        """Return (is_safe, message)."""


class FailoverManager:
    """Route execution through primary -> secondary -> optional tertiary."""

    def __init__(
        self, adapter: CLIAdapter, sanitizer: SanitizerProtocol, config: dict[str, Any]
    ) -> None:
        self.adapter = adapter
        self.sanitizer = sanitizer
        self.config = config
        self.telemetry_logger = logging.getLogger("model_bridge.telemetry")

    def _format_response(self, content: str, routing: Sequence[str]) -> str:
        return f"{content}\n\n--- [Routing Log] ---\n" + "\n".join(routing)

    def _format_error(
        self, routing: Sequence[str], msg: str, why_failed: str = "", next_action: str = ""
    ) -> str:
        failure_meta = (
            f"\n\n--- [Failure Metadata] ---\nwhy_failed: {why_failed}\nnext_action: {next_action}"
        )
        return (
            f"[Task Execution Failed]\n{msg}{failure_meta}\n\n--- [Routing Log] ---\n"
            + "\n".join(routing)
        )

    async def _run_adapter(
        self, service_name: str, args: Sequence[str], input_text: str
    ) -> tuple[bool, str]:
        return await self.adapter.run_async(service_name, args, input_text)

    def _emit_telemetry(
        self,
        request_id: str,
        primary: str,
        secondary: str,
        mode: str,
        routing_tier: int,
        status: str,
        error_category: str,
        latency_ms: int,
    ) -> None:
        payload = {
            "request_id": request_id,
            "primary": primary,
            "secondary": secondary,
            "mode": mode,
            "routing_tier": routing_tier,
            "status": status,
            "error_category": error_category,
            "latency_ms": latency_ms,
        }
        self.telemetry_logger.info(json.dumps(payload, ensure_ascii=False))

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
        request_id = uuid.uuid4().hex
        start_ts = time.perf_counter()

        ok, sec_msg = self.sanitizer.inspect(prompt, mode=mode)
        if not ok:
            self._emit_telemetry(
                request_id=request_id,
                primary=primary,
                secondary=secondary,
                mode=mode,
                routing_tier=0,
                status="security_block",
                error_category="security_policy",
                latency_ms=int((time.perf_counter() - start_ts) * 1000),
            )
            return sec_msg

        routing_log: List[str] = []

        routing_log.append(f"[1] Primary ({primary}): Trying...")
        success, output = await self._run_adapter(primary, [], prompt)
        if success:
            routing_log.append("    [SUCCESS]")
            self._emit_telemetry(
                request_id=request_id,
                primary=primary,
                secondary=secondary,
                mode=mode,
                routing_tier=1,
                status="success",
                error_category="none",
                latency_ms=int((time.perf_counter() - start_ts) * 1000),
            )
            return self._format_response(output, routing_log)

        routing_log.append("    [FAILED]")
        if force_primary:
            self._emit_telemetry(
                request_id=request_id,
                primary=primary,
                secondary=secondary,
                mode=mode,
                routing_tier=1,
                status="force_primary_failed",
                error_category="primary_failed_forced",
                latency_ms=int((time.perf_counter() - start_ts) * 1000),
            )
            return self._format_error(
                routing_log,
                f"Forced Primary ({primary}) failed.\nError: {output}",
                why_failed="primary_failed_and_force_primary_enabled",
                next_action=f"retry with force_primary=False or inspect {primary} availability",
            )

        failover_prompt = f"[Context: {primary} failed] {prompt}"
        routing_log.append(f"[2] Secondary ({secondary}): Trying...")
        success, output = await self._run_adapter(secondary, [], failover_prompt)
        if success:
            routing_log.append("    [SUCCESS]")
            self._emit_telemetry(
                request_id=request_id,
                primary=primary,
                secondary=secondary,
                mode=mode,
                routing_tier=2,
                status="success",
                error_category="primary_failed_recovered_secondary",
                latency_ms=int((time.perf_counter() - start_ts) * 1000),
            )
            return self._format_response(output, routing_log)

        routing_log.append("    [FAILED]")

        if allow_tertiary and primary != "ollama":
            backup_model = self.config["models"]["ollama_final_backup_model"]
            routing_log.append("[3] Ollama: Trying...")
            success, output = await self._run_adapter("ollama", [backup_model], failover_prompt)
            if success:
                routing_log.append("    [SUCCESS]")
                self._emit_telemetry(
                    request_id=request_id,
                    primary=primary,
                    secondary=secondary,
                    mode=mode,
                    routing_tier=3,
                    status="success",
                    error_category="secondary_failed_recovered_tertiary",
                    latency_ms=int((time.perf_counter() - start_ts) * 1000),
                )
                return self._format_response(output, routing_log)
            routing_log.append("    [FAILED]")

        self._emit_telemetry(
            request_id=request_id,
            primary=primary,
            secondary=secondary,
            mode=mode,
            routing_tier=3 if allow_tertiary and primary != "ollama" else 2,
            status="failed",
            error_category="all_services_failed",
            latency_ms=int((time.perf_counter() - start_ts) * 1000),
        )
        return self._format_error(
            routing_log,
            f"All services failed. Last Error: {output}",
            why_failed="all_services_failed",
            next_action="verify cli health checks and retry",
        )
