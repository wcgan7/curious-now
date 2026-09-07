from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

# Published per-million rates, July 2026. Cached input bills at a fraction of
# the fresh rate, so it is tracked separately.
PRICING = {
    "gpt-5.6-sol": {"input": 5.00, "output": 30.00},
    "gpt-5.6-terra": {"input": 2.50, "output": 15.00},
    "gpt-5.6-luna": {"input": 1.00, "output": 6.00},
}
CACHED_INPUT_DISCOUNT = 0.10

DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_EFFORT = "high"

# Reader-facing generation is text transformation, not an agent task.  Keep
# every built-in capability that could inspect the host or delegate work out of
# the model's tool surface. The event parser below remains fail-closed for any
# new tool type a later CLI might add.
DISABLED_GENERATION_FEATURES = (
    "shell_tool",
    "unified_exec",
    "view_image",
    "computer_use",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "image_generation",
    "multi_agent",
    "multi_agent_v2",
    "workspace_dependencies",
)


# A model writing mathematics writes a great many backslashes, and sometimes
# escapes one too many: the Technical walkthrough of a quantum optimisation
# paper came back with ten literal "\\n" sequences where paragraph breaks
# belonged. The negative lookahead is what keeps this safe — every LaTeX command
# beginning with n continues in lower case (\\nabla, \\neq, \\nu, \\nonumber), so a
# backslash-n followed by anything else was never a command.
_ESCAPED_NEWLINE = re.compile(r"\\n(?![a-z])")


# Postgres text cannot hold a NUL, and a model that has read a PDF will
# occasionally hand one back. The call has already been paid for by then, so
# the row is lost at the very last step: five of one hundred and seventy-six
# stories in one run, every one of them a completed generation.
_UNSTORABLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def unescape_newlines(text: str) -> str:
    """Turn a literally written newline escape back into a newline."""

    return _ESCAPED_NEWLINE.sub("\n", text)


def storable(text: str) -> str:
    """Model text with the characters a text column cannot hold removed."""

    return _UNSTORABLE.sub("", text)


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0

    def cost(self, model: str) -> float:
        rates = PRICING.get(model)
        if not rates:
            return 0.0
        fresh = max(self.input_tokens - self.cached_input_tokens, 0)
        return (
            fresh * rates["input"]
            + self.cached_input_tokens * rates["input"] * CACHED_INPUT_DISCOUNT
            + self.output_tokens * rates["output"]
        ) / 1_000_000


@dataclass(frozen=True)
class Completion:
    payload: dict[str, Any] | None
    usage: Usage = field(default_factory=Usage)
    seconds: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.payload is not None


@dataclass(frozen=True)
class TextCompletion:
    """An unconstrained prose reply and the cost of producing it."""

    text: str | None
    usage: Usage = field(default_factory=Usage)
    seconds: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.text is not None and bool(self.text.strip())


class Generator(Protocol):
    """Whatever produces structured control data and unconstrained prose.

    Control-plane classifiers use schema-constrained JSON; reader-facing layers
    use plain text. Both retain usage and error information so swapping this for
    a direct API client does not touch their callers.
    """

    model: str

    def complete(
        self, prompt: str, schema: dict[str, Any], *, timeout: float = 900
    ) -> Completion: ...

    def complete_text(self, prompt: str, *, timeout: float = 900) -> TextCompletion: ...


@dataclass
class CodexGenerator:
    """Runs prompts through the Codex CLI, which carries existing auth.

    Codex is an agent harness, so every call pays for its system prompt —
    around 12,000 tokens before our own. That is acceptable for evaluating and
    for a first pass; a production pipeline should call the API directly, and
    batch, since this work is entirely asynchronous.
    """

    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT

    @staticmethod
    def _events(stdout: str) -> tuple[Usage, tuple[str, ...]]:
        """Read usage and record any agent tool activity.

        Generation prompts contain third-party text.  A prose or extraction
        call has no legitimate reason to inspect the machine, so any tool call
        makes the result unusable even when the CLI eventually writes output.
        """

        usage = Usage()
        tools: list[str] = []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            if "usage" in event:
                raw = event["usage"]
                usage = Usage(
                    input_tokens=int(raw.get("input_tokens", 0)),
                    cached_input_tokens=int(raw.get("cached_input_tokens", 0)),
                    output_tokens=int(raw.get("output_tokens", 0)),
                )
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", ""))
            # Agent prose/reasoning is expected. Everything else is a tool or
            # harness action and fails closed, including types introduced by a
            # future CLI version that this code does not know by name.
            if item_type and item_type not in {"agent_message", "reasoning"}:
                tools.append(item_type)
        return usage, tuple(dict.fromkeys(tools))

    def _base_command(self, scratch: str) -> list[str]:
        """A source-isolated CLI invocation.

        Both shell implementations are disabled, the process runs from an
        empty directory without user/project instructions, and the read-only
        sandbox remains as defence in depth. Any other observed tool activity
        is rejected rather than published.
        """

        command = [
            "codex",
            "exec",
            "-m",
            self.model,
            "-c",
            f'model_reasoning_effort="{self.effort}"',
            "-c",
            'web_search="disabled"',
        ]
        for feature in DISABLED_GENERATION_FEATURES:
            command.extend(["--disable", feature])
        command.extend(
            [
                "--sandbox",
                "read-only",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--skip-git-repo-check",
                "-C",
                scratch,
            ]
        )
        return command

    def complete(
        self, prompt: str, schema: dict[str, Any], *, timeout: float = 900
    ) -> Completion:
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as scratch:
            schema_path = Path(scratch) / "schema.json"
            output_path = Path(scratch) / "out.json"
            schema_path.write_text(json.dumps(schema))
            try:
                completed = subprocess.run(
                    [
                        *self._base_command(scratch),
                        "--output-schema", str(schema_path),
                        "-o", str(output_path),
                        "--json",
                        "-",
                    ],
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=scratch,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                return Completion(
                    None,
                    seconds=time.monotonic() - started,
                    error=f"{type(exc).__name__}: {exc}",
                )

            usage, tools = self._events(completed.stdout)

            seconds = time.monotonic() - started
            if completed.returncode != 0:
                return Completion(
                    None,
                    usage=usage,
                    seconds=seconds,
                    error=(
                        completed.stderr.strip()
                        or f"codex exited with status {completed.returncode}"
                    )[:400],
                )
            if tools:
                return Completion(
                    None,
                    usage=usage,
                    seconds=seconds,
                    error=f"untrusted source triggered tool activity: {', '.join(tools)}",
                )
            if not output_path.exists():
                return Completion(
                    None,
                    usage=usage,
                    seconds=seconds,
                    error=(completed.stderr or "no output written")[:400],
                )
            try:
                return Completion(
                    json.loads(output_path.read_text()), usage=usage, seconds=seconds
                )
            except ValueError as exc:
                return Completion(
                    None, usage=usage, seconds=seconds, error=f"unparseable: {exc}"
                )

    def complete_text(self, prompt: str, *, timeout: float = 900) -> TextCompletion:
        """Run the prompt as prose, without turning the answer into a form.

        Reader-facing generation is deliberately separate from `complete`.
        The three depth prompts were evaluated as ordinary prose requests;
        applying an output schema would change that objective back into field
        filling, which is the behaviour the direct pipeline is removing.
        """

        started = time.monotonic()
        with tempfile.TemporaryDirectory() as scratch:
            output_path = Path(scratch) / "out.txt"
            try:
                completed = subprocess.run(
                    [
                        *self._base_command(scratch),
                        "-o",
                        str(output_path),
                        "--json",
                        "-",
                    ],
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=scratch,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                return TextCompletion(
                    None,
                    seconds=time.monotonic() - started,
                    error=f"{type(exc).__name__}: {exc}",
                )

            usage, tools = self._events(completed.stdout)

            seconds = time.monotonic() - started
            if completed.returncode != 0:
                return TextCompletion(
                    None,
                    usage=usage,
                    seconds=seconds,
                    error=(
                        completed.stderr.strip()
                        or f"codex exited with status {completed.returncode}"
                    )[:400],
                )
            if tools:
                return TextCompletion(
                    None,
                    usage=usage,
                    seconds=seconds,
                    error=f"untrusted source triggered tool activity: {', '.join(tools)}",
                )
            if not output_path.exists():
                return TextCompletion(
                    None,
                    usage=usage,
                    seconds=seconds,
                    error=(completed.stderr or "no output written")[:400],
                )
            text = output_path.read_text().strip()
            if not text:
                return TextCompletion(
                    None,
                    usage=usage,
                    seconds=seconds,
                    error="empty output",
                )
            return TextCompletion(text, usage=usage, seconds=seconds)
