"""Failover orchestration manager."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from typing import Any, List, Protocol, Sequence

from model_bridge.adapters.base import CLIAdapter
from model_bridge.core.error_category import ErrorInfo

_ERROR_BUFFER_MAX_SIZE = 50
_ERROR_MESSAGE_TRUNCATION = 500

_ERROR_BUFFER: deque[dict] = deque(maxlen=_ERROR_BUFFER_MAX_SIZE)


def record_error(
    provider: str,
    error_category: str,
    raw_message: str,
    timeout_value: float | None = None,
) -> None:
    """Record an error into the in-memory ring buffer."""
    _ERROR_BUFFER.append(
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "provider": provider,
            "error_category": error_category,
            "raw_message": raw_message[:_ERROR_MESSAGE_TRUNCATION],
            "timeout_value": timeout_value,
        }
    )


def get_last_errors(count: int = 5) -> list[dict]:
    """Return the last N errors from the ring buffer."""
    n = max(1, min(count, len(_ERROR_BUFFER)))
    return list(_ERROR_BUFFER)[-n:]


class SanitizerProtocol(Protocol):
    """Protocol for prompt sanitizer implementations."""

    def inspect(self, prompt: str, mode: str = "execution") -> tuple[bool, str]:
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
        self,
        routing: Sequence[str],
        msg: str,
        why_failed: str = "",
        next_action: str = "",
        errors_by_tier: dict[str, str] | None = None,
    ) -> str:
        errors_by_tier = errors_by_tier or {}
        failure_meta = "\n\n--- [Failure Metadata] ---\n"
        failure_meta += f"why_failed: {why_failed}\nnext_action: {next_action}"
        if errors_by_tier.get("primary"):
            failure_meta += f"\nprimary_error: {errors_by_tier['primary']}"
        if errors_by_tier.get("secondary"):
            failure_meta += f"\nsecondary_error: {errors_by_tier['secondary']}"
        if errors_by_tier.get("tertiary"):
            failure_meta += f"\ntertiary_error: {errors_by_tier['tertiary']}"
        return (
            f"[Task Execution Failed]\n{msg}{failure_meta}\n\n--- [Routing Log] ---\n"
            + "\n".join(routing)
        )

    async def _run_adapter(
        self,
        service_name: str,
        args: Sequence[str],
        input_text: str,
        timeout_seconds: float | None = None,
        output_mode: str = "clean",
    ) -> tuple[bool, str]:
        strip_noise = output_mode != "raw"
        return await self.adapter.run_async(
            service_name,
            args,
            input_text,
            timeout_seconds=timeout_seconds,
            strip_noise=strip_noise,
        )

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
        provider_args: dict[str, Sequence[str]] | None = None,
    ) -> str:
        return asyncio.run(
            self.execute_async(
                primary=primary,
                secondary=secondary,
                prompt=prompt,
                mode=mode,
                force_primary=force_primary,
                allow_tertiary=allow_tertiary,
                provider_args=provider_args,
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
        timeout_seconds: float | None = None,
        provider_args: dict[str, Sequence[str]] | None = None,
        output_mode: str = "clean",
    ) -> str:
        request_id = uuid.uuid4().hex
        start_ts = time.perf_counter()
        provider_args = provider_args or {}
        if output_mode not in {"clean", "raw"}:
            raise ValueError("output_mode must be one of: clean, raw")
        errors_by_tier: dict[str, str] = {}

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
        success, output = await self._run_adapter(
            primary,
            provider_args.get(primary, []),
            prompt,
            timeout_seconds=timeout_seconds,
            output_mode=output_mode,
        )
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
        errors_by_tier["primary"] = output
        primary_error_info = ErrorInfo.from_message(output, primary)
        record_error(primary, primary_error_info.category.value, output, timeout_seconds)
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
                errors_by_tier=errors_by_tier,
            )

        failover_prompt = f"[Context: {primary} failed] {prompt}"
        routing_log.append(f"[2] Secondary ({secondary}): Trying...")
        success, output = await self._run_adapter(
            secondary,
            provider_args.get(secondary, []),
            failover_prompt,
            timeout_seconds=timeout_seconds,
            output_mode=output_mode,
        )
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
        errors_by_tier["secondary"] = output
        secondary_error_info = ErrorInfo.from_message(output, secondary)
        record_error(secondary, secondary_error_info.category.value, output, timeout_seconds)

        if allow_tertiary and primary != "ollama":
            backup_model = self.config["models"]["ollama_final_backup_model"]
            routing_log.append("[3] Ollama: Trying...")
            success, output = await self._run_adapter(
                "ollama",
                list(provider_args.get("ollama", [])) or [backup_model],
                failover_prompt,
                timeout_seconds=timeout_seconds,
                output_mode=output_mode,
            )
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
            errors_by_tier["tertiary"] = output
            tertiary_error_info = ErrorInfo.from_message(output, "ollama")
            record_error("ollama", tertiary_error_info.category.value, output, timeout_seconds)

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
            errors_by_tier=errors_by_tier,
        )
