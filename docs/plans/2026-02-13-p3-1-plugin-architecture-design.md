# P3-1: Plugin Architecture Design

## Goal

Enable dynamic loading of external provider adapters as plugins, allowing users to extend model-bridge-mcp without modifying core code.

## Current Architecture

```python
# main.py - hardcoded dispatchers
def _get_provider_dispatchers():
    return {
        "codex": ask_chatgpt_cli,
        "gemini": ask_gemini_cli,
        "ollama": ask_ollama,
        "claude_code": ask_claude_code,
    }
```

## Target Architecture

```
src/model_bridge/
├── core/
│   ├── provider_registry.py      # Existing - provider metadata
│   └── plugin_loader.py          # NEW - plugin discovery & loading
├── plugins/                       # NEW - built-in plugins directory
│   ├── __init__.py
│   └── base.py                   # NEW - base plugin interface
└── main.py                       # Modified - use plugin loader

plugins/                           # EXTERNAL - user plugins directory
├── my_provider/
│   └── plugin.py
```

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Plugin location | `~/.model_bridge/plugins/` + built-in | User plugins outside codebase, built-in for defaults |
| Discovery | Directory scan + entry points | Simple file-based + optional setuptools entry points |
| Registration | `@register_provider` decorator | Pythonic, explicit, type-safe |
| Interface | Abstract base class | Clear contract, IDE support |

## Plugin Interface

```python
# src/model_bridge/plugins/base.py
from abc import ABC, abstractmethod
from typing import Callable, Awaitable

class ProviderPlugin(ABC):
    """Base class for provider plugins."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier (e.g., 'openai', 'anthropic')."""
        pass

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Provider capabilities. Defaults can be overridden."""
        return ProviderCapabilities()

    @abstractmethod
    async def execute(
        self,
        prompt: str,
        model: str | None,
        options: dict,
        **kwargs,
    ) -> str:
        """Execute a prompt and return the response."""
        pass

    def is_configured(self) -> bool:
        """Check if provider is properly configured."""
        return True
```

## Registration Decorator

```python
# src/model_bridge/plugins/__init__.py
from model_bridge.core.plugin_loader import PluginRegistry

def register_provider(cls):
    """Decorator to register a provider plugin."""
    PluginRegistry.instance().register(cls())
    return cls
```

## Example External Plugin

```python
# ~/.model_bridge/plugins/openai/plugin.py
from model_bridge.plugins import register_provider, ProviderPlugin, ProviderCapabilities

@register_provider
class OpenAIProvider(ProviderPlugin):
    @property
    def provider_id(self) -> str:
        return "openai"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_json=True,
            supports_stream=True,
            supports_force_model=True,
        )

    async def execute(self, prompt: str, model: str | None, options: dict, **kwargs) -> str:
        # Implementation using OpenAI API
        import openai
        response = await openai.ChatCompletion.acreate(...)
        return response.choices[0].message.content

    def is_configured(self) -> bool:
        import os
        return bool(os.environ.get("OPENAI_API_KEY"))
```

## Implementation Plan

### Step 1: Create plugin infrastructure
- `src/model_bridge/plugins/__init__.py` - exports and decorator
- `src/model_bridge/plugins/base.py` - ProviderPlugin ABC

### Step 2: Create plugin loader
- `src/model_bridge/core/plugin_loader.py` - PluginLoader class
  - `discover_plugins()` - scan directories
  - `load_plugin(path)` - import and register
  - `get_handlers()` - return handler dict for dispatch

### Step 3: Integrate with main.py
- Replace `_get_provider_dispatchers()` with `PluginLoader.get_handlers()`
- Initialize plugins at startup

### Step 4: Migrate built-in providers
- Create plugin wrappers for codex, gemini, ollama, claude_code
- Keep backward compatibility

### Step 5: Tests
- `tests/unit/test_plugin_loader.py`
- `tests/fixtures/plugins/` - test plugins

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/model_bridge/plugins/__init__.py` | CREATE |
| `src/model_bridge/plugins/base.py` | CREATE |
| `src/model_bridge/core/plugin_loader.py` | CREATE |
| `src/model_bridge/main.py` | MODIFY |
| `tests/unit/test_plugin_loader.py` | CREATE |
| `docs/IMPROVEMENT_ROADMAP.md` | MODIFY |

## Verification

1. Existing tests pass (backward compatibility)
2. External plugin can be loaded and used
3. `@register_provider` decorator works
4. Provider registry reflects loaded plugins
