from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from curious_now_v2.core.enums import ExplanationDepth
from curious_now_v2.generation.client import (
    Completion,
    Generator,
    storable,
    unescape_newlines,
)
from curious_now_v2.generation.packet import ExtractedPacket

PROMPT_VERSION = "present-v11"

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
    "required": ["spine", "display_title", "explain"],
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
                  Name the one central change, not its practical variants or
                  implementation alternatives.
  core_intuition  the simplest accurate way to hold the idea
  qualification   the one thing whose omission would most mislead a reader
                  State only the boundary on the claim, not the workaround,
                  practical variant, or future work that responds to it.

Then produce:

1. display_title: 6-14 words. No hype, no unsupported superlative, no \
manufactured question. Attribute the claim if only an interested party makes it.

   Write it in the register of these, which are real headlines from science \
   newsrooms and research labs:

       Butterflies thrive in micro-reserve garden
       Uncovering repurposed medicines to fight liver fibrosis
       All living things emit a faint glow. Could this light be useful?
       How confessions can keep language models honest
       Deep-sea snails ride surface currents to reach distant hydrothermal vents
       Uniting biological toolkits for a new approach to ALS
       AI maps Titan's methane clouds in record time
       A new quantum toolkit for optimization
       Finding GPT-4's mistakes with GPT-4
       The anatomy of a personal health agent

   Notice what they do not do: they do not name the method, they do not stack \
   nouns, and they do not use an acronym a reader would have to look up. Notice \
   what they do: a concrete subject, an ordinary verb, and one idea. For an \
   explainer, the same register applied to the thing being explained.

   Then check your title against one rule before you answer: if it contains \
   three nouns in a row, rewrite it. A noun stack is what a title looks like \
   when it has named a technique instead of saying what happened.

2. explain: an ELI20 for a reader who knows this field, answering ONE question: \
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
from the source. Never treat them as content and never say what the equation \
states.

Recovered mathematics arrives delimited, as \\( ... \\) or \\[ ... \\]. Where you \
quote any, keep those delimiters: they are how the reader's typesetter finds \
the formula, and without them it prints backslashes at the reader. Glance \
should rarely need any at all.

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
    # Idea is deliberately written in a separate, smaller call. Keeping that
    # call here lets the database record the provenance of the words it stores.
    glance_completion: Completion | None = None
    glance_prompt_version: str = ""
    glance_declined_reason: str = ""
    # The grounded editorial choice that preceded the Idea writer. Keeping it
    # with the layer makes centrality inspectable after generation rather than
    # leaving only the finished prose and a prompt-version label.
    glance_brief: dict[str, Any] = field(default_factory=dict)
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


# Sources whose headlines are already written for a general reader, by a
# journalist or a lab's communications team.
WRITTEN_FOR_READERS = frozenset(
    {"news", "blog", "lab_announcement", "press_release"}
)


def title_for(
    *, source_title: str, generated: str, content_type: str
) -> tuple[str, tuple[str, ...]]:
    """Which title to show, and what is wrong with it.

    Rewriting a paper's title helps: measured over 45 papers, ours read as
    plain to a non-expert where the authors' did in 81% of cases, because a
    paper's title is written for peers.

    Rewriting a news headline does the opposite. Across 140 published stories a
    judge found ours harder than the source's own in 28% of items that arrived
    already written for a reader, against 7% of papers -- "How AI trained on
    birds is surfacing underwater mysteries" became "Perch 2.0 Transfers
    Bird-Learned Sound Features to Underwater Tasks". So those keep their own
    headline.

    Length is not checked on a headline we did not write. The 6-14 word bound
    exists to stop our own titles sprawling or saying nothing; a newsroom's
    "Butterflies thrive in micro-reserve garden" is not defective for being
    six words and "Report from the self-organizing conference" is not defective
    for being five. Hype and manufactured questions are still refused, because
    those are the reasons a headline is unusable rather than merely short.
    """

    source = (source_title or "").strip()
    if content_type in WRITTEN_FOR_READERS and source:
        refusals = _unusable(source)
        if not refusals:
            return source, ()
        # A hyped or interrogative headline is worse than our rewrite, so the
        # rewrite stands and is judged on its own terms.

    return generated, validate_title(generated)


def _unusable(title: str) -> tuple[str, ...]:
    """What makes a headline unusable, regardless of who wrote it."""

    problems: list[str] = []
    if any(word in title.casefold() for word in HYPE):
        problems.append("title uses prohibited hype")
    if title.rstrip().endswith("?"):
        problems.append("title is a question")
    return tuple(problems)


def validate_glance_words(glance: str) -> tuple[str, ...]:
    """The Glance's length contract, on its own.

    Split out so a pass that rewrites only the Glance can check it without
    assembling a whole Presentation. The bounds are the same ones `validate`
    applies, and there is one copy of them.
    """

    count = _words(glance)
    if not GLANCE_MIN_WORDS <= count <= GLANCE_MAX_WORDS:
        return (f"glance is {count} words",)
    return ()


def validate_title(title: str) -> tuple[str, ...]:
    """Judge the display title alone.

    Separate from the layers because the remedy is separate: a title that fails
    is replaced by the source's own headline, which is an attributed fact rather
    than our editorial text, and the story goes out regardless.
    """

    problems: list[str] = []
    if not TITLE_MIN_WORDS <= _words(title) <= TITLE_MAX_WORDS:
        problems.append(f"title is {_words(title)} words")
    return tuple(problems) + _unusable(title)


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
        if presentation.glance_brief:
            boundary = presentation.glance_brief.get("essential_boundary") or {}
            qualifiable = bool(boundary.get("supported"))
        else:
            # Legacy presentations and direct callers have no editorial brief.
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
    explain = payload.get("explain") or {}

    presentation = Presentation(
        spine_novelty=str(spine.get("novelty") or "").strip(),
        spine_intuition=str(spine.get("core_intuition") or "").strip(),
        spine_qualification=str(spine.get("qualification") or "").strip(),
        display_title=str(payload.get("display_title") or "").strip(),
        glance="",
        glance_qualification_span="",
        glance_supported=False,
        explain=storable(unescape_newlines(str(explain.get("text") or "").strip())),
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
