from __future__ import annotations

import json
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


class Generator(Protocol):
    """Whatever produces structured output for a prompt.

    Narrow on purpose: the pipeline needs a schema-constrained JSON reply and
    the cost of getting it, nothing more. Swapping this for a direct API client
    should not touch anything that calls it.
    """

    model: str

    def complete(
        self, prompt: str, schema: dict[str, Any], *, timeout: float = 900
    ) -> Completion: ...


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
                        "codex", "exec",
                        "-m", self.model,
                        "-c", f'model_reasoning_effort="{self.effort}"',
                        "--sandbox", "read-only",
                        "--ephemeral",
                        "--skip-git-repo-check",
                        "--output-schema", str(schema_path),
                        "-o", str(output_path),
                        "--json",
                        "-",
                    ],
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                return Completion(
                    None,
                    seconds=time.monotonic() - started,
                    error=f"{type(exc).__name__}: {exc}",
                )

            usage = Usage()
            for line in completed.stdout.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict) and "usage" in event:
                    raw = event["usage"]
                    usage = Usage(
                        input_tokens=int(raw.get("input_tokens", 0)),
                        cached_input_tokens=int(raw.get("cached_input_tokens", 0)),
                        output_tokens=int(raw.get("output_tokens", 0)),
                    )

            seconds = time.monotonic() - started
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
