"""Provider plugins for model-bridge-mcp (P3-1).

This module provides the plugin infrastructure for extending model-bridge-mcp
with custom providers.

Example usage:

```python
from model_bridge.plugins import ProviderPlugin, register_provider

@register_provider
class MyCustomProvider(ProviderPlugin):
    @property
    def provider_id(self) -> str:
        return "my_custom"

    async def execute(self, prompt: str, model: str | None, options: dict, **kwargs) -> str:
        # Your implementation
        return "response"
```
"""

from model_bridge.plugins.base import ProviderPlugin, PluginCapabilities

# Lazy import to avoid circular dependency
def __getattr__(name: str):
    if name == "PluginLoader":
        from model_bridge.core.plugin_loader import PluginLoader
        return PluginLoader
    if name == "register_provider":
        from model_bridge.core.plugin_loader import register_provider
        return register_provider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ProviderPlugin",
    "PluginCapabilities",
    "PluginLoader",
    "register_provider",
]
