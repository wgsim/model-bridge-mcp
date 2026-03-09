"""SDK transport adapter (phase 4, api-key-first)."""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence, Tuple

from .base import CLIAdapter
from model_bridge.core.codex_capabilities import (
    DEFAULT_CODEX_MODEL,
    normalize_codex_reasoning_effort,
)


class SDKAdapter(CLIAdapter):
    """Adapter for direct provider SDK/API execution."""

    def __init__(
        self,
        models_config: Mapping[str, object] | None = None,
        env: Mapping[str, str] | None = None,
        system_suffix: str = "",
        apply_system_suffix_for: Mapping[str, bool] | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.models_config = dict(models_config or {})
        self.env = dict(env) if env is not None else os.environ.copy()
        self.system_suffix = system_suffix
        self.apply_system_suffix_for = dict(apply_system_suffix_for or {})
        self.timeout_seconds = timeout_seconds
        self.default_codex_model = DEFAULT_CODEX_MODEL

    def preflight_check(self, service_name: str) -> Tuple[bool, str]:
        known = {"codex", "gemini", "ollama", "claude_code"}
        if service_name not in known:
            return False, f"Unknown provider: {service_name}"
        if service_name == "codex":
            token = self._resolve_openai_token()
            if token:
                return True, "ok"
            return False, "[SDK AUTH ERROR] Missing OPENAI_API_KEY (recommended) or OPENAI_ACCESS_TOKEN."
        if service_name == "gemini":
            api_key, access_token = self._resolve_gemini_auth()
            if api_key or access_token:
                return True, "ok"
            return (
                False,
                "[SDK AUTH ERROR] Missing GEMINI_API_KEY/GOOGLE_API_KEY or GEMINI/GOOGLE OAuth access token.",
            )
        if service_name == "claude_code":
            api_key, access_token = self._resolve_anthropic_auth()
            if api_key or access_token:
                return True, "ok"
            return (
                False,
                "[SDK AUTH ERROR] Missing ANTHROPIC_API_KEY or ANTHROPIC OAuth access token.",
            )
        if service_name == "ollama":
            return self._probe_ollama()
        return False, self._build_not_implemented_error(service_name, model_name=None)

    def _oauth_env(self, provider: str, suffix: str) -> str:
        return self.env.get(f"{provider}_OAUTH_{suffix}", "").strip()

    @staticmethod
    def _coerce_expires_at(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _token_is_expired(expires_at: float | None, skew_seconds: float = 30.0) -> bool:
        if expires_at is None:
            return False
        return time.time() >= max(0.0, expires_at - skew_seconds)

    @staticmethod
    def _load_oauth_record(file_path: str) -> dict[str, Any]:
        try:
            raw = Path(file_path).expanduser().read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
        return {}

    @staticmethod
    def _save_oauth_record(file_path: str, record: dict[str, Any]) -> None:
        path = Path(file_path).expanduser()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False, indent=2, sort_keys=True)
            # os.open(mode=0o600) does not tighten permissions on pre-existing files.
            os.chmod(path, 0o600)
        except OSError:
            return

    def _oauth_post_form(
        self,
        token_url: str,
        form_data: dict[str, str],
        timeout_seconds: float,
        provider: str,
    ) -> tuple[bool, Any]:
        body = urllib.parse.urlencode(form_data).encode("utf-8")
        req = urllib.request.Request(
            token_url,
            data=body,
            method="POST",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                detail = ""
            if detail:
                return False, f"[SDK OAUTH ERROR] provider={provider} status={exc.code} detail={detail[:400]}"
            return False, f"[SDK OAUTH ERROR] provider={provider} status={exc.code}"
        except urllib.error.URLError as exc:
            return False, f"[SDK OAUTH ERROR] provider={provider} reason={exc.reason}"
        except Exception as exc:
            return False, f"[SDK OAUTH ERROR] provider={provider} error={exc}"

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return False, f"[SDK OAUTH ERROR] provider={provider} token endpoint returned non-JSON response"
        return True, parsed

    def _oauth_refresh_token(
        self,
        provider: str,
        refresh_token: str,
        token_url: str,
        client_id: str = "",
        client_secret: str = "",
        scope: str = "",
    ) -> dict[str, Any] | None:
        form = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        if client_id:
            form["client_id"] = client_id
        if client_secret:
            form["client_secret"] = client_secret
        if scope:
            form["scope"] = scope
        ok, raw = self._oauth_post_form(
            token_url=token_url,
            form_data=form,
            timeout_seconds=12.0,
            provider=provider.lower(),
        )
        if not ok or not isinstance(raw, dict):
            return None
        access_token = str(raw.get("access_token", "")).strip()
        if not access_token:
            return None
        output: dict[str, Any] = {"access_token": access_token}
        next_refresh = str(raw.get("refresh_token", "")).strip() or refresh_token
        if next_refresh:
            output["refresh_token"] = next_refresh
        expires_in = raw.get("expires_in")
        try:
            expires_in_val = int(float(expires_in))
        except (TypeError, ValueError):
            expires_in_val = 0
        if expires_in_val > 0:
            output["expires_at"] = time.time() + float(expires_in_val)
        return output

    def _resolve_oauth_access_token(self, provider: str) -> str:
        direct = self._oauth_env(provider, "ACCESS_TOKEN")
        if not direct:
            direct = self.env.get(f"{provider}_ACCESS_TOKEN", "").strip()
        if direct:
            return direct

        token_file = self._oauth_env(provider, "TOKEN_FILE")
        record = self._load_oauth_record(token_file) if token_file else {}
        access_token = str(record.get("access_token", "")).strip()
        expires_at = self._coerce_expires_at(record.get("expires_at"))
        if access_token and not self._token_is_expired(expires_at):
            return access_token

        refresh_token = self._oauth_env(provider, "REFRESH_TOKEN") or str(
            record.get("refresh_token", "")
        ).strip()
        token_url = self._oauth_env(provider, "TOKEN_URL") or str(record.get("token_url", "")).strip()
        client_id = self._oauth_env(provider, "CLIENT_ID") or str(record.get("client_id", "")).strip()
        client_secret = self._oauth_env(provider, "CLIENT_SECRET") or str(
            record.get("client_secret", "")
        ).strip()
        scope = self._oauth_env(provider, "SCOPE") or str(record.get("scope", "")).strip()
        if refresh_token and token_url:
            refreshed = self._oauth_refresh_token(
                provider=provider,
                refresh_token=refresh_token,
                token_url=token_url,
                client_id=client_id,
                client_secret=client_secret,
                scope=scope,
            )
            if refreshed:
                merged = dict(record)
                merged.update(refreshed)
                if token_url:
                    merged["token_url"] = token_url
                if client_id:
                    merged["client_id"] = client_id
                if client_secret:
                    merged["client_secret"] = client_secret
                if scope:
                    merged["scope"] = scope
                if token_file:
                    self._save_oauth_record(token_file, merged)
                return str(refreshed.get("access_token", "")).strip()

        if access_token and expires_at is None:
            return access_token
        return ""

    def _resolve_openai_token(self) -> str:
        api_key = self.env.get("OPENAI_API_KEY", "").strip()
        if api_key:
            return api_key
        return self._resolve_oauth_access_token("OPENAI")

    def _resolve_base_url(self) -> str:
        raw = self.env.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return raw.rstrip("/")

    def _resolve_gemini_api_key(self) -> str:
        key = self.env.get("GEMINI_API_KEY", "").strip()
        if key:
            return key
        return self.env.get("GOOGLE_API_KEY", "").strip()

    def _resolve_gemini_access_token(self) -> str:
        direct_candidates = (
            "GEMINI_OAUTH_ACCESS_TOKEN",
            "GEMINI_ACCESS_TOKEN",
            "GOOGLE_OAUTH_ACCESS_TOKEN",
            "GOOGLE_ACCESS_TOKEN",
        )
        for key in direct_candidates:
            token = self.env.get(key, "").strip()
            if token:
                return token
        token = self._resolve_oauth_access_token("GEMINI")
        if token:
            return token
        return self._resolve_oauth_access_token("GOOGLE")

    def _resolve_gemini_auth(self) -> tuple[str, str]:
        api_key = self._resolve_gemini_api_key()
        if api_key:
            return api_key, ""
        access_token = self._resolve_gemini_access_token()
        if access_token:
            return "", access_token
        return "", ""

    def _resolve_gemini_base_url(self) -> str:
        raw = self.env.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
        return raw.rstrip("/")

    def _resolve_anthropic_api_key(self) -> str:
        return self.env.get("ANTHROPIC_API_KEY", "").strip()

    def _resolve_anthropic_access_token(self) -> str:
        direct_candidates = (
            "ANTHROPIC_OAUTH_ACCESS_TOKEN",
            "ANTHROPIC_ACCESS_TOKEN",
        )
        for key in direct_candidates:
            token = self.env.get(key, "").strip()
            if token:
                return token
        return self._resolve_oauth_access_token("ANTHROPIC")

    def _resolve_anthropic_auth(self) -> tuple[str, str]:
        api_key = self._resolve_anthropic_api_key()
        if api_key:
            return api_key, ""
        access_token = self._resolve_anthropic_access_token()
        if access_token:
            return "", access_token
        return "", ""

    def _resolve_anthropic_base_url(self) -> str:
        raw = self.env.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        return raw.rstrip("/")

    def _resolve_anthropic_version(self) -> str:
        version = self.env.get("ANTHROPIC_API_VERSION", "").strip()
        if version:
            return version
        return "2023-06-01"

    def _resolve_anthropic_max_tokens(self) -> int:
        raw = self.env.get("ANTHROPIC_MAX_TOKENS", "").strip()
        if not raw:
            return 4096
        try:
            value = int(raw)
        except ValueError:
            return 4096
        return max(1, value)

    def _resolve_ollama_base_url(self) -> str:
        raw = self.env.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        return raw.rstrip("/")

    def _resolve_model(self, service_name: str, args: Sequence[str]) -> str | None:
        args_list = list(args)
        if "--model" in args_list:
            idx = args_list.index("--model")
            if idx + 1 < len(args_list):
                token = args_list[idx + 1].strip()
                if token:
                    return token
        if service_name == "ollama" and args_list:
            token = args_list[0].strip()
            if token:
                return token
        catalog_key = f"{service_name}_model_catalog"
        catalog = self.models_config.get(catalog_key, [])
        if isinstance(catalog, list):
            for item in catalog:
                token = str(item).strip()
                if token:
                    return token
        if service_name == "ollama":
            aliases = self.models_config.get("ollama_aliases", {})
            if isinstance(aliases, dict):
                default_alias = str(aliases.get("default", "")).strip()
                if default_alias:
                    return default_alias
            fallback = str(self.models_config.get("ollama_default_model", "")).strip()
            return fallback or None
        return None

    def _resolve_codex_model(self, args: Sequence[str]) -> str:
        from_args = self._resolve_model("codex", args)
        if from_args:
            return from_args
        catalog = self.models_config.get("codex_model_catalog", [])
        if isinstance(catalog, list):
            for item in catalog:
                token = str(item).strip()
                if token:
                    return token
        return self.default_codex_model

    def _resolve_codex_reasoning_effort(self, args: Sequence[str]) -> str | None:
        args_list = list(args)
        if "--reasoning-effort" not in args_list:
            return None
        idx = args_list.index("--reasoning-effort")
        if idx + 1 >= len(args_list):
            raise ValueError("Missing value for --reasoning-effort")
        return normalize_codex_reasoning_effort(args_list[idx + 1])

    def _resolve_gemini_model(self, args: Sequence[str]) -> str:
        from_args = self._resolve_model("gemini", args)
        if from_args:
            return from_args
        catalog = self.models_config.get("gemini_model_catalog", [])
        if isinstance(catalog, list):
            for item in catalog:
                token = str(item).strip()
                if token:
                    return token
        return "gemini-2.5-flash"

    def _resolve_claude_model(self, args: Sequence[str]) -> str:
        token = self._resolve_model("claude_code", args)
        if not token:
            token = self.env.get("ANTHROPIC_MODEL", "").strip()
        if not token:
            catalog = self.models_config.get("claude_code_model_catalog", [])
            if isinstance(catalog, list):
                for item in catalog:
                    candidate = str(item).strip()
                    if candidate:
                        token = candidate
                        break
        token = token or "sonnet"
        alias_env = {
            "haiku": self.env.get("ANTHROPIC_MODEL_HAIKU", "").strip(),
            "sonnet": self.env.get("ANTHROPIC_MODEL_SONNET", "").strip(),
            "opus": self.env.get("ANTHROPIC_MODEL_OPUS", "").strip(),
        }
        mapped = alias_env.get(token)
        if mapped:
            return mapped
        return token

    def _resolve_ollama_model(self, args: Sequence[str]) -> str | None:
        token = self._resolve_model("ollama", args)
        if token:
            return token
        return str(self.models_config.get("ollama_default_model", "")).strip() or None

    @staticmethod
    def _extract_response_text(payload: Any) -> str:
        if isinstance(payload, dict):
            output_text = payload.get("output_text")
            if isinstance(output_text, str) and output_text.strip():
                return output_text.strip()

            chunks: list[str] = []
            raw_output = payload.get("output")
            if isinstance(raw_output, list):
                for item in raw_output:
                    if not isinstance(item, dict):
                        continue
                    content = item.get("content", [])
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        text = block.get("text")
                        if isinstance(text, str) and text.strip():
                            chunks.append(text.strip())
            if chunks:
                return "\n".join(chunks)

            choices = payload.get("choices")
            if isinstance(choices, list):
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    message = choice.get("message")
                    if isinstance(message, dict):
                        content = message.get("content")
                        if isinstance(content, str) and content.strip():
                            return content.strip()
            return json.dumps(payload, ensure_ascii=False)

        if isinstance(payload, str):
            return payload.strip()
        return str(payload)

    @staticmethod
    def _extract_gemini_text(payload: Any) -> str:
        if not isinstance(payload, dict):
            return str(payload)
        candidates = payload.get("candidates")
        if isinstance(candidates, list):
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                content = candidate.get("content", {})
                if not isinstance(content, dict):
                    continue
                parts = content.get("parts")
                if not isinstance(parts, list):
                    continue
                chunks: list[str] = []
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text.strip())
                if chunks:
                    return "\n".join(chunks)
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _extract_claude_text(payload: Any) -> str:
        if not isinstance(payload, dict):
            return str(payload)
        content = payload.get("content")
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
            if chunks:
                return "\n".join(chunks)
        completion = payload.get("completion")
        if isinstance(completion, str) and completion.strip():
            return completion.strip()
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _extract_ollama_text(payload: Any) -> str:
        if not isinstance(payload, dict):
            return str(payload)
        response = payload.get("response")
        if isinstance(response, str) and response.strip():
            return response.strip()
        message = payload.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
        return json.dumps(payload, ensure_ascii=False)

    def _post_json(
        self,
        url: str,
        token: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> tuple[bool, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                detail = ""
            if detail:
                return False, f"[SDK REQUEST ERROR] provider=codex status={exc.code} detail={detail[:400]}"
            return False, f"[SDK REQUEST ERROR] provider=codex status={exc.code}"
        except urllib.error.URLError as exc:
            return False, f"[SDK REQUEST ERROR] provider=codex reason={exc.reason}"
        except Exception as exc:
            return False, f"[SDK REQUEST ERROR] provider=codex error={exc}"

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return False, "[SDK REQUEST ERROR] provider=codex returned non-JSON response"
        return True, parsed

    def _post_gemini_json(
        self,
        model: str,
        api_key: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> tuple[bool, Any]:
        base_url = self._resolve_gemini_base_url()
        model_q = urllib.parse.quote(model, safe="")
        url = f"{base_url}/v1beta/models/{model_q}:generateContent"
        headers = {"Content-Type": "application/json"}
        if api_key:
            query = urllib.parse.urlencode({"key": api_key})
            url = f"{url}?{query}"
        else:
            access_token = self._resolve_gemini_access_token()
            if not access_token:
                return (
                    False,
                    "[SDK AUTH ERROR] Missing GEMINI_API_KEY/GOOGLE_API_KEY or GEMINI/GOOGLE OAuth access token.",
                )
            headers["Authorization"] = f"Bearer {access_token}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                detail = ""
            if detail:
                return False, f"[SDK REQUEST ERROR] provider=gemini status={exc.code} detail={detail[:400]}"
            return False, f"[SDK REQUEST ERROR] provider=gemini status={exc.code}"
        except urllib.error.URLError as exc:
            return False, f"[SDK REQUEST ERROR] provider=gemini reason={exc.reason}"
        except Exception as exc:
            return False, f"[SDK REQUEST ERROR] provider=gemini error={exc}"

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return False, "[SDK REQUEST ERROR] provider=gemini returned non-JSON response"
        return True, parsed

    def _post_claude_json(
        self,
        payload: dict[str, Any],
        api_key: str,
        access_token: str,
        timeout_seconds: float,
    ) -> tuple[bool, Any]:
        url = f"{self._resolve_anthropic_base_url()}/v1/messages"
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "anthropic-version": self._resolve_anthropic_version(),
            "content-type": "application/json",
        }
        if api_key:
            headers["x-api-key"] = api_key
        elif access_token:
            headers["authorization"] = f"Bearer {access_token}"
        else:
            return (
                False,
                "[SDK AUTH ERROR] Missing ANTHROPIC_API_KEY or ANTHROPIC OAuth access token.",
            )
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                detail = ""
            if detail:
                return False, f"[SDK REQUEST ERROR] provider=claude_code status={exc.code} detail={detail[:400]}"
            return False, f"[SDK REQUEST ERROR] provider=claude_code status={exc.code}"
        except urllib.error.URLError as exc:
            return False, f"[SDK REQUEST ERROR] provider=claude_code reason={exc.reason}"
        except Exception as exc:
            return False, f"[SDK REQUEST ERROR] provider=claude_code error={exc}"

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return False, "[SDK REQUEST ERROR] provider=claude_code returned non-JSON response"
        return True, parsed

    def _post_ollama_json(
        self,
        model: str,
        prompt: str,
        timeout_seconds: float,
    ) -> tuple[bool, Any]:
        url = f"{self._resolve_ollama_base_url()}/api/generate"
        data = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                detail = ""
            if detail:
                return False, f"[SDK REQUEST ERROR] provider=ollama status={exc.code} detail={detail[:400]}"
            return False, f"[SDK REQUEST ERROR] provider=ollama status={exc.code}"
        except urllib.error.URLError as exc:
            return False, f"[SDK REQUEST ERROR] provider=ollama reason={exc.reason}"
        except Exception as exc:
            return False, f"[SDK REQUEST ERROR] provider=ollama error={exc}"

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return False, "[SDK REQUEST ERROR] provider=ollama returned non-JSON response"
        return True, parsed

    def _probe_ollama(self) -> tuple[bool, str]:
        url = f"{self._resolve_ollama_base_url()}/api/tags"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=2.0):
                return True, "ok"
        except urllib.error.HTTPError as exc:
            return False, f"[SDK PREFLIGHT ERROR] provider=ollama status={exc.code}"
        except urllib.error.URLError as exc:
            return False, f"[SDK PREFLIGHT ERROR] provider=ollama reason={exc.reason}"
        except Exception as exc:
            return False, f"[SDK PREFLIGHT ERROR] provider=ollama error={exc}"

    def _build_not_implemented_error(
        self,
        service_name: str,
        model_name: str | None,
    ) -> str:
        model_part = f", model={model_name}" if model_name else ""
        return (
            f"[SDK NOT IMPLEMENTED] provider={service_name}{model_part}. "
            "Use runtime.transport_mode='subprocess' until provider SDK handlers are implemented."
        )

    def run(
        self,
        service_name: str,
        args: Sequence[str],
        input_text: str,
        timeout_seconds: float | None = None,
        strip_noise: bool = True,
    ) -> Tuple[bool, str]:
        try:
            asyncio.get_running_loop()
            return False, "SDKAdapter.run() cannot be used inside a running event loop. Use run_async()."
        except RuntimeError:
            pass
        return asyncio.run(
            self.run_async(
                service_name,
                args,
                input_text,
                timeout_seconds=timeout_seconds,
                strip_noise=strip_noise,
            )
        )

    async def _run_codex(
        self,
        args: Sequence[str],
        full_input: str,
        timeout_seconds: float,
    ) -> tuple[bool, str]:
        token = self._resolve_openai_token()
        if not token:
            return False, "[SDK AUTH ERROR] Missing OPENAI_API_KEY (recommended) or OPENAI_ACCESS_TOKEN."
        model_name = self._resolve_codex_model(args)
        payload = {"model": model_name, "input": full_input}
        reasoning_effort = self._resolve_codex_reasoning_effort(args)
        if reasoning_effort:
            payload["reasoning"] = {"effort": reasoning_effort}
        url = f"{self._resolve_base_url()}/responses"
        ok, raw = await asyncio.to_thread(self._post_json, url, token, payload, float(timeout_seconds))
        if not ok:
            return False, str(raw)
        return True, self._extract_response_text(raw)

    async def _run_gemini(
        self,
        args: Sequence[str],
        full_input: str,
        timeout_seconds: float,
    ) -> tuple[bool, str]:
        api_key, access_token = self._resolve_gemini_auth()
        if not api_key and not access_token:
            return (
                False,
                "[SDK AUTH ERROR] Missing GEMINI_API_KEY/GOOGLE_API_KEY or GEMINI/GOOGLE OAuth access token.",
            )
        model_name = self._resolve_gemini_model(args)
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": full_input}],
                }
            ]
        }
        # api_key path is preferred; if empty, _post_gemini_json uses OAuth bearer token.
        ok, raw = await asyncio.to_thread(
            self._post_gemini_json,
            model_name,
            api_key,
            payload,
            float(timeout_seconds),
        )
        if not ok:
            return False, str(raw)
        return True, self._extract_gemini_text(raw)

    async def _run_claude_code(
        self,
        args: Sequence[str],
        full_input: str,
        timeout_seconds: float,
    ) -> tuple[bool, str]:
        api_key, access_token = self._resolve_anthropic_auth()
        if not api_key and not access_token:
            return (
                False,
                "[SDK AUTH ERROR] Missing ANTHROPIC_API_KEY or ANTHROPIC OAuth access token.",
            )
        model_name = self._resolve_claude_model(args)
        payload = {
            "model": model_name,
            "max_tokens": self._resolve_anthropic_max_tokens(),
            "messages": [{"role": "user", "content": full_input}],
        }
        ok, raw = await asyncio.to_thread(
            self._post_claude_json,
            payload,
            api_key,
            access_token,
            float(timeout_seconds),
        )
        if not ok:
            return False, str(raw)
        return True, self._extract_claude_text(raw)

    async def _run_ollama(
        self,
        args: Sequence[str],
        full_input: str,
        timeout_seconds: float,
    ) -> tuple[bool, str]:
        model_name = self._resolve_ollama_model(args)
        if not model_name:
            return False, "[MODEL ERROR] Unable to resolve Ollama model in sdk mode."
        ok, raw = await asyncio.to_thread(
            self._post_ollama_json,
            model_name,
            full_input,
            float(timeout_seconds),
        )
        if not ok:
            return False, str(raw)
        return True, self._extract_ollama_text(raw)

    async def run_async(
        self,
        service_name: str,
        args: Sequence[str],
        input_text: str,
        timeout_seconds: float | None = None,
        strip_noise: bool = True,
    ) -> Tuple[bool, str]:
        _ = strip_noise
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        if effective_timeout is None:
            effective_timeout = 120.0
        full_input = (
            input_text + self.system_suffix
            if self.apply_system_suffix_for.get(service_name, True)
            else input_text
        )

        if service_name == "codex":
            return await self._run_codex(args=args, full_input=full_input, timeout_seconds=float(effective_timeout))
        if service_name == "gemini":
            return await self._run_gemini(args=args, full_input=full_input, timeout_seconds=float(effective_timeout))
        if service_name == "claude_code":
            return await self._run_claude_code(
                args=args,
                full_input=full_input,
                timeout_seconds=float(effective_timeout),
            )
        if service_name == "ollama":
            return await self._run_ollama(args=args, full_input=full_input, timeout_seconds=float(effective_timeout))

        model_name = self._resolve_model(service_name, args)
        return False, self._build_not_implemented_error(service_name, model_name)
