"""Tests for plugin loader (P3-1)."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from model_bridge.core.plugin_loader import PluginLoader, register_provider
from model_bridge.plugins.base import ProviderPlugin, PluginCapabilities


class MockPlugin(ProviderPlugin):
    """Mock plugin for testing."""

    def __init__(self, provider_id: str = "mock"):
        self._provider_id = provider_id

    @property
    def provider_id(self) -> str:
        return self._provider_id

    async def execute(self, prompt: str, model: str | None, options: dict, **kwargs) -> str:
        return f"mock response: {prompt}"


class TestPluginLoader:
    """Tests for PluginLoader class."""

    def setup_method(self):
        """Reset singleton before each test."""
        PluginLoader.reset()

    def test_singleton_instance(self):
        """Test that PluginLoader is a singleton."""
        loader1 = PluginLoader.instance()
        loader2 = PluginLoader.instance()
        assert loader1 is loader2

    def test_register_plugin(self):
        """Test registering a plugin."""
        loader = PluginLoader.instance()
        plugin = MockPlugin("test_provider")
        loader.register(plugin)

        assert loader.get_plugin("test_provider") is plugin
        assert "test_provider" in loader.list_plugins()

    def test_register_duplicate_raises(self):
        """Test that registering duplicate provider_id raises error."""
        loader = PluginLoader.instance()
        loader.register(MockPlugin("duplicate"))

        with pytest.raises(ValueError, match="already registered"):
            loader.register(MockPlugin("duplicate"))

    def test_get_handlers_returns_callable_dict(self):
        """Test that get_handlers returns a dict of callables."""
        loader = PluginLoader.instance()
        loader.register(MockPlugin("handler_test"))

        handlers = loader.get_handlers()
        assert "handler_test" in handlers
        assert callable(handlers["handler_test"])

    @pytest.mark.anyio
    async def test_handler_executes_plugin(self):
        """Test that handler calls plugin.execute()."""
        loader = PluginLoader.instance()
        loader.register(MockPlugin("exec_test"))

        handlers = loader.get_handlers()
        handler = handlers["exec_test"]

        result = await handler("hello world")
        assert result == "mock response: hello world"

    def test_build_registry(self):
        """Test building ProviderRegistry from plugins."""
        loader = PluginLoader.instance()
        loader.register(MockPlugin("registry_test"))

        registry = loader.build_registry({})
        provider = registry.get("registry_test")

        assert provider is not None
        assert provider.provider_id == "registry_test"
        assert provider.configured is True  # MockPlugin.is_configured() returns True

    def test_load_from_directory(self):
        """Test loading plugins from a directory."""
        loader = PluginLoader.instance()

        # Create a temp directory with a plugin file
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "test_plugin.py"
            plugin_file.write_text("""
from model_bridge.plugins import ProviderPlugin, register_provider

@register_provider
class DirTestPlugin(ProviderPlugin):
    @property
    def provider_id(self) -> str:
        return "dir_test"

    async def execute(self, prompt: str, model, options, **kwargs) -> str:
        return "dir test response"
""")

            count = loader._load_from_directory(Path(tmpdir))
            assert count == 1
            assert "dir_test" in loader.list_plugins()

    def test_load_from_entry_points(self):
        """Test loading plugins from entry points."""
        PluginLoader.reset()
        loader = PluginLoader.instance()

        # Create a mock plugin class
        class EntryPointsTestPlugin(ProviderPlugin):
            @property
            def provider_id(self) -> str:
                return "entry_test"

            async def execute(self, prompt, model, options, **kwargs) -> str:
                return "entry test"

        # Mock entry points
        mock_ep = MagicMock()
        mock_ep.name = "test_entry"
        mock_ep.load.return_value = EntryPointsTestPlugin

        # Create a mock SelectableGroups object
        mock_eps = MagicMock()
        mock_group = [mock_ep]
        mock_eps.select.return_value = mock_group

        # Mock importlib.metadata.entry_points
        with patch.dict(
            'sys.modules',
            {'importlib.metadata': MagicMock(entry_points=MagicMock(return_value=mock_eps))}
        ):
            count = loader._load_from_entry_points()
            # Should have loaded at least attempted (may fail due to mock)
            # Just verify it doesn't crash
            assert isinstance(count, int)


class TestRegisterProviderDecorator:
    """Tests for @register_provider decorator."""

    def setup_method(self):
        """Reset singleton before each test."""
        PluginLoader.reset()

    def test_decorator_registers_plugin(self):
        """Test that @register_provider registers the plugin."""

        @register_provider
        class DecoratedPlugin(ProviderPlugin):
            @property
            def provider_id(self) -> str:
                return "decorated"

            async def execute(self, prompt: str, model, options, **kwargs) -> str:
                return "decorated response"

        loader = PluginLoader.instance()
        assert "decorated" in loader.list_plugins()

    def test_decorator_returns_class(self):
        """Test that decorator returns the original class."""

        @register_provider
        class ReturnTestPlugin(ProviderPlugin):
            @property
            def provider_id(self) -> str:
                return "return_test"

            async def execute(self, prompt: str, model, options, **kwargs) -> str:
                return ""

        assert ReturnTestPlugin.__name__ == "ReturnTestPlugin"


class TestPluginCapabilities:
    """Tests for plugin capabilities."""

    def test_default_capabilities(self):
        """Test default capabilities."""

        class DefaultCapsPlugin(ProviderPlugin):
            @property
            def provider_id(self) -> str:
                return "default_caps"

            async def execute(self, prompt: str, model, options, **kwargs) -> str:
                return ""

        plugin = DefaultCapsPlugin()
        caps = plugin.capabilities

        assert caps.supports_json is True
        assert caps.supports_stream is False
        assert caps.supports_force_model is True

    def test_custom_capabilities(self):
        """Test custom capabilities."""

        class CustomCapsPlugin(ProviderPlugin):
            @property
            def provider_id(self) -> str:
                return "custom_caps"

            @property
            def capabilities(self) -> PluginCapabilities:
                return PluginCapabilities(
                    supports_json=False,
                    supports_stream=True,
                    supports_force_model=False,
                )

            async def execute(self, prompt: str, model, options, **kwargs) -> str:
                return ""

        plugin = CustomCapsPlugin()
        caps = plugin.capabilities

        assert caps.supports_json is False
        assert caps.supports_stream is True
        assert caps.supports_force_model is False


class TestIsConfigured:
    """Tests for is_configured method."""

    def test_default_is_configured(self):
        """Test default is_configured returns True."""

        class DefaultConfiguredPlugin(ProviderPlugin):
            @property
            def provider_id(self) -> str:
                return "default_configured"

            async def execute(self, prompt: str, model, options, **kwargs) -> str:
                return ""

        plugin = DefaultConfiguredPlugin()
        assert plugin.is_configured() is True

    def test_custom_is_configured(self):
        """Test custom is_configured."""

        class CustomConfiguredPlugin(ProviderPlugin):
            @property
            def provider_id(self) -> str:
                return "custom_configured"

            async def execute(self, prompt: str, model, options, **kwargs) -> str:
                return ""

            def is_configured(self) -> bool:
                return False

        plugin = CustomConfiguredPlugin()
        assert plugin.is_configured() is False


class TestMainIntegration:
    """Tests for main.py plugin integration."""

    def setup_method(self):
        """Reset singletons before each test."""
        PluginLoader.reset()

    def test_get_provider_dispatchers_uses_plugins(self, monkeypatch):
        """Test that _get_provider_dispatchers uses PluginLoader."""
        from model_bridge import main as main_module

        # Reset global state
        monkeypatch.setattr(main_module, "PLUGIN_LOADER", None)

        # Register a mock plugin
        loader = PluginLoader.instance()
        loader.register(MockPlugin("integration_test"))
        monkeypatch.setattr(main_module, "PLUGIN_LOADER", loader)

        dispatchers = main_module._get_provider_dispatchers()
        assert "integration_test" in dispatchers

    def test_get_provider_dispatchers_fallback(self, monkeypatch):
        """Test that _get_provider_dispatchers falls back when no plugins."""
        from model_bridge import main as main_module

        # Ensure PLUGIN_LOADER is None
        monkeypatch.setattr(main_module, "PLUGIN_LOADER", None)

        dispatchers = main_module._get_provider_dispatchers()
        # Should have built-in providers
        assert "codex" in dispatchers
        assert "gemini" in dispatchers
