"""LLM Adapter abstraction layer.

This module provides a unified interface for interacting with LLMs
through CLI tools, avoiding expensive API calls.

Supported adapters:
- codex: OpenAI Codex CLI
- claude: Claude CLI (Anthropic)
- ollama: Ollama local LLM runner

Usage:
    from curious_now.ai import get_llm_adapter

    adapter = get_llm_adapter()
    response = adapter.complete("Explain quantum computing in simple terms")
    print(response.text)
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from curious_now.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMResponse:
    """Response from an LLM completion request."""

    text: str
    model: str
    adapter: str
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def failure(adapter: str, error: str) -> LLMResponse:
        """Create a failure response."""
        return LLMResponse(
            text="",
            model="unknown",
            adapter=adapter,
            success=False,
            error=error,
        )


class LLMAdapter(ABC):
    """Abstract base class for LLM adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the adapter name."""
        pass

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Generate a completion for the given prompt.

        Args:
            prompt: The user prompt to complete
            system_prompt: Optional system prompt for context
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)

        Returns:
            LLMResponse with the completion text
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this adapter is available (CLI installed, etc.)."""
        pass

    def complete_json(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
    ) -> dict[str, Any] | None:
        """
        Generate a completion and parse as JSON.

        Args:
            prompt: The user prompt (should request JSON output)
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response

        Returns:
            Parsed JSON dict, or None if parsing fails
        """
        response = self.complete(
            prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=0.3,  # Lower temperature for structured output
        )

        if not response.success:
            logger.warning("LLM completion failed: %s", response.error)
            return None

        text = response.text.strip()

        # Try to extract JSON from response
        # Handle cases where LLM wraps JSON in markdown code blocks
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            logger.warning("LLM response is not a JSON object: %s", type(parsed))
            return None
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM response as JSON: %s", e)
            return None


class OllamaAdapter(LLMAdapter):
    """
    Adapter for Ollama local LLM runner.

    Ollama runs LLMs locally and provides a CLI interface.
    Install: https://ollama.ai

    Models: llama2, mistral, codellama, etc.
    """

    def __init__(self, model: str = "llama2") -> None:
        self.model = model

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        """Check if ollama CLI is available."""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate completion using ollama CLI."""
        try:
            # Build the full prompt
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            # Run ollama
            result = subprocess.run(
                [
                    "ollama",
                    "run",
                    self.model,
                    full_prompt,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                return LLMResponse.failure(
                    self.name,
                    f"Ollama error: {result.stderr}",
                )

            return LLMResponse(
                text=result.stdout.strip(),
                model=self.model,
                adapter=self.name,
                success=True,
            )

        except subprocess.TimeoutExpired:
            return LLMResponse.failure(self.name, "Ollama request timed out")
        except FileNotFoundError:
            return LLMResponse.failure(self.name, "Ollama CLI not found")
        except Exception as e:
            return LLMResponse.failure(self.name, str(e))


class ClaudeCLIAdapter(LLMAdapter):
    """
    Adapter for Claude CLI.

    Uses the Claude CLI tool for completions.
    Install: npm install -g @anthropic-ai/claude-cli
    Or: pip install claude-cli
    """

    def __init__(self, model: str = "claude-3-haiku-20240307") -> None:
        self.model = model

    @property
    def name(self) -> str:
        return "claude-cli"

    def is_available(self) -> bool:
        """Check if claude CLI is available."""
        try:
            # Try 'claude' command
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        try:
            # Try 'claude-cli' command
            result = subprocess.run(
                ["claude-cli", "--version"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _get_cli_command(self) -> str:
        """Determine which CLI command to use."""
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return "claude"
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return "claude-cli"

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate completion using Claude CLI."""
        try:
            cli_cmd = self._get_cli_command()

            # Write prompt to temp file for complex prompts
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                if system_prompt:
                    f.write(f"System: {system_prompt}\n\n")
                f.write(prompt)
                prompt_file = f.name

            try:
                # Build command
                cmd = [
                    cli_cmd,
                    "--print",  # Print response to stdout
                    "--model", self.model,
                ]

                # Read from file
                with open(prompt_file) as pf:
                    result = subprocess.run(
                        cmd,
                        stdin=pf,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
            finally:
                Path(prompt_file).unlink(missing_ok=True)

            if result.returncode != 0:
                return LLMResponse.failure(
                    self.name,
                    f"Claude CLI error: {result.stderr}",
                )

            return LLMResponse(
                text=result.stdout.strip(),
                model=self.model,
                adapter=self.name,
                success=True,
            )

        except subprocess.TimeoutExpired:
            return LLMResponse.failure(self.name, "Claude CLI request timed out")
        except FileNotFoundError:
            return LLMResponse.failure(self.name, "Claude CLI not found")
        except Exception as e:
            return LLMResponse.failure(self.name, str(e))


class CodexCLIAdapter(LLMAdapter):
    """
    Adapter for OpenAI-compatible CLI tools.

    This adapter supports various OpenAI CLI tools:
    - codex CLI (OpenAI Codex agent via 'codex exec' non-interactive mode)
    - openai CLI (official OpenAI CLI)
    - sgpt (shell-gpt - community tool)
    """

    def __init__(self, model: str = "gpt-3.5-turbo") -> None:
        self.model = model
        self._cli_cmd: str | None = None

    @property
    def name(self) -> str:
        return "codex-cli"

    def is_available(self) -> bool:
        """Check if any compatible CLI is available."""
        for cmd in ["codex", "openai", "sgpt"]:
            try:
                result = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    self._cli_cmd = cmd
                    return True
            except (subprocess.SubprocessError, FileNotFoundError):
                continue
        return False

    def _get_cli_command(self) -> str | None:
        """Determine which CLI command to use."""
        if self._cli_cmd:
            return self._cli_cmd

        for cmd in ["codex", "openai", "sgpt"]:
            try:
                result = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    self._cli_cmd = cmd
                    return cmd
            except (subprocess.SubprocessError, FileNotFoundError):
                continue
        return None

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate completion using OpenAI-compatible CLI."""
        cli_cmd = self._get_cli_command()
        if not cli_cmd:
            return LLMResponse.failure(self.name, "No compatible CLI found")

        try:
            if cli_cmd == "codex":
                return self._complete_codex(prompt, system_prompt)
            elif cli_cmd == "sgpt":
                return self._complete_sgpt(prompt, system_prompt, max_tokens)
            else:
                return self._complete_openai(
                    prompt, system_prompt, max_tokens, temperature
                )

        except subprocess.TimeoutExpired:
            return LLMResponse.failure(self.name, "Request timed out")
        except FileNotFoundError:
            return LLMResponse.failure(self.name, f"{cli_cmd} CLI not found")
        except Exception as e:
            return LLMResponse.failure(self.name, str(e))

    def _complete_codex(
        self,
        prompt: str,
        system_prompt: str | None,
    ) -> LLMResponse:
        """Use codex CLI in exec (non-interactive) mode."""
        import tempfile

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        # Use a temp file for output
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            output_file = f.name

        try:
            result = subprocess.run(
                [
                    "codex", "exec",
                    "--skip-git-repo-check",
                    "-o", output_file,
                    full_prompt,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                return LLMResponse.failure(
                    self.name, f"codex error: {result.stderr}"
                )

            # Read the output from file
            import os
            if os.path.exists(output_file):
                with open(output_file) as f:
                    output_text = f.read().strip()
                os.unlink(output_file)
            else:
                output_text = ""

            return LLMResponse(
                text=output_text,
                model="codex",
                adapter=self.name,
                success=True,
            )
        except Exception as e:
            # Clean up temp file on error
            import os
            if os.path.exists(output_file):
                os.unlink(output_file)
            raise e

    def _complete_sgpt(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int,
    ) -> LLMResponse:
        """Use shell-gpt CLI."""
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        result = subprocess.run(
            ["sgpt", full_prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            return LLMResponse.failure(self.name, f"sgpt error: {result.stderr}")

        return LLMResponse(
            text=result.stdout.strip(),
            model="gpt-3.5-turbo",  # sgpt default
            adapter=self.name,
            success=True,
        )

    def _complete_openai(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Use official OpenAI CLI."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Write messages to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(messages, f)
            messages_file = f.name

        try:
            result = subprocess.run(
                [
                    "openai",
                    "api",
                    "chat.completions.create",
                    "-m", self.model,
                    "-M", str(max_tokens),
                    "-t", str(temperature),
                    "--messages", f"@{messages_file}",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
        finally:
            Path(messages_file).unlink(missing_ok=True)

        if result.returncode != 0:
            return LLMResponse.failure(self.name, f"OpenAI CLI error: {result.stderr}")

        # Parse response
        try:
            response_data = json.loads(result.stdout)
            text = response_data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            return LLMResponse.failure(self.name, f"Failed to parse response: {e}")

        return LLMResponse(
            text=text.strip(),
            model=self.model,
            adapter=self.name,
            success=True,
        )

class MockAdapter(LLMAdapter):
    """
    Mock adapter for testing without actual LLM.

    Returns predefined responses or echo responses.
    """

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = responses or {}

    @property
    def name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Return mock response."""
        # Check for predefined response
        for key, response in self.responses.items():
            if key.lower() in prompt.lower():
                return LLMResponse(
                    text=response,
                    model="mock",
                    adapter=self.name,
                    success=True,
                )

        # Default: echo the prompt with a prefix
        return LLMResponse(
            text=f"[Mock LLM Response]\nPrompt: {prompt[:100]}...",
            model="mock",
            adapter=self.name,
            success=True,
            metadata={"echoed": True},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Factory function
# ─────────────────────────────────────────────────────────────────────────────


def get_llm_adapter(adapter_type: str | None = None) -> LLMAdapter:
    """
    Get the configured LLM adapter.

    Args:
        adapter_type: Override the configured adapter type.
                     Options: "ollama", "claude-cli", "codex-cli", "mock"

    Returns:
        Configured LLMAdapter instance

    Raises:
        ValueError: If adapter type is unknown or unavailable
    """
    settings = get_settings()

    # Determine adapter type
    if adapter_type is None:
        adapter_type = getattr(settings, "llm_adapter", "ollama")

    # Get model configuration
    llm_model = getattr(settings, "llm_model", None)

    # Create adapter
    adapter: LLMAdapter
    if adapter_type == "ollama":
        adapter = OllamaAdapter(model=llm_model or "llama2")
    elif adapter_type == "claude-cli":
        adapter = ClaudeCLIAdapter(model=llm_model or "claude-3-haiku-20240307")
    elif adapter_type == "codex-cli":
        adapter = CodexCLIAdapter(model=llm_model or "gpt-3.5-turbo")
    elif adapter_type == "mock":
        return MockAdapter()
    else:
        raise ValueError(f"Unknown LLM adapter type: {adapter_type}")

    # Check availability
    if not adapter.is_available():
        logger.warning(
            "LLM adapter '%s' is not available, falling back to mock",
            adapter_type,
        )
        return MockAdapter()

    return adapter


def list_available_adapters() -> list[str]:
    """List all available LLM adapters on this system."""
    available = []

    adapters = [
        ("ollama", OllamaAdapter()),
        ("claude-cli", ClaudeCLIAdapter()),
        ("codex-cli", CodexCLIAdapter()),
        ("mock", MockAdapter()),
    ]

    for name, adapter in adapters:
        if adapter.is_available():
            available.append(name)

    return available
