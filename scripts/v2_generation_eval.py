#!/usr/bin/env python
"""Compare candidate models on the job this product actually needs.

Generates a Glance and an Explain for real stories from the corpus, through
`codex exec`, and reports speed, cost, and how well each result obeys the
presentation contract.

    python scripts/v2_generation_eval.py --models gpt-5.6-luna,gpt-5.6-terra

A generic benchmark cannot answer the question that matters here: whether a
model explains grounded in the evidence it was given, and declines when the
evidence will not carry the layer. Both are measured against real retrieved
text, including a deliberately thin case where declining is the right answer.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

SCRATCH = Path(__file__).parents[1] / ".eval"
SCHEMA_PATH = SCRATCH / "schema.json"

# Asking for both layers in one call mirrors how the contract allows Title and
# Glance to be produced together, and keeps the comparison to one variable.
OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["display_title", "glance", "explain"],
    "properties": {
        "display_title": {"type": "string"},
        "glance": {
            "type": "object",
            "additionalProperties": False,
            "required": ["text", "qualification", "supported"],
            "properties": {
                "text": {"type": "string"},
                "qualification": {"type": "string"},
                "supported": {"type": "boolean"},
            },
        },
        "explain": {
            "type": "object",
            "additionalProperties": False,
            "required": ["text", "mechanism_supported", "declined_reason"],
            "properties": {
                "text": {"type": "string"},
                "mechanism_supported": {"type": "boolean"},
                "declined_reason": {"type": "string"},
            },
        },
    },
}

PROMPT = """You are writing for Curious Now, a calm feed of science worth \
understanding. Work ONLY from the SOURCE TEXT below. Do not use outside \
knowledge, and do not state anything the source does not support.

Produce three things.

1. display_title: 6-14 words, plain language, describing the actual \
development. No hype words, no unsupported superlatives, no manufactured \
question. Attribute the claim if it comes only from an interested party.

2. glance: for a reader new to the topic, about 120-200 words. State what \
happened, the simplest accurate mental model, and why it might matter. Put the \
single most interpretation-changing caveat in `qualification`. Set `supported` \
to false if the source cannot even support this.

3. explain: for a reader who knows the field, about 700-1200 words, answering \
ONE question: how does it work? Explain the mechanism and why it produces the \
claimed effect. Cover evidence and comparison only where the source supports \
them. Carry the qualification that keeps the mechanism honest.

If the source does not describe a mechanism, set mechanism_supported to false, \
put the reason in declined_reason, and leave explain.text empty. Declining is \
a correct answer and is preferred over writing something the source does not \
support.

SOURCE: {source_name} ({content_type})
TITLE: {title}

SOURCE TEXT:
{full_text}
"""


@dataclass
class Result:
    model: str
    story: str
    seconds: float
    tokens: int
    payload: dict[str, object] | None
    error: str | None = None
    checks: dict[str, bool] = field(default_factory=dict)


def run_model(model: str, effort: str, prompt: str, tag: str) -> Result:
    SCRATCH.mkdir(exist_ok=True)
    out = SCRATCH / f"{tag}.json"
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [
                "codex", "exec",
                "-m", model,
                "-c", f'model_reasoning_effort="{effort}"',
                "--sandbox", "read-only",
                "--ephemeral",
                "--skip-git-repo-check",
                "--output-schema", str(SCHEMA_PATH),
                "-o", str(out),
                "-",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except subprocess.TimeoutExpired:
        return Result(model, tag, time.monotonic() - started, 0, None, "timed out")

    seconds = time.monotonic() - started
    tokens = 0
    match = re.search(r"tokens used[:\s]+([\d,]+)", completed.stdout + completed.stderr)
    if match:
        tokens = int(match.group(1).replace(",", ""))

    if not out.exists():
        return Result(model, tag, seconds, tokens, None, "no output written")
    try:
        payload = json.loads(out.read_text())
    except ValueError as exc:
        return Result(model, tag, seconds, tokens, None, f"unparseable: {exc}")
    return Result(model, tag, seconds, tokens, payload)


def words(value: object) -> int:
    return len(str(value or "").split())


def check(result: Result, *, expect_mechanism: bool) -> None:
    """Score one result against the parts of the contract a machine can judge."""

    payload = result.payload
    if not payload:
        return
    glance = payload.get("glance") or {}
    explain = payload.get("explain") or {}
    title = str(payload.get("display_title") or "")

    hype = ("breakthrough", "revolutionary", "game-chang", "groundbreaking")
    result.checks = {
        "title_length_ok": 5 <= len(title.split()) <= 16,
        "title_no_hype": not any(word in title.casefold() for word in hype),
        "glance_length_ok": 80 <= words(glance.get("text")) <= 260,
        "glance_has_qualification": bool(str(glance.get("qualification") or "").strip()),
        "explain_declined_or_written": (
            bool(explain.get("mechanism_supported"))
            != bool(str(explain.get("declined_reason") or "").strip())
        ),
    }
    if expect_mechanism:
        # The gate judges whether there is enough *text* for Explain; only the
        # model can see whether the text describes a mechanism. A funding
        # announcement clears the word count and still has nothing to explain,
        # so a reasoned decline is a correct answer here, not a failure.
        if explain.get("mechanism_supported"):
            result.checks["explain_length_ok"] = (
                600 <= words(explain.get("text")) <= 1500
            )
        else:
            result.checks["explain_declined_with_reason"] = (
                len(str(explain.get("declined_reason") or "").split()) >= 8
            )
    else:
        # The thin case: the right answer is to decline, not to write anyway.
        result.checks["declined_thin_evidence"] = not explain.get(
            "mechanism_supported"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="gpt-5.6-luna,gpt-5.6-terra")
    parser.add_argument("--effort", default="high")
    parser.add_argument("--stories", type=int, default=4)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("/tmp/claude-1000/-home-gan-Documents-curious-now")
        / "27ad0ebc-321f-4577-a3e7-0f6a86854dd3/scratchpad/eval_stories.json",
    )
    args = parser.parse_args()

    SCRATCH.mkdir(exist_ok=True)
    SCHEMA_PATH.write_text(json.dumps(OUTPUT_SCHEMA))

    corpus = json.loads(args.input.read_text())
    # Cover the shapes the contract treats differently: a dense paper, a lab
    # release, ordinary journalism, and something too thin to explain.
    wanted = ["arXiv AI", "Google DeepMind", "BBC Science & Environment", "medRxiv"]
    chosen = [
        story
        for name in wanted[: args.stories]
        for story in corpus
        if story["source_name"] == name
    ]

    results: list[Result] = []
    for model in args.models.split(","):
        for story in chosen:
            expect = "explain" in story["supported_depths"]
            tag = f"{model}-{story['source_name'].replace(' ', '_')}"
            prompt = PROMPT.format(
                source_name=story["source_name"],
                content_type=story["content_type"],
                title=story["title"],
                full_text=story["full_text"],
            )
            print(f"  running {tag} ...", flush=True)
            result = run_model(model, args.effort, prompt, tag)
            check(result, expect_mechanism=expect)
            results.append(result)

    print(f"\n{'model':16s} {'story':28s} {'sec':>6s} {'tok':>7s}  checks")
    for result in results:
        passed = sum(1 for value in result.checks.values() if value)
        total = len(result.checks)
        failed = [name for name, value in result.checks.items() if not value]
        note = result.error or (f"{passed}/{total}" + (f"  FAILED: {', '.join(failed)}" if failed else ""))
        print(
            f"{result.model:16s} {result.story.split('-', 2)[-1][:28]:28s} "
            f"{result.seconds:6.1f} {result.tokens:7,d}  {note}"
        )

    for model in args.models.split(","):
        rows = [r for r in results if r.model == model and r.payload]
        if not rows:
            continue
        print(
            f"\n{model}: mean {sum(r.seconds for r in rows)/len(rows):.1f}s, "
            f"mean {sum(r.tokens for r in rows)//len(rows):,} tokens, "
            f"{sum(sum(1 for v in r.checks.values() if v) for r in rows)}"
            f"/{sum(len(r.checks) for r in rows)} checks passed"
        )

    (SCRATCH / "results.json").write_text(
        json.dumps(
            [
                {
                    "model": r.model,
                    "story": r.story,
                    "seconds": round(r.seconds, 2),
                    "tokens": r.tokens,
                    "checks": r.checks,
                    "error": r.error,
                    "payload": r.payload,
                }
                for r in results
            ],
            indent=1,
        )
    )
    print(f"\nfull outputs written to {SCRATCH / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
