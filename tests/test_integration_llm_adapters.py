"""Integration tests for LLM adapters.

These tests verify that the LLM adapters work correctly with real CLI tools.
Requires: claude CLI and/or codex CLI to be installed and configured.
"""

from __future__ import annotations

import pytest

from curious_now.ai.llm_adapter import (
    ClaudeCLIAdapter,
    CodexCLIAdapter,
    LLMAdapter,
    LLMResponse,
    MockAdapter,
    OllamaAdapter,
    get_llm_adapter,
    list_available_adapters,
)
from curious_now.settings import clear_settings_cache


class TestMockAdapter:
    """Test MockAdapter (always available)."""

    def test_is_available(self) -> None:
        adapter = MockAdapter()
        assert adapter.is_available() is True

    def test_name(self) -> None:
        adapter = MockAdapter()
        assert adapter.name == "mock"

    def test_complete_returns_response(self) -> None:
        adapter = MockAdapter()
        response = adapter.complete("Hello world")

        assert isinstance(response, LLMResponse)
        assert response.success is True
        assert response.adapter == "mock"
        assert response.model == "mock"
        assert "Hello world" in response.text or "Mock" in response.text

    def test_complete_with_predefined_responses(self) -> None:
        adapter = MockAdapter(responses={"quantum": "Quantum mechanics is fascinating"})
        response = adapter.complete("Tell me about quantum physics")

        assert response.success is True
        assert "Quantum mechanics is fascinating" in response.text

    def test_complete_json(self) -> None:
        adapter = MockAdapter(responses={"json": '{"key": "value"}'})
        result = adapter.complete_json("Return json data")

        assert result == {"key": "value"}


class TestClaudeCLIAdapter:
    """Test ClaudeCLIAdapter with real claude CLI."""

    @pytest.fixture
    def adapter(self) -> ClaudeCLIAdapter:
        return ClaudeCLIAdapter()

    def test_name(self, adapter: ClaudeCLIAdapter) -> None:
        assert adapter.name == "claude-cli"

    def test_is_available(self, adapter: ClaudeCLIAdapter) -> None:
        """Test that claude CLI is available in this environment."""
        available = adapter.is_available()
        if not available:
            pytest.skip("Claude CLI not available in this environment")
        assert available is True

    def test_complete_simple_prompt(self, adapter: ClaudeCLIAdapter) -> None:
        """Test a simple completion with claude CLI."""
        if not adapter.is_available():
            pytest.skip("Claude CLI not available")

        response = adapter.complete(
            "What is 2 + 2? Reply with just the number.",
            max_tokens=50,
        )

        assert isinstance(response, LLMResponse)
        assert response.adapter == "claude-cli"
        if response.success:
            assert "4" in response.text
        else:
            # CLI might not be configured, check error is meaningful
            assert response.error is not None

    def test_complete_with_system_prompt(self, adapter: ClaudeCLIAdapter) -> None:
        """Test completion with system prompt."""
        if not adapter.is_available():
            pytest.skip("Claude CLI not available")

        response = adapter.complete(
            "What color is the sky?",
            system_prompt="You are a helpful assistant. Be very brief.",
            max_tokens=100,
        )

        assert isinstance(response, LLMResponse)
        assert response.adapter == "claude-cli"


class TestCodexCLIAdapter:
    """Test CodexCLIAdapter with real codex/openai CLI."""

    @pytest.fixture
    def adapter(self) -> CodexCLIAdapter:
        return CodexCLIAdapter()

    def test_name(self, adapter: CodexCLIAdapter) -> None:
        assert adapter.name == "codex-cli"

    def test_is_available(self, adapter: CodexCLIAdapter) -> None:
        """Test that codex/openai CLI is available in this environment."""
        available = adapter.is_available()
        if not available:
            pytest.skip("Codex/OpenAI CLI not available in this environment")
        assert available is True

    def test_complete_simple_prompt(self, adapter: CodexCLIAdapter) -> None:
        """Test a simple completion with codex CLI."""
        if not adapter.is_available():
            pytest.skip("Codex CLI not available")

        response = adapter.complete(
            "What is 3 + 3? Reply with just the number.",
            max_tokens=50,
        )

        assert isinstance(response, LLMResponse)
        assert response.adapter == "codex-cli"
        if response.success:
            assert "6" in response.text
        else:
            # CLI might not be configured, check error is meaningful
            assert response.error is not None


class TestOllamaAdapter:
    """Test OllamaAdapter."""

    @pytest.fixture
    def adapter(self) -> OllamaAdapter:
        return OllamaAdapter()

    def test_name(self, adapter: OllamaAdapter) -> None:
        assert adapter.name == "ollama"

    def test_is_available(self, adapter: OllamaAdapter) -> None:
        """Test ollama availability check."""
        # Just verify the method runs without error
        available = adapter.is_available()
        assert isinstance(available, bool)

    def test_complete_when_available(self, adapter: OllamaAdapter) -> None:
        """Test completion if ollama is available."""
        if not adapter.is_available():
            pytest.skip("Ollama not available in this environment")

        response = adapter.complete(
            "Say hello",
            max_tokens=50,
        )

        assert isinstance(response, LLMResponse)
        assert response.adapter == "ollama"


class TestGetLLMAdapter:
    """Test the factory function."""

    def setup_method(self) -> None:
        """Clear settings cache before each test."""
        clear_settings_cache()

    def test_get_mock_adapter(self) -> None:
        """Test getting mock adapter explicitly."""
        adapter = get_llm_adapter("mock")
        assert isinstance(adapter, MockAdapter)
        assert adapter.name == "mock"

    def test_get_claude_adapter(self) -> None:
        """Test getting claude adapter."""
        adapter = get_llm_adapter("claude-cli")
        # If claude is available, should return ClaudeCLIAdapter
        # Otherwise falls back to MockAdapter
        assert isinstance(adapter, LLMAdapter)
        if isinstance(adapter, ClaudeCLIAdapter):
            assert adapter.name == "claude-cli"
        else:
            assert isinstance(adapter, MockAdapter)

    def test_get_codex_adapter(self) -> None:
        """Test getting codex adapter."""
        adapter = get_llm_adapter("codex-cli")
        assert isinstance(adapter, LLMAdapter)
        if isinstance(adapter, CodexCLIAdapter):
            assert adapter.name == "codex-cli"
        else:
            assert isinstance(adapter, MockAdapter)

    def test_get_ollama_adapter(self) -> None:
        """Test getting ollama adapter."""
        adapter = get_llm_adapter("ollama")
        assert isinstance(adapter, LLMAdapter)
        if isinstance(adapter, OllamaAdapter):
            assert adapter.name == "ollama"
        else:
            assert isinstance(adapter, MockAdapter)

    def test_unknown_adapter_raises_error(self) -> None:
        """Test that unknown adapter type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown LLM adapter type"):
            get_llm_adapter("unknown-adapter")

    def test_factory_uses_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that factory reads from settings when no type specified."""
        clear_settings_cache()
        monkeypatch.setenv("CN_DATABASE_URL", "postgresql://test")
        monkeypatch.setenv("CN_LLM_ADAPTER", "mock")

        adapter = get_llm_adapter()
        assert isinstance(adapter, MockAdapter)


class TestListAvailableAdapters:
    """Test listing available adapters."""

    def test_list_includes_mock(self) -> None:
        """Mock adapter should always be available."""
        available = list_available_adapters()
        assert "mock" in available

    def test_list_returns_list(self) -> None:
        """Should return a list of strings."""
        available = list_available_adapters()
        assert isinstance(available, list)
        assert all(isinstance(name, str) for name in available)


class TestLLMResponseDataclass:
    """Test the LLMResponse dataclass."""

    def test_create_success_response(self) -> None:
        response = LLMResponse(
            text="Hello world",
            model="test-model",
            adapter="test-adapter",
            success=True,
        )
        assert response.text == "Hello world"
        assert response.model == "test-model"
        assert response.adapter == "test-adapter"
        assert response.success is True
        assert response.error is None

    def test_create_failure_response(self) -> None:
        response = LLMResponse.failure("test-adapter", "Something went wrong")
        assert response.text == ""
        assert response.model == "unknown"
        assert response.adapter == "test-adapter"
        assert response.success is False
        assert response.error == "Something went wrong"

    def test_response_is_frozen(self) -> None:
        """LLMResponse should be immutable."""
        response = LLMResponse(
            text="test",
            model="model",
            adapter="adapter",
        )
        with pytest.raises(AttributeError):
            response.text = "modified"  # type: ignore[misc]
