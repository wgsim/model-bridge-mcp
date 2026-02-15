"""Plugin loader for dynamic provider discovery (P3-1)."""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from model_bridge.plugins.base import PluginCapabilities, ProviderPlugin
from model_bridge.core.provider_registry import ProviderCapabilities, ProviderSpec, ProviderRegistry

if TYPE_CHECKING:
    pass

logger = logging.getLogger("model_bridge.plugin_loader")


class PluginLoader:
    """Discovers and loads provider plugins from directories.

    Plugins are discovered from:
    1. Built-in plugins in `src/model_bridge/plugins/builtins/`
    2. User plugins in `~/.model_bridge/plugins/`

    Plugin files should:
    - Be named `plugin.py` or end with `_plugin.py`
    - Use `@register_provider` decorator on provider classes
    - Extend `ProviderPlugin` base class
    """

    _instance: PluginLoader | None = None

    def __init__(self) -> None:
        self._plugins: dict[str, ProviderPlugin] = {}
        self._loaded = False

    @classmethod
    def instance(cls) -> PluginLoader:
        """Get singleton instance of PluginLoader."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing)."""
        cls._instance = None

    def register(self, plugin: ProviderPlugin) -> None:
        """Register a plugin instance.

        Called automatically by @register_provider decorator.

        Args:
            plugin: ProviderPlugin instance to register

        Raises:
            ValueError: If provider_id is already registered
        """
        provider_id = plugin.provider_id
        if provider_id in self._plugins:
            raise ValueError(f"Provider '{provider_id}' is already registered")
        self._plugins[provider_id] = plugin
        logger.info("Registered plugin: %s", provider_id)

    def discover_and_load(self, extra_paths: list[str] | None = None) -> int:
        """Discover and load all plugins.

        Args:
            extra_paths: Additional directories to search for plugins

        Returns:
            Number of plugins loaded
        """
        if self._loaded:
            return len(self._plugins)

        paths = self._get_plugin_paths(extra_paths)
        loaded_count = 0

        # Load from directories
        for path in paths:
            if path.exists():
                loaded_count += self._load_from_directory(path)

        # Load from entry points
        loaded_count += self._load_from_entry_points()

        self._loaded = True
        return loaded_count

    def _load_from_entry_points(self) -> int:
        """Load plugins from setuptools entry points.

        Entry points should be registered under the 'model_bridge.plugins' group.

        Example setup.py:
            entry_points={
                'model_bridge.plugins': [
                    'my_provider = my_package.plugin:MyProviderPlugin',
                ],
            }
        """
        loaded = 0

        try:
            # Python 3.10+ uses importlib.metadata
            from importlib.metadata import entry_points
        except ImportError:
            # Python 3.9 fallback
            from importlib_metadata import entry_points

        try:
            # Get entry points for our group
            eps = entry_points()
            if hasattr(eps, 'select'):
                # Python 3.10+ API
                group = eps.select(group='model_bridge.plugins')
            else:
                # Python 3.9 API
                group = eps.get('model_bridge.plugins', [])

            for ep in group:
                try:
                    # Load the entry point - it should be a ProviderPlugin class
                    plugin_class = ep.load()
                    # If it's a class, instantiate and register
                    if isinstance(plugin_class, type):
                        plugin = plugin_class()
                        self.register(plugin)
                    else:
                        # If it's already an instance, register directly
                        self.register(plugin_class)
                    loaded += 1
                    logger.info("Loaded plugin from entry point: %s", ep.name)
                except Exception as e:
                    logger.error("Failed to load entry point %s: %s", ep.name, e)

        except Exception as e:
            logger.debug("No entry points found or error loading: %s", e)

        return loaded

    def _get_plugin_paths(self, extra_paths: list[str] | None = None) -> list[Path]:
        """Get all paths to search for plugins."""
        paths = []

        # Built-in plugins directory
        builtin_path = Path(__file__).parent.parent / "plugins" / "builtins"
        paths.append(builtin_path)

        # User plugins directory
        user_path = Path.home() / ".model_bridge" / "plugins"
        paths.append(user_path)

        # Extra paths
        if extra_paths:
            paths.extend(Path(p) for p in extra_paths)

        return paths

    def _load_from_directory(self, directory: Path) -> int:
        """Load plugins from a directory.

        Looks for:
        - plugin.py files
        - *_plugin.py files
        - Subdirectories with plugin.py
        """
        loaded = 0

        for item in directory.iterdir():
            if item.is_file() and self._is_plugin_file(item):
                if self._load_plugin_file(item):
                    loaded += 1
            elif item.is_dir() and (item / "plugin.py").exists():
                if self._load_plugin_file(item / "plugin.py"):
                    loaded += 1

        return loaded

    def _is_plugin_file(self, path: Path) -> bool:
        """Check if a file is a plugin file."""
        name = path.name
        return name == "plugin.py" or name.endswith("_plugin.py")

    def _load_plugin_file(self, path: Path) -> bool:
        """Load a single plugin file.

        Args:
            path: Path to the plugin file

        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_{path.stem}",
                path,
            )
            if spec is None or spec.loader is None:
                logger.warning("Could not load spec for: %s", path)
                return False

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            logger.debug("Loaded plugin file: %s", path)
            return True

        except Exception as e:
            logger.error("Failed to load plugin %s: %s", path, e)
            return False

    def get_plugin(self, provider_id: str) -> ProviderPlugin | None:
        """Get a plugin by provider ID."""
        return self._plugins.get(provider_id)

    def list_plugins(self) -> list[str]:
        """List all registered provider IDs."""
        return sorted(self._plugins.keys())

    def get_handlers(self) -> dict[str, Callable]:
        """Get handler functions for all plugins.

        Returns a dict mapping provider_id to async execute function,
        compatible with _get_provider_dispatchers() format.

        Returns:
            Dict of provider_id -> async handler function
        """
        handlers = {}
        for provider_id, plugin in self._plugins.items():
            handlers[provider_id] = self._create_handler(plugin)
        return handlers

    def _create_handler(self, plugin: ProviderPlugin) -> Callable:
        """Create a handler function for a plugin.

        The handler adapts the plugin's execute() method to the
        expected signature used by _dispatch_ask_provider.
        """

        async def handler(
            prompt: str,
            *,
            save_path: str | None = None,
            force_model: bool = False,
            model: str | None = None,
            timeout_seconds: float = 120.0,
            max_output_tokens: int = 0,
            response_format: str = "text",
            verbosity: str = "normal",
            stream: bool = False,
            output_mode: str = "clean",
            **kwargs,
        ) -> str:
            options = {
                "timeout_seconds": timeout_seconds,
                "max_output_tokens": max_output_tokens,
                "response_format": response_format,
                "verbosity": verbosity,
                "stream": stream,
            }
            return await plugin.execute(
                prompt=prompt,
                model=model,
                options=options,
                force_model=force_model,
                save_path=save_path,
                output_mode=output_mode,
                **kwargs,
            )

        return handler

    def build_registry(self, config: dict) -> ProviderRegistry:
        """Build a ProviderRegistry from loaded plugins.

        Args:
            config: Configuration dict (used for additional provider settings)

        Returns:
            ProviderRegistry with all loaded plugins
        """
        registry = ProviderRegistry()
        commands_cfg = config.get("commands", {})

        for provider_id, plugin in self._plugins.items():
            caps = plugin.capabilities
            provider_caps = ProviderCapabilities(
                supports_json=caps.supports_json,
                supports_stream=caps.supports_stream,
                supports_force_model=caps.supports_force_model,
            )
            spec = ProviderSpec(
                provider_id=provider_id,
                configured=plugin.is_configured(),
                capabilities=provider_caps,
            )
            registry.register(spec)

        return registry


def register_provider(cls: type[ProviderPlugin]) -> type[ProviderPlugin]:
    """Decorator to register a provider plugin.

    Usage:
        @register_provider
        class MyProvider(ProviderPlugin):
            ...

    Args:
        cls: ProviderPlugin subclass to register

    Returns:
        The same class (unchanged)
    """
    # Create instance and register
    plugin = cls()
    PluginLoader.instance().register(plugin)
    return cls
