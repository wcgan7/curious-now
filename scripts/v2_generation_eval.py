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


# Published per-million rates, July 2026. Cached input bills at a fraction of
# the fresh rate, so it is tracked separately: token totals alone say nothing
# about cost when the tiers are priced 2.5x apart.
# The shapes the contract treats differently: a dense paper, a lab release
# with no mechanism, ordinary journalism, and evidence too thin to explain.
DEFAULT_SOURCES = [
    "arXiv AI",
    "Google DeepMind",
    "BBC Science & Environment",
    "medRxiv",
]

PRICING = {
    "gpt-5.6-sol": {"input": 5.00, "output": 30.00},
    "gpt-5.6-terra": {"input": 2.50, "output": 15.00},
    "gpt-5.6-luna": {"input": 1.00, "output": 6.00},
}
CACHED_INPUT_DISCOUNT = 0.10


@dataclass
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

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


@dataclass
class Result:
    model: str
    story: str
    seconds: float
    tokens: int
    payload: dict[str, object] | None
    error: str | None = None
    checks: dict[str, bool] = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)
    separation: dict[str, float] = field(default_factory=dict)


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
                "--json",
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

    usage = Usage()
    for line in completed.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or "usage" not in event:
            continue
        raw = event["usage"]
        usage = Usage(
            input_tokens=int(raw.get("input_tokens", 0)),
            cached_input_tokens=int(raw.get("cached_input_tokens", 0)),
            output_tokens=int(raw.get("output_tokens", 0)),
            reasoning_tokens=int(raw.get("reasoning_output_tokens", 0)),
        )

    if not out.exists():
        return Result(model, tag, seconds, usage.total, None, "no output written", usage=usage)
    try:
        payload = json.loads(out.read_text())
    except ValueError as exc:
        return Result(model, tag, seconds, usage.total, None, f"unparseable: {exc}", usage=usage)
    return Result(model, tag, seconds, usage.total, payload, usage=usage)


def words(value: object) -> int:
    return len(str(value or "").split())


_STOPWORDS = frozenset(
    """the a an and or but of to in on for with by from as at is are was were be
    been it its this that these those which who whom what when where how why not
    no can could may might will would should has have had do does did than then
    so such more most other some any each both all one two into over under""".split()
)


def _content_words(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z][a-z-]{2,}", text.casefold())
        if word not in _STOPWORDS
    }


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) > 5]


def ladder_separation(glance: str, explain: str) -> dict[str, float]:
    """Whether Explain adds resolution or just restates Glance at length.

    The ladder only works if each layer answers its own question. An Explain
    that reuses Glance's sentences is the "expanded abstract" the contract
    prohibits, and it is invisible unless measured.
    """

    if not glance.strip() or not explain.strip():
        return {}
    glance_sentences = set(_sentences(glance))
    reused = sum(1 for s in _sentences(explain) if s in glance_sentences)
    glance_vocab = _content_words(glance)
    explain_vocab = _content_words(explain)
    new = explain_vocab - glance_vocab
    return {
        "verbatim_sentences_reused": float(reused),
        "new_vocabulary_ratio": round(len(new) / max(len(explain_vocab), 1), 3),
        "length_multiple": round(words(explain) / max(words(glance), 1), 2),
    }


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
    if explain.get("mechanism_supported"):
        separation = ladder_separation(
            str(glance.get("text") or ""), str(explain.get("text") or "")
        )
        result.separation = separation
        if separation:
            # Explain must go deeper, not longer: no lifted sentences, and a
            # majority of its vocabulary should be new.
            result.checks["explain_reuses_no_glance_sentences"] = (
                separation["verbatim_sentences_reused"] == 0
            )
            result.checks["explain_adds_new_vocabulary"] = (
                separation["new_vocabulary_ratio"] >= 0.5
            )

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
        "--sources",
        default="",
        help="pipe-separated source names to evaluate, in order",
    )
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
    wanted = args.sources.split("|") if args.sources else DEFAULT_SOURCES
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

    print(
        f"\n{'model':16s} {'story':22s} {'sec':>6s} {'in':>7s} {'out':>6s} "
        f"{'US$':>8s}  checks"
    )
    for result in results:
        passed = sum(1 for value in result.checks.values() if value)
        total = len(result.checks)
        failed = [name for name, value in result.checks.items() if not value]
        note = result.error or (f"{passed}/{total}" + (f"  FAILED: {', '.join(failed)}" if failed else ""))
        print(
            f"{result.model:16s} {result.story.split('-', 2)[-1][:22]:22s} "
            f"{result.seconds:6.1f} {result.usage.input_tokens:7,d} "
            f"{result.usage.output_tokens:6,d} "
            f"{result.usage.cost(result.model):8.4f}  {note}"
        )

    for model in args.models.split(","):
        rows = [r for r in results if r.model == model and r.payload]
        if not rows:
            continue
        total_cost = sum(r.usage.cost(model) for r in rows)
        print(
            f"\n{model}: mean {sum(r.seconds for r in rows)/len(rows):.1f}s, "
            f"mean {sum(r.tokens for r in rows)//len(rows):,} tokens, "
            f"US${total_cost/len(rows):.4f}/story "
            f"(US${total_cost/len(rows)*2000:.2f} per 2,000 stories), "
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
                    "input_tokens": r.usage.input_tokens,
                    "cached_input_tokens": r.usage.cached_input_tokens,
                    "output_tokens": r.usage.output_tokens,
                    "reasoning_tokens": r.usage.reasoning_tokens,
                    "cost_usd": round(r.usage.cost(r.model), 5),
                    "checks": r.checks,
                    "separation": r.separation,
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
