from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from curious_now_v2.core.enums import ExplanationDepth
from curious_now_v2.generation.client import Completion, Generator
from curious_now_v2.generation.packet import ExtractedPacket

PROMPT_VERSION = "present-v6"

# Prohibited by the title contract, and cheap to check.
HYPE = (
    "breakthrough",
    "revolutionary",
    "game-chang",
    "groundbreaking",
    "unprecedented",
    "paradigm shift",
)

# A qualification the reader meets as a heading is the thing we removed, so
# catch it coming back in the prose.
_LABELLED = re.compile(
    r"\s*(caveat|qualification|limitation|note|important|disclaimer|but note)\b\s*[:—-]",
    re.I,
)
_QUOTES = str.maketrans("‘’“”", "''\"\"")

# A ceiling low enough to force a choice. At 260 a Glance could carry the
# study's prevalence range, its date range, its method, two comparisons and a
# closing flourish, and every one of those was true — which is exactly the
# compressed abstract the contract prohibits.
#
# The floor is a nonsense guard and nothing more. A 49-word Glance was rejected
# by a floor of 50 while being the best in the batch — one idea, its
# qualification inside it, no padding — which is word count becoming the target
# again, in the other direction.
GLANCE_MIN_WORDS = 25
GLANCE_MAX_WORDS = 150
EXPLAIN_MAX_WORDS = 520
TITLE_MIN_WORDS = 5
TITLE_MAX_WORDS = 16

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["spine", "display_title", "glance", "explain"],
    "properties": {
        "spine": {
            "type": "object",
            "additionalProperties": False,
            "required": ["novelty", "core_intuition", "qualification"],
            "properties": {
                "novelty": {"type": "string"},
                "core_intuition": {"type": "string"},
                "qualification": {"type": "string"},
            },
        },
        "display_title": {"type": "string"},
        "glance": {
            "type": "object",
            "additionalProperties": False,
            "required": ["text", "qualification_span", "supported"],
            "properties": {
                "text": {"type": "string"},
                # Not shown to anyone: a quote from `text` locating the
                # qualification, so integration can be checked rather than
                # trusted. A separate field would be read as a separate section.
                "qualification_span": {"type": "string"},
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
understanding.

Everything you write must stay inside the SUPPORTED CLAIMS below. Those claims \
were extracted from the source and each is backed by a verbatim quote. The \
source text is given so you can phrase things naturally — not so you can add \
anything the claims do not carry. Do not use outside knowledge.

First settle the spine, which all the writing shares:
  novelty         what is genuinely new here, in one sentence — or, for an
                  explainer, which nothing is new in, what it makes clear
  core_intuition  the simplest accurate way to hold the idea
  qualification   the one thing whose omission would most mislead a reader

Then produce:

1. display_title: 6-14 words, plain language, naming the actual development — or \
for an explainer, the thing being explained. No hype, no unsupported \
superlative, no manufactured question. Attribute the claim if only an \
interested party makes it.

2. glance: for someone curious with no background in this field — imagine a \
sharp friend who works in something else.

   ONE idea. Decide the single thing this reader should walk away knowing, say \
   it plainly, give them one way to picture it or one reason to believe it, and \
   say why it might matter. Then stop. You are not summarising the source. You \
   are handing over the one thing worth carrying.

   Leave out of Glance, however true: how the work was done, sample sizes, \
   percentages, date ranges, place names that mean nothing to this reader, \
   lists of anything, and any second finding. All of that belongs to Explain. A \
   Glance carrying them has spent the reader's attention on detail before they \
   have the idea the detail is about.

   Any term your reader would not know must be explained right where it appears \
   or replaced with ordinary language. A Glance that reads like a compressed \
   abstract has failed even if every word in it is true. Set `supported` false \
   if the claims cannot carry even this.

   Where the evidence carries a qualification, write it into the Glance as \
   part of the explanation — a clause or a sentence in the reader's path, \
   placed where it changes how the sentence beside it is read. It belongs \
   wherever the reader would otherwise take away too much, which is almost \
   never the final sentence: a last line has nothing after it to correct, and \
   reads as the disclaimer we are trying to avoid. Then quote the words you \
   used in `qualification_span`, verbatim from your own Glance text. That \
   quote is a check on you and is shown to nobody.

   A qualification says what is not settled. A further claim about what is \
   expected or predicted is not one, unless you write what makes it uncertain.

   The qualification is the thing whose omission would most mislead — and what \
   that is depends on the kind of item:

   - a study or analysis: the scope condition or uncertainty the work itself \
     concedes — the population, the setting, what was not shown;
   - a release or anything an interested party announces about its own work: \
     that the claim comes from them and has not been independently checked;
   - an explainer: where the account stops — the part of the picture that is \
     still contested, or the step the explanation does not settle.

   Do not manufacture one. A restatement of what the thing is ("it interprets \
   data rather than recording it"), or a product detail ("still in beta"), is \
   not a qualification — leave `qualification_span` empty rather than write \
   either. Never write about the source itself: say what is uncertain, not \
   "the source says".

3. explain: an ELI20 for a reader who knows this field, answering ONE question: \
how does it work? The mechanism, and why it produces the claimed effect. Carry \
the qualification that keeps the mechanism honest.

   Explain is read on its own. It is not the next section after Glance — it is \
   the other way in, chosen by a reader who knows the field and may never see \
   Glance at all. So say what the thing is before you say how it works. Do not \
   open on a reference back: "The test hinges on...", "The mechanism begins \
   with...", "The reported gap comes from..." each assume a paragraph the \
   reader may not have read. Name the subject in your first sentence.

   Standing alone is not repeating. What Explain must never do is reuse \
   Glance's sentences or stay at Glance's level; re-establishing its own \
   subject in a clause is not that, and costs almost nothing.

   Write the explanation, not a length. Stop when the mechanism is clear — 300 \
   words that land beat 500 that pad. Never exceed 500 words.

   A mechanism says how something works. A list of what something can do is \
   not a mechanism, however long: "it fetches information when needed", "it \
   filters background noise" and "it follows instructions more reliably" \
   describe capabilities, and an Explain assembled from them only tells the \
   reader what Glance already told them, at greater length. If the second level \
   would be more detail rather than more depth, there is no second level.

   For a release this is the usual case, so treat Explain as the exception. A \
   product announcement describes what its product does; that is its purpose. \
   Write an Explain only where the source says what is going on INSIDE — the \
   technique, the representation, the signal, the reason the approach works. \
   "SynthID embeds an imperceptible watermark into the generated waveform" is \
   a mechanism. "It translates between two languages and switches based on who \
   is speaking" is the product working as described, and is Glance's job.

   So if the claims carry no mechanism, set mechanism_supported false, give the \
   reason in declined_reason, and leave text empty. Declining is correct, it is \
   common for a product announcement, and it is always preferred to writing \
   past the evidence. A story with a good Glance and no Explain is a complete \
   story.

`[equation]` and `[expression]` mark mathematics that could not be recovered \
from the source. Never treat them as content and never say what the equation states.

SOURCE: {source_name} ({content_type})
THIS ITEM IS A: {story_kind}
CENTRAL CLAIM: {central_claim}

SUPPORTED CLAIMS
{claims}

CONCEDED LIMITATIONS
{limitations}

SOURCE TEXT (for phrasing only)
{text}
"""


@dataclass(frozen=True)
class Presentation:
    spine_novelty: str
    spine_intuition: str
    spine_qualification: str
    display_title: str
    glance: str
    glance_qualification_span: str
    glance_supported: bool
    explain: str
    explain_supported: bool
    explain_declined_reason: str
    completion: Completion
    # Kept apart because they fail apart. A hyped title is a reason to fall
    # back to the source's own headline, not a reason to withhold an
    # explanation that is perfectly sound: "a failed title generation MUST NOT
    # block publication" (PRESENTATION_CONTRACT.md).
    title_violations: tuple[str, ...] = field(default_factory=tuple)
    violations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def valid_depths(self) -> tuple[ExplanationDepth, ...]:
        depths: list[ExplanationDepth] = []
        if self.glance_supported and self.glance.strip():
            depths.append(ExplanationDepth.GLANCE)
        if self.explain_supported and self.explain.strip():
            depths.append(ExplanationDepth.EXPLAIN)
        return tuple(depths)

    @property
    def valid(self) -> bool:
        """Whether anything can be shown to a reader — titles aside."""

        return not self.violations and bool(self.valid_depths)

    @property
    def title_valid(self) -> bool:
        return not self.title_violations and bool(self.display_title.strip())

    @property
    def all_violations(self) -> tuple[str, ...]:
        return self.title_violations + self.violations


def _words(value: str) -> int:
    return len(value.split())


def _flat(value: str) -> str:
    """Normalise for comparison: whitespace, and the quote marks models vary on."""

    return " ".join(value.split()).translate(_QUOTES).casefold()


def _quotes(span: str, text: str) -> bool:
    """Whether the span really is a piece of the text it claims to come from.

    The length floor only exists so a span cannot match by accident — "the" is
    inside every Glance ever written. It is not a judgement about how much a
    qualification needs to say: "Google says", opening a sentence about a
    company's own product, attributes the claim in two words, and an earlier
    three-word floor rejected a Glance for carrying it properly.
    """

    return (
        len(span.split()) >= 2
        and len(span.strip()) >= 8
        and _flat(span) in _flat(text)
    )


def _sentences(text: str) -> set[str]:
    return {
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", text)
        if len(part.split()) > 5
    }


def validate_title(title: str) -> tuple[str, ...]:
    """Judge the display title alone.

    Separate from the layers because the remedy is separate: a title that fails
    is replaced by the source's own headline, which is an attributed fact rather
    than our editorial text, and the story goes out regardless.
    """

    problems: list[str] = []
    if not TITLE_MIN_WORDS <= _words(title) <= TITLE_MAX_WORDS:
        problems.append(f"title is {_words(title)} words")
    if any(word in title.casefold() for word in HYPE):
        problems.append("title uses prohibited hype")
    if title.rstrip().endswith("?"):
        problems.append("title is a question")
    return tuple(problems)


def validate(presentation: Presentation, packet: ExtractedPacket) -> tuple[str, ...]:
    """Check the parts of the contract a machine can judge.

    Human evaluation still decides whether the result is any good; this only
    catches the breaches that need no taste — a Glance with no qualification,
    an Explain that restates Glance at length. The title is judged separately,
    by `validate_title`, since it fails without taking the story with it.
    """

    problems: list[str] = []

    if presentation.glance_supported:
        count = _words(presentation.glance)
        if not GLANCE_MIN_WORDS <= count <= GLANCE_MAX_WORDS:
            problems.append(f"glance is {count} words")
        # A qualification is required where the evidence or the source's own
        # interest supplies one. Demanding it everywhere is what produced
        # "still in beta" and "it interprets data rather than recording it".
        qualifiable = bool(
            packet.limitations
            or packet.story_kind == "release"
            or any(
                claim.kind.value in {"limitation", "uncertainty"}
                for claim in packet.claims
            )
        )
        span = presentation.glance_qualification_span.strip()
        if qualifiable and not span:
            problems.append("glance omits a qualification the evidence supports")
        elif span and not _quotes(span, presentation.glance):
            # The span exists only to prove the qualification is in the prose
            # the reader gets. If it is not there, it was written beside the
            # Glance rather than into it, which is what we removed.
            problems.append("qualification is not in the glance the reader reads")
        if re.match(r"\s*the (source|article|paper|post)\b", span, re.I):
            problems.append("qualification describes the source, not the science")
        if _LABELLED.match(span):
            problems.append("qualification is labelled rather than written in")

    if presentation.explain_supported:
        count = _words(presentation.explain)
        if count > EXPLAIN_MAX_WORDS:
            problems.append(f"explain is {count} words, over the ceiling")
        if count < 60:
            problems.append(f"explain is only {count} words")
        shared = _sentences(presentation.glance) & _sentences(presentation.explain)
        if shared:
            problems.append("explain reuses a sentence from glance")
    elif not presentation.explain_declined_reason.strip():
        problems.append("explain declined without a reason")

    # A mechanism cannot be explained from claims that never describe one.
    if presentation.explain_supported and not any(
        claim.kind.value == "method" for claim in packet.claims
    ):
        problems.append("explain claims a mechanism the packet does not support")

    if "[equation]" in presentation.explain or "[expression]" in presentation.explain:
        problems.append("explain passes an unrecovered-maths marker to the reader")

    return tuple(problems)


def generate_presentation(
    generator: Generator,
    packet: ExtractedPacket,
    *,
    source_name: str,
    content_type: str,
    text: str,
) -> Presentation:
    """Render the reader-facing layers from the packet's supported claims."""

    claims = "\n".join(
        f"- [{claim.kind.value}] {claim.text}" for claim in packet.claims
    )
    limitations = (
        "\n".join(f"- {value}" for value in packet.limitations)
        or "- (the source concedes none)"
    )
    completion = generator.complete(
        PROMPT.format(
            source_name=source_name,
            content_type=content_type,
            story_kind=packet.story_kind,
            central_claim=packet.central_claim,
            claims=claims,
            limitations=limitations,
            text=text,
        ),
        SCHEMA,
    )
    payload = completion.payload or {}
    spine = payload.get("spine") or {}
    glance = payload.get("glance") or {}
    explain = payload.get("explain") or {}

    presentation = Presentation(
        spine_novelty=str(spine.get("novelty") or "").strip(),
        spine_intuition=str(spine.get("core_intuition") or "").strip(),
        spine_qualification=str(spine.get("qualification") or "").strip(),
        display_title=str(payload.get("display_title") or "").strip(),
        glance=str(glance.get("text") or "").strip(),
        glance_qualification_span=str(glance.get("qualification_span") or "").strip(),
        glance_supported=bool(glance.get("supported")),
        explain=str(explain.get("text") or "").strip(),
        explain_supported=bool(explain.get("mechanism_supported")),
        explain_declined_reason=str(explain.get("declined_reason") or "").strip(),
        completion=completion,
    )
    if not completion.ok:
        return presentation
    return Presentation(
        **{
            **presentation.__dict__,
            "title_violations": validate_title(presentation.display_title),
            "violations": validate(presentation, packet),
        }
    )
