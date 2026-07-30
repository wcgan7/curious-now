from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from curious_now_v2.core.enums import ClaimKind
from curious_now_v2.generation.client import Completion, Generator

PROMPT_VERSION = "packet-v2"

# Extraction, deliberately: asking which claims the source supports is a task a
# model does well, where asking whether it feels able to explain something is
# not. Absence of a claim is then a fact the pipeline can check, rather than a
# judgement it has to trust.
SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "story_kind",
        "central_claim",
        "claims",
        "limitations",
        "prerequisites",
    ],
    "properties": {
        "story_kind": {
            "type": "string",
            "enum": [
                "research_result",
                "release",
                "correction",
                "debate",
                "announcement",
                "not_science",
            ],
        },
        "central_claim": {"type": "string"},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "prerequisites": {"type": "array", "items": {"type": "string"}},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "text", "confidence", "excerpt"],
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [kind.value for kind in ClaimKind],
                    },
                    "text": {"type": "string"},
                    "confidence": {"type": "number"},
                    "excerpt": {"type": "string"},
                },
            },
        },
    },
}

PROMPT = """Read the SOURCE TEXT and record what it supports. You are not \
writing for a reader; you are building the factual record that later writing \
must stay inside.

For each claim the source actually makes, give:
  kind        one of: observation, result, method, comparison, limitation,
              uncertainty, context
  text        the claim in one plain sentence
  confidence  0 to 1, how firmly the source states it
  excerpt     a short verbatim span from the source that supports it

Rules that matter more than completeness:

- Record only what the source states. Do not add background knowledge, and do
  not infer a claim the text merely gestures at.
- Every claim needs a verbatim excerpt. If you cannot quote it, do not record it.
- Use `method` for how something works or was done — the mechanism. Use
  `comparison` only where the source compares against a baseline or prior
  state. Use `limitation` or `uncertainty` for what the source itself concedes.
- Do not invent limitations. If the source concedes nothing, leave the list
  empty; that absence is itself informative.
- `[equation]` or `[expression]` marks mathematics that could not be recovered
  from the source format. Never treat those markers as content, and never
  describe what the equation says.

story_kind is what this item actually is, which decides how it can be written
about. Judge the item, not the publisher:

  research_result  a study, experiment, analysis, or proof, with findings
  release          a model, tool, dataset, or product made available, where the
                   source describes what it is and how it works
  correction       a retraction, correction, or revised conclusion
  debate           disagreement between positions over evidence
  announcement     an event, podcast, funding award, appointment, or programme —
                   something happening rather than something found or built
  not_science      marketing, opinion, or general news with no scientific content

Be strict. A company blog post about a product is a release only if it explains
what the thing does; if it is mainly promotion, it is an announcement. A podcast
series, a conference, or a grant is an announcement, however scientific the
subject matter.

central_claim is the single thing this item amounts to, in one sentence.
prerequisites are concepts a reader would need in order to follow it.

SOURCE: {source_name} ({content_type})
TITLE: {title}

SOURCE TEXT:
{text}
"""


@dataclass(frozen=True)
class ExtractedClaim:
    kind: ClaimKind
    text: str
    confidence: float
    excerpt: str


VALID_KINDS = frozenset(
    {
        "research_result",
        "release",
        "correction",
        "debate",
        "announcement",
        "not_science",
    }
)
# Kinds that carry a development worth opening. An announcement reports that
# something happened; the feed is for what was found or built.
PUBLISHABLE_KINDS = frozenset({"research_result", "release", "correction", "debate"})


@dataclass(frozen=True)
class ExtractedPacket:
    story_kind: str
    central_claim: str
    claims: tuple[ExtractedClaim, ...]
    limitations: tuple[str, ...]
    prerequisites: tuple[str, ...]
    completion: Completion

    @property
    def kinds(self) -> frozenset[ClaimKind]:
        return frozenset(claim.kind for claim in self.claims)

    @property
    def usable(self) -> bool:
        return bool(self.central_claim.strip() and self.claims)

    @property
    def worth_publishing(self) -> bool:
        """Whether this is a development rather than news of one."""

        return self.story_kind in PUBLISHABLE_KINDS


def _grounded(claim: dict[str, Any], source_text: str) -> bool:
    """Whether the excerpt really appears in the source.

    A claim is only as good as the span behind it, and an excerpt the source
    does not contain is the clearest possible sign the claim was invented.
    Whitespace is normalised before comparing, since extraction reflows text.
    """

    excerpt = " ".join(str(claim.get("excerpt", "")).split())
    if len(excerpt) < 12:
        return False
    return excerpt.casefold() in " ".join(source_text.split()).casefold()


def extract_packet(
    generator: Generator,
    *,
    source_name: str,
    content_type: str,
    title: str,
    text: str,
) -> ExtractedPacket:
    """Build the factual record a story's presentations must stay inside."""

    completion = generator.complete(
        PROMPT.format(
            source_name=source_name,
            content_type=content_type,
            title=title,
            text=text,
        ),
        SCHEMA,
    )
    payload = completion.payload or {}

    claims: list[ExtractedClaim] = []
    for raw in payload.get("claims") or []:
        if not isinstance(raw, dict) or not _grounded(raw, text):
            continue
        try:
            kind = ClaimKind(str(raw.get("kind")))
        except ValueError:
            continue
        statement = str(raw.get("text", "")).strip()
        if not statement:
            continue
        claims.append(
            ExtractedClaim(
                kind=kind,
                text=statement,
                confidence=min(max(float(raw.get("confidence") or 0.5), 0.0), 1.0),
                excerpt=" ".join(str(raw.get("excerpt", "")).split()),
            )
        )

    story_kind = str(payload.get("story_kind") or "").strip()
    return ExtractedPacket(
        story_kind=story_kind if story_kind in VALID_KINDS else "not_science",
        central_claim=str(payload.get("central_claim") or "").strip(),
        claims=tuple(claims),
        limitations=tuple(
            str(value).strip()
            for value in (payload.get("limitations") or [])
            if str(value).strip()
        ),
        prerequisites=tuple(
            str(value).strip()
            for value in (payload.get("prerequisites") or [])
            if str(value).strip()
        ),
        completion=completion,
    )
