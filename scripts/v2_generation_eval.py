#!/usr/bin/env python
"""Compare candidate models on the job this product actually needs.

Runs the real generation pipeline — evidence packet, then presentation — over
stories from the corpus, and reports speed, cost, and how each model fares
against the contract the pipeline already enforces.

    PYTHONPATH=. python scripts/v2_generation_eval.py --models gpt-5.6-luna,gpt-5.6-terra

A generic benchmark cannot answer the question that matters here: whether a
model classifies what an item is, explains grounded in the evidence it was
given, and declines when the evidence will not carry the layer. All three are
measured against real retrieved text, including a deliberately thin case where
declining is the right answer.

The prompts and checks come from `curious_now_v2.generation`, deliberately. An
eval with its own copy of the prompt measures a pipeline nobody ships.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from curious_now_v2.generation.client import CodexGenerator
from curious_now_v2.generation.packet import ExtractedPacket, extract_packet
from curious_now_v2.generation.present import Presentation, generate_presentation

SCRATCH = Path(__file__).parents[1] / ".eval"

# The shapes the contract treats differently: a dense paper, a lab release with
# no mechanism, ordinary journalism, and evidence too thin to explain.
DEFAULT_SOURCES = [
    "arXiv AI",
    "Google DeepMind",
    "BBC Science & Environment",
    "medRxiv",
]


@dataclass
class Result:
    model: str
    story: str
    seconds: float
    cost: float
    packet: ExtractedPacket | None = None
    presentation: Presentation | None = None
    error: str | None = None
    checks: dict[str, bool] = field(default_factory=dict)
    separation: dict[str, float] = field(default_factory=dict)

    @property
    def tokens(self) -> tuple[int, int]:
        stages = [
            stage.completion.usage
            for stage in (self.packet, self.presentation)
            if stage is not None
        ]
        return (
            sum(usage.input_tokens for usage in stages),
            sum(usage.output_tokens for usage in stages),
        )


def words(value: str) -> int:
    return len(value.split())


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


def run_story(
    model: str, effort: str, story: dict[str, str], *, expect_mechanism: bool
) -> Result:
    """Put one story through both stages, exactly as the pipeline does."""

    generator = CodexGenerator(model=model, effort=effort)
    started = time.monotonic()
    tag = story["source_name"]

    packet = extract_packet(
        generator,
        source_name=story["source_name"],
        content_type=story["content_type"],
        title=story["title"],
        text=story["full_text"],
    )
    cost = packet.completion.usage.cost(model)
    if not packet.completion.ok:
        return Result(
            model, tag, time.monotonic() - started, cost,
            packet=packet, error=packet.completion.error,
        )

    result = Result(model, tag, 0.0, cost, packet=packet)
    result.checks["packet_usable"] = packet.usable
    # Every claim carries a verbatim excerpt or it is dropped in extraction, so
    # a model that invents evidence shows up as claims lost, not as claims kept.
    result.checks["packet_kept_claims"] = len(packet.claims) >= 3

    if not packet.usable:
        result.seconds = time.monotonic() - started
        return result

    if not packet.worth_publishing:
        # Withholding is a real outcome, not a failure: the pipeline stops here
        # and never spends a second call. Whether it was right is a judgement
        # for the reader of this report.
        result.checks["withheld_before_second_call"] = True
        result.seconds = time.monotonic() - started
        return result

    presentation = generate_presentation(
        generator,
        packet,
        source_name=story["source_name"],
        content_type=story["content_type"],
        text=story["full_text"],
    )
    result.presentation = presentation
    result.cost = cost + presentation.completion.usage.cost(model)
    result.seconds = time.monotonic() - started
    if not presentation.completion.ok:
        result.error = presentation.completion.error
        return result

    # The validator the pipeline runs is the check that matters; anything it
    # rejects would never reach a reader.
    result.checks["contract_clean"] = not presentation.violations

    if presentation.explain_supported:
        result.separation = ladder_separation(presentation.glance, presentation.explain)
        if result.separation:
            # Explain must go deeper, not longer: no lifted sentences, and a
            # majority of its vocabulary should be new.
            result.checks["explain_reuses_no_glance_sentences"] = (
                result.separation["verbatim_sentences_reused"] == 0
            )
            result.checks["explain_adds_new_vocabulary"] = (
                result.separation["new_vocabulary_ratio"] >= 0.5
            )

    if expect_mechanism:
        # The gate judges whether there is enough *text* for Explain; only the
        # model can see whether the text describes a mechanism. A funding
        # announcement clears the word count and still has nothing to explain,
        # so a reasoned decline is a correct answer here, not a failure.
        if not presentation.explain_supported:
            result.checks["explain_declined_with_reason"] = (
                len(presentation.explain_declined_reason.split()) >= 8
            )
    else:
        # The thin case: the right answer is to decline, not to write anyway.
        result.checks["declined_thin_evidence"] = not presentation.explain_supported

    return result


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
    parser.add_argument("--input", type=Path, required=True,
                        help="JSON array of stories captured from the corpus")
    args = parser.parse_args()

    SCRATCH.mkdir(exist_ok=True)
    corpus = json.loads(args.input.read_text())
    wanted = args.sources.split("|") if args.sources else DEFAULT_SOURCES
    chosen = [
        story
        for name in wanted[: args.stories]
        for story in corpus
        if story["source_name"] == name
    ]
    if not chosen:
        raise SystemExit(f"no stories matched {wanted}")

    results: list[Result] = []
    for model in args.models.split(","):
        for story in chosen:
            print(f"  running {model} / {story['source_name']} ...", flush=True)
            results.append(
                run_story(
                    model,
                    args.effort,
                    story,
                    expect_mechanism="explain" in story["supported_depths"],
                )
            )

    print(
        f"\n{'model':16s} {'story':22s} {'kind':16s} {'sec':>6s} {'in':>7s} "
        f"{'out':>6s} {'US$':>8s}  checks"
    )
    for result in results:
        passed = sum(1 for value in result.checks.values() if value)
        failed = [name for name, value in result.checks.items() if not value]
        note = result.error or (
            f"{passed}/{len(result.checks)}"
            + (f"  FAILED: {', '.join(failed)}" if failed else "")
        )
        if result.presentation and result.presentation.violations:
            note += f"  [{'; '.join(result.presentation.violations)}]"
        incoming, outgoing = result.tokens
        print(
            f"{result.model:16s} {result.story[:22]:22s} "
            f"{(result.packet.story_kind if result.packet else '-'):16s} "
            f"{result.seconds:6.1f} {incoming:7,d} {outgoing:6,d} "
            f"{result.cost:8.4f}  {note}"
        )

    for model in args.models.split(","):
        rows = [r for r in results if r.model == model]
        if not rows:
            continue
        cost = sum(r.cost for r in rows)
        print(
            f"\n{model}: mean {sum(r.seconds for r in rows) / len(rows):.1f}s, "
            f"US${cost / len(rows):.4f}/story "
            f"(US${cost / len(rows) * 2000:.2f} per 2,000 stories), "
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
                    "cost_usd": round(r.cost, 5),
                    "story_kind": r.packet.story_kind if r.packet else None,
                    "checks": r.checks,
                    "separation": r.separation,
                    "violations": (
                        list(r.presentation.violations) if r.presentation else []
                    ),
                    "error": r.error,
                    "display_title": (
                        r.presentation.display_title if r.presentation else None
                    ),
                    "glance": r.presentation.glance if r.presentation else None,
                    "qualification_span": (
                        r.presentation.glance_qualification_span
                        if r.presentation
                        else None
                    ),
                    "explain": r.presentation.explain if r.presentation else None,
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
