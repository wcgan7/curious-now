from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from curious_now_v2.generation.client import (
    DISABLED_GENERATION_FEATURES,
    CodexGenerator,
)


def _write_output(args: list[str], text: str) -> None:
    output = Path(args[args.index("-o") + 1])
    output.write_text(text)


def test_plain_text_rejects_nonzero_exit_even_if_output_was_written(
    monkeypatch: Any,
) -> None:
    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        _write_output(args, "partial answer")
        return subprocess.CompletedProcess(args, 9, stdout="", stderr="provider failed")

    monkeypatch.setattr(subprocess, "run", run)

    result = CodexGenerator().complete_text("Summarise this")

    assert not result.ok
    assert result.error == "provider failed"


def test_plain_text_runs_outside_the_repo_and_rejects_agent_tool_use(
    monkeypatch: Any,
) -> None:
    observed: dict[str, Any] = {}

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["args"] = args
        observed["cwd"] = kwargs["cwd"]
        _write_output(args, "text obtained after inspecting files")
        stdout = json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "command_execution", "command": "find .."},
            }
        )
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", run)

    result = CodexGenerator().complete_text("Untrusted source")

    assert not result.ok
    assert result.error == "untrusted source triggered tool activity: command_execution"
    assert observed["args"].count("--disable") == len(DISABLED_GENERATION_FEATURES)
    assert set(DISABLED_GENERATION_FEATURES) <= set(observed["args"])
    assert "--ignore-user-config" in observed["args"]
    assert "--ignore-rules" in observed["args"]
    assert observed["args"][observed["args"].index("-C") + 1] == observed["cwd"]


def test_event_filter_fails_closed_for_a_future_tool_type() -> None:
    stdout = json.dumps(
        {"type": "item.completed", "item": {"type": "future_file_reader"}}
    )

    _, tools = CodexGenerator._events(stdout)

    assert tools == ("future_file_reader",)
