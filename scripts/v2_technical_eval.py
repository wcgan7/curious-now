#!/usr/bin/env python
"""Generate a Technical walkthrough and check it cites what it draws on.

Technical is the layer the structured extraction exists for: the contract
requires it to cite the sections, figures, and tables it uses, which a flat
blob of text could never support. This feeds the model the section and float
map recovered during retrieval and then checks the citations back against it —
a claimed "Figure 4" that the paper does not have is worse than no citation.

    python scripts/v2_technical_eval.py --models gpt-5.6-luna,gpt-5.6-terra
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

SCRATCH = Path(__file__).parents[1] / ".eval"
SCHEMA_PATH = SCRATCH / "technical_schema.json"

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sections", "prerequisites", "citations", "eligible", "declined_reason"],
    "properties": {
        "eligible": {"type": "boolean"},
        "declined_reason": {"type": "string"},
        "prerequisites": {"type": "array", "items": {"type": "string"}},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "used_for"],
                "properties": {
                    "label": {"type": "string"},
                    "used_for": {"type": "string"},
                },
            },
        },
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["heading", "text"],
                "properties": {
                    "heading": {"type": "string"},
                    "text": {"type": "string"},
                },
            },
        },
    },
}

PROMPT = """You are writing the Technical walkthrough for Curious Now. The \
reader has already read a Glance and an Explain, so the central intuition is \
established. They are now inspecting the work itself: the question this layer \
answers is whether it holds up.

Work ONLY from the SOURCE TEXT. Do not use outside knowledge.

Write 1200-2500 words total, split across these headings in this order, \
omitting any the source cannot support:
  Orientation, Problem formulation, Approach, Evidence, Results,
  Ablations or alternatives, Limitations, Relation to prior work

Use equations or numbers only where they improve understanding of the claim.
Remain an intuitive walkthrough, not a compressed paper.

In `citations`, list the sections, figures, and tables you actually drew on, \
using labels EXACTLY as they appear in the STRUCTURE MAP below, each with what \
you used it for. Do not cite anything absent from that map.

In `prerequisites`, list the concepts a capable reader outside this speciality \
would need in order to follow the walkthrough.

If the source cannot support an inspection of the method and evidence, set \
eligible to false and explain why in declined_reason.

SOURCE: {source_name} ({content_type})
TITLE: {title}

STRUCTURE MAP
Sections: {sections}
Figures: {figures}
Tables: {tables}

SOURCE TEXT:
{full_text}
"""


def run(model: str, effort: str, prompt: str, tag: str) -> dict[str, object]:
    SCRATCH.mkdir(exist_ok=True)
    out = SCRATCH / f"tech-{tag}.json"
    started = time.monotonic()
    completed = subprocess.run(
        [
            "codex", "exec", "-m", model,
            "-c", f'model_reasoning_effort="{effort}"',
            "--sandbox", "read-only", "--ephemeral", "--skip-git-repo-check",
            "--output-schema", str(SCHEMA_PATH), "-o", str(out), "--json", "-",
        ],
        input=prompt, capture_output=True, text=True, timeout=1500,
    )
    seconds = time.monotonic() - started

    usage: dict[str, int] = {}
    for line in completed.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and "usage" in event:
            usage = event["usage"]

    payload = None
    if out.exists():
        try:
            payload = json.loads(out.read_text())
        except ValueError:
            payload = None
    return {"seconds": seconds, "usage": usage, "payload": payload}


def known_labels(structure: dict[str, object]) -> set[str]:
    """Everything the extraction actually recovered, for checking citations."""

    labels: set[str] = set()
    for section in structure.get("sections") or []:
        title = (section or {}).get("title")
        if title:
            labels.add(str(title).strip().casefold())
    for group in ("figures", "tables"):
        for item in structure.get(group) or []:
            label = (item or {}).get("label")
            if label:
                labels.add(str(label).strip().casefold())
    return labels


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="gpt-5.6-luna,gpt-5.6-terra")
    parser.add_argument("--effort", default="high")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("/tmp/claude-1000/-home-gan-Documents-curious-now")
        / "27ad0ebc-321f-4577-a3e7-0f6a86854dd3/scratchpad/technical_stories.json",
    )
    args = parser.parse_args()

    SCRATCH.mkdir(exist_ok=True)
    SCHEMA_PATH.write_text(json.dumps(OUTPUT_SCHEMA))
    corpus = json.loads(args.input.read_text())

    results = []
    for model in args.models.split(","):
        for story in corpus:
            structure = story.get("structure") or {}
            sections = [
                s["title"]
                for s in (structure.get("sections") or [])
                if s.get("title") and s.get("words", 0) > 40
            ][:40]
            figures = [
                f"{f.get('label')}: {(f.get('caption') or '')[:90]}"
                for f in (structure.get("figures") or [])
                if f.get("label")
            ][:25]
            tables = [
                f"{t.get('label')}: {(t.get('caption') or '')[:90]}"
                for t in (structure.get("tables") or [])
                if t.get("label")
            ][:15]

            tag = f"{model}-{story['source_name'].replace(' ', '_')}"
            print(f"  running {tag} ...", flush=True)
            outcome = run(
                model,
                args.effort,
                PROMPT.format(
                    source_name=story["source_name"],
                    content_type=story["content_type"],
                    title=story["title"],
                    sections="; ".join(sections) or "(none recovered)",
                    figures="; ".join(figures) or "(none recovered)",
                    tables="; ".join(tables) or "(none recovered)",
                    full_text=story["full_text"],
                ),
                tag,
            )
            outcome |= {
                "model": model,
                "story": story["source_name"],
                "known_labels": sorted(known_labels(structure)),
            }
            results.append(outcome)

    print(f"\n{'model':15s} {'story':10s} {'sec':>6s} {'words':>6s} {'cites':>6s} {'bad':>4s} {'prereq':>7s}")
    for entry in results:
        payload = entry.get("payload") or {}
        body = " ".join(s.get("text", "") for s in payload.get("sections") or [])
        citations = payload.get("citations") or []
        known = set(entry["known_labels"])
        # The structure map presents floats as "Figure 3: caption", so a model
        # told to quote labels exactly returns that whole string. Match on the
        # label part rather than calling a correct citation invented.
        def matches(label: str) -> bool:
            probe = label.strip().casefold()
            head = probe.split(":", 1)[0].strip()
            return any(
                probe == k or head == k or probe.startswith(k) or k.startswith(head)
                for k in known
                if k
            )

        invented = [
            c.get("label")
            for c in citations
            if not matches(str(c.get("label", "")))
        ]
        print(
            f"{entry['model']:15s} {entry['story'][:10]:10s} {entry['seconds']:6.1f} "
            f"{len(body.split()):6,d} {len(citations):6d} {len(invented):4d} "
            f"{len(payload.get('prerequisites') or []):7d}"
            + (f"   invented: {invented[:3]}" if invented else "")
        )

    (SCRATCH / "technical_results.json").write_text(json.dumps(results, indent=1))
    print(f"\nfull outputs written to {SCRATCH / 'technical_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
