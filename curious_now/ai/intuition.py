"""Layered intuition generation for story clusters.

This module generates two intuition layers in a strict cascade:
- ELI20 (Conceptual Intuition): derived only from Deep Dive text
- ELI5 (Foundational Intuition): derived only from ELI20 text
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from curious_now.ai.llm_adapter import LLMAdapter, LLMResponse, get_llm_adapter

logger = logging.getLogger(__name__)

_DIGIT_RE = re.compile(r"\d")

# Soft length targets (words)
ELI20_TARGET_MIN_WORDS = 100
ELI20_TARGET_MAX_WORDS = 150
ELI20_HARD_MAX_WORDS = 250

ELI5_TARGET_MIN_WORDS = 60
ELI5_TARGET_MAX_WORDS = 100
ELI5_HARD_MAX_WORDS = 250


@dataclass
class IntuitionInput:
    """Input data for layered intuition generation.

    Notes:
    - `deep_dive_markdown` is required for the new cascade.
    - Legacy fields are accepted for backward compatibility but ignored.
    """

    cluster_title: str
    deep_dive_markdown: str | None = None
    takeaway: str | None = None
    technical_snippets: list[str] | None = None
    glossary_terms: list[GlossaryTerm] | None = None
    topic_names: list[str] | None = None


@dataclass
class GlossaryTerm:
    """A glossary term with definition (legacy compatibility)."""

    term: str
    definition: str


@dataclass
class IntuitionResult:
    """Result of layered intuition generation."""

    intuition: str  # Backward-compatible alias for ELI5 output
    eli20: str
    eli5: str
    confidence: float
    model: str
    success: bool = True
    error: str | None = None
    eli20_word_count: int = 0
    eli5_word_count: int = 0
    eli20_rerun_shorten: bool = False
    eli5_rerun_shorten: bool = False
    eli20_new_digit_flag: bool = False
    eli5_new_digit_flag: bool = False

    @staticmethod
    def failure(error: str) -> IntuitionResult:
        """Create a failure result."""
        return IntuitionResult(
            intuition="",
            eli20="",
            eli5="",
            confidence=0.0,
            model="unknown",
            success=False,
            error=error,
        )


ELI20_SYSTEM_PROMPT = """You are explaining a scientific or technical topic to a reader who already has some familiarity with the field.

Goal: Provide the \"Conceptual Intuition\" layer-help the reader form a clear mental model of what was done and how it works at a high level, without diving into implementation details.

Rules:
- Base your explanation strictly on the provided Deep Dive text.
- Do not add new facts, interpretations, implications, or claims beyond what appears in the Deep Dive.
- Use technical terms when they improve precision, but stay at the conceptual level.
- Avoid everyday analogies unless absolutely necessary.
- No hype, no filler."""


ELI20_USER_PROMPT_TEMPLATE = """Topic: {cluster_title}

Canonical Deep Dive (source of truth):
{deep_dive_markdown}

Task:
Write a single compact paragraph that:
- Explains the core idea or approach at a conceptual level
- Describes how it works at a high level (key components/steps, but not implementation detail)
- Highlights what is distinctive or novel ONLY if stated in the Deep Dive

Constraints:
- Do NOT introduce any new information.
- Do NOT include numeric results, sample sizes, p-values, or detailed experimental setup.
- Target length: ~100-150 words.
- Output ONLY the paragraph text."""


ELI5_SYSTEM_PROMPT = """You are explaining a scientific idea to an intelligent reader with no background in this topic.

Goal: Provide the \"Foundational Intuition\" layer-help the reader quickly grasp what this is about and what problem it addresses, without technical detail.

Rules:
- Base your explanation strictly on the provided ELI20 text.
- Use plain language and minimize technical terms.
- Do not oversimplify in a way that changes the meaning.
- Use an everyday analogy only if it genuinely clarifies the concept; do not force one.
- Do not add new facts, interpretations, implications, or claims.
- No hype, no filler."""


ELI5_USER_PROMPT_TEMPLATE = """Topic: {cluster_title}

Conceptual Intuition (ELI20):
{eli20_text}

Task:
Write one short paragraph that:
- Introduces what this idea is about
- Explains what problem it is trying to solve
- Gives a very high-level sense of how it works

Constraints:
- Do NOT introduce new information.
- Target length: ~60-100 words.
- Do not force analogies.
- Output ONLY the paragraph text."""

ABSTRACT_ELI5_SYSTEM_PROMPT = """You are explaining a research abstract to a curious general reader.

Goal: Provide a plain-language short explainer (ELI5-style) based only on the supplied abstracts.

Rules:
- Stay strictly grounded in the provided abstract text.
- Do not add methods, results, or implications that are not explicitly present.
- Avoid certainty language when abstracts are limited.
- No hype, no filler."""

ABSTRACT_ELI5_USER_PROMPT_TEMPLATE = """Topic: {cluster_title}

Abstract sources:
{abstracts_text}

Task:
Write one short paragraph that explains:
- What this research is about
- The problem it addresses
- What appears to be the main idea at a high level

Constraints:
- Use only what is present in the abstracts.
- Do not introduce new facts, numbers, or claims.
- Mention that this is based on abstracts only.
- Target length: ~60-100 words.
- Output ONLY the paragraph text.
- If there is not enough information in the abstracts to write a meaningful summary, output exactly: INSUFFICIENT_CONTEXT"""


# ─────────────────────────────────────────────────────────────────────────────
# News/Article Summary (for non-paper sources)
# ─────────────────────────────────────────────────────────────────────────────

NEWS_SUMMARY_MIN_CONTENT_CHARS = 300  # Minimum content length to attempt summary

NEWS_SUMMARY_SYSTEM_PROMPT = """You are summarizing a news article or press release for a curious reader.

Goal: Provide a brief, factual summary of what this news item is about.

Rules:
- Stay strictly grounded in the provided title and content.
- Do not invent details, statistics, or implications not present in the source.
- Do not speculate about causes, consequences, or future developments.
- Use plain language.
- No hype, no filler."""

NEWS_SUMMARY_USER_PROMPT_TEMPLATE = """Title: {title}

Content:
{content}

Task:
Write 1-2 sentences summarizing what this news item is about.

Constraints:
- Use ONLY information present in the title and content above.
- Do NOT invent or hallucinate any details, numbers, or claims.
- If the content is too brief or vague to summarize meaningfully, output exactly: INSUFFICIENT_CONTEXT
- Target length: 30-60 words.
- Output ONLY the summary text (or INSUFFICIENT_CONTEXT)."""

INSUFFICIENT_CONTEXT_MARKER = "INSUFFICIENT_CONTEXT"


def _word_count(text: str) -> int:
    return len(text.split())


def _clean_output(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1].strip()
    if cleaned.startswith("'") and cleaned.endswith("'"):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _has_new_digits(source_text: str, derived_text: str) -> bool:
    source_digits = set(_DIGIT_RE.findall(source_text))
    derived_digits = set(_DIGIT_RE.findall(derived_text))
    return len(derived_digits - source_digits) > 0


def _calc_confidence(
    eli20: str,
    eli5: str,
    *,
    eli20_new_digit_flag: bool,
    eli5_new_digit_flag: bool,
) -> float:
    confidence = 0.75

    eli20_words = _word_count(eli20)
    eli5_words = _word_count(eli5)

    if ELI20_TARGET_MIN_WORDS <= eli20_words <= ELI20_TARGET_MAX_WORDS:
        confidence += 0.1
    elif eli20_words > ELI20_HARD_MAX_WORDS or eli20_words < 50:
        confidence -= 0.1

    if ELI5_TARGET_MIN_WORDS <= eli5_words <= ELI5_TARGET_MAX_WORDS:
        confidence += 0.1
    elif eli5_words > ELI5_HARD_MAX_WORDS or eli5_words < 30:
        confidence -= 0.1

    if eli20_new_digit_flag:
        confidence -= 0.1
    if eli5_new_digit_flag:
        confidence -= 0.1

    return max(0.0, min(1.0, confidence))


def generate_eli20(
    input_data: IntuitionInput,
    *,
    adapter: LLMAdapter | None = None,
) -> tuple[str, str, bool, int, bool]:
    """Generate ELI20 from deep dive only.

    Returns: (text, model, rerun_shorten, word_count, new_digit_flag)
    """
    if adapter is None:
        adapter = get_llm_adapter()

    if not input_data.deep_dive_markdown:
        return "", "unknown", False, 0, False

    user_prompt = ELI20_USER_PROMPT_TEMPLATE.format(
        cluster_title=input_data.cluster_title,
        deep_dive_markdown=input_data.deep_dive_markdown,
    )

    response: LLMResponse = adapter.complete(
        user_prompt,
        system_prompt=ELI20_SYSTEM_PROMPT,
        max_tokens=500,
        temperature=0.3,
    )

    if not response.success:
        return "", response.model, False, 0, False

    eli20_text = _clean_output(response.text)
    eli20_words = _word_count(eli20_text)
    rerun_shorten = False

    if eli20_words > ELI20_HARD_MAX_WORDS:
        rerun_shorten = True
        shortened_prompt = (
            user_prompt
            + "\n\nRevision instruction: shorten aggressively to 100-150 words while preserving meaning."
        )
        retry_response = adapter.complete(
            shortened_prompt,
            system_prompt=ELI20_SYSTEM_PROMPT,
            max_tokens=300,
            temperature=0.2,
        )
        if retry_response.success:
            response = retry_response
            eli20_text = _clean_output(retry_response.text)
            eli20_words = _word_count(eli20_text)

    new_digit_flag = _has_new_digits(input_data.deep_dive_markdown, eli20_text)

    return eli20_text, response.model, rerun_shorten, eli20_words, new_digit_flag


def generate_eli5(
    *,
    cluster_title: str,
    eli20_text: str,
    adapter: LLMAdapter | None = None,
) -> tuple[str, str, bool, int, bool]:
    """Generate ELI5 from ELI20 only.

    Returns: (text, model, rerun_shorten, word_count, new_digit_flag)
    """
    if adapter is None:
        adapter = get_llm_adapter()

    user_prompt = ELI5_USER_PROMPT_TEMPLATE.format(
        cluster_title=cluster_title,
        eli20_text=eli20_text,
    )

    response: LLMResponse = adapter.complete(
        user_prompt,
        system_prompt=ELI5_SYSTEM_PROMPT,
        max_tokens=350,
        temperature=0.3,
    )

    if not response.success:
        return "", response.model, False, 0, False

    eli5_text = _clean_output(response.text)
    eli5_words = _word_count(eli5_text)
    rerun_shorten = False

    if eli5_words > ELI5_HARD_MAX_WORDS:
        rerun_shorten = True
        shortened_prompt = (
            user_prompt
            + "\n\nRevision instruction: shorten aggressively to 60-100 words while preserving meaning."
        )
        retry_response = adapter.complete(
            shortened_prompt,
            system_prompt=ELI5_SYSTEM_PROMPT,
            max_tokens=220,
            temperature=0.2,
        )
        if retry_response.success:
            response = retry_response
            eli5_text = _clean_output(retry_response.text)
            eli5_words = _word_count(eli5_text)

    new_digit_flag = _has_new_digits(eli20_text, eli5_text)

    return eli5_text, response.model, rerun_shorten, eli5_words, new_digit_flag


def generate_intuition(
    input_data: IntuitionInput,
    *,
    adapter: LLMAdapter | None = None,
) -> IntuitionResult:
    """Generate layered intuition via Deep Dive -> ELI20 -> ELI5."""
    if not input_data.cluster_title:
        return IntuitionResult.failure("No cluster title provided")

    if not input_data.deep_dive_markdown:
        return IntuitionResult.failure("No deep dive markdown provided")

    if adapter is None:
        adapter = get_llm_adapter()

    eli20_text, eli20_model, eli20_rerun, eli20_words, eli20_digit_flag = generate_eli20(
        input_data, adapter=adapter
    )
    if not eli20_text:
        return IntuitionResult.failure("ELI20 generation failed")

    eli5_text, eli5_model, eli5_rerun, eli5_words, eli5_digit_flag = generate_eli5(
        cluster_title=input_data.cluster_title,
        eli20_text=eli20_text,
        adapter=adapter,
    )
    if not eli5_text:
        return IntuitionResult.failure("ELI5 generation failed")

    confidence = _calc_confidence(
        eli20_text,
        eli5_text,
        eli20_new_digit_flag=eli20_digit_flag,
        eli5_new_digit_flag=eli5_digit_flag,
    )

    return IntuitionResult(
        intuition=eli5_text,
        eli20=eli20_text,
        eli5=eli5_text,
        confidence=confidence,
        model=eli5_model or eli20_model,
        success=True,
        eli20_word_count=eli20_words,
        eli5_word_count=eli5_words,
        eli20_rerun_shorten=eli20_rerun,
        eli5_rerun_shorten=eli5_rerun,
        eli20_new_digit_flag=eli20_digit_flag,
        eli5_new_digit_flag=eli5_digit_flag,
    )


def generate_intuition_from_abstracts(
    *,
    cluster_title: str,
    abstracts_text: str,
    adapter: LLMAdapter | None = None,
) -> IntuitionResult:
    """Generate ELI5-only intuition from abstract text when full text is unavailable."""
    if not cluster_title:
        return IntuitionResult.failure("No cluster title provided")
    if not abstracts_text or not abstracts_text.strip():
        return IntuitionResult.failure("No abstract text provided")

    if adapter is None:
        adapter = get_llm_adapter()

    user_prompt = ABSTRACT_ELI5_USER_PROMPT_TEMPLATE.format(
        cluster_title=cluster_title,
        abstracts_text=abstracts_text,
    )
    response = adapter.complete(
        user_prompt,
        system_prompt=ABSTRACT_ELI5_SYSTEM_PROMPT,
        max_tokens=350,
        temperature=0.25,
    )
    if not response.success:
        return IntuitionResult.failure(response.error or "ELI5 from abstracts generation failed")

    eli5_text = _clean_output(response.text)

    # Check if LLM indicated insufficient context
    if INSUFFICIENT_CONTEXT_MARKER in eli5_text.upper():
        logger.info("Abstract ELI5: LLM indicated insufficient context for: %s", cluster_title)
        return IntuitionResult.failure("Insufficient context in abstracts")

    if not eli5_text:
        return IntuitionResult.failure("ELI5 from abstracts generation failed")

    eli5_words = _word_count(eli5_text)
    new_digit_flag = _has_new_digits(abstracts_text, eli5_text)
    confidence = 0.62
    if ELI5_TARGET_MIN_WORDS <= eli5_words <= ELI5_TARGET_MAX_WORDS:
        confidence += 0.08
    elif eli5_words > ELI5_HARD_MAX_WORDS or eli5_words < 30:
        confidence -= 0.1
    if new_digit_flag:
        confidence -= 0.1
    confidence = max(0.0, min(1.0, confidence))

    return IntuitionResult(
        intuition=eli5_text,
        eli20="",
        eli5=eli5_text,
        confidence=confidence,
        model=response.model,
        success=True,
        eli20_word_count=0,
        eli5_word_count=eli5_words,
        eli20_rerun_shorten=False,
        eli5_rerun_shorten=False,
        eli20_new_digit_flag=False,
        eli5_new_digit_flag=new_digit_flag,
    )


def generate_intuition_from_db_data(
    cluster_id: str,
    canonical_title: str,
    takeaway: str | None = None,
    technical_snippets: list[str] | None = None,
    glossary_terms: list[dict[str, Any]] | None = None,
    topic_names: list[str] | None = None,
    deep_dive_markdown: str | None = None,
    *,
    adapter: LLMAdapter | None = None,
) -> IntuitionResult:
    """Generate layered intuition from database-style inputs."""
    _ = (cluster_id, takeaway, technical_snippets, glossary_terms, topic_names)

    input_data = IntuitionInput(
        cluster_title=canonical_title,
        deep_dive_markdown=deep_dive_markdown,
    )

    return generate_intuition(input_data, adapter=adapter)


@dataclass
class NewsSummaryResult:
    """Result of news/article summary generation."""

    summary: str
    confidence: float
    model: str
    success: bool = True
    error: str | None = None
    word_count: int = 0
    insufficient_context: bool = False

    @staticmethod
    def failure(error: str) -> NewsSummaryResult:
        """Create a failure result."""
        return NewsSummaryResult(
            summary="",
            confidence=0.0,
            model="unknown",
            success=False,
            error=error,
        )

    @staticmethod
    def no_context() -> NewsSummaryResult:
        """Create an insufficient context result."""
        return NewsSummaryResult(
            summary="",
            confidence=0.0,
            model="unknown",
            success=True,  # Not a failure, just insufficient content
            insufficient_context=True,
        )


def generate_news_summary(
    *,
    title: str,
    snippet: str | None = None,
    full_text: str | None = None,
    adapter: LLMAdapter | None = None,
) -> NewsSummaryResult:
    """Generate a brief summary for news articles and other non-paper sources.

    This is simpler than ELI5/ELI20 - just a factual summary of what the news is about.
    Returns insufficient_context=True if there's not enough information.

    Content selection (tiered):
    1. full_text if available and >= threshold
    2. snippet if >= threshold
    3. insufficient_context otherwise

    Args:
        title: Article title
        snippet: Article snippet/excerpt (may be None or short)
        full_text: Full article text if available (preferred over snippet)
        adapter: LLM adapter to use

    Returns:
        NewsSummaryResult with summary or insufficient_context flag
    """
    if not title:
        return NewsSummaryResult.failure("No title provided")

    # Tiered content selection: full_text → snippet → skip
    full_text_clean = (full_text or "").strip()
    snippet_clean = (snippet or "").strip()

    content_text: str | None = None
    content_source: str = ""

    if len(full_text_clean) >= NEWS_SUMMARY_MIN_CONTENT_CHARS:
        # Truncate full_text to reasonable length for LLM (first ~2000 chars)
        content_text = full_text_clean[:2000]
        content_source = "full_text"
    elif len(snippet_clean) >= NEWS_SUMMARY_MIN_CONTENT_CHARS:
        content_text = snippet_clean
        content_source = "snippet"
    else:
        logger.info(
            "News summary skipped: insufficient content (full_text=%d, snippet=%d chars < %d minimum)",
            len(full_text_clean),
            len(snippet_clean),
            NEWS_SUMMARY_MIN_CONTENT_CHARS,
        )
        return NewsSummaryResult.no_context()

    if adapter is None:
        adapter = get_llm_adapter()

    user_prompt = NEWS_SUMMARY_USER_PROMPT_TEMPLATE.format(
        title=title,
        content=content_text,
    )

    logger.debug("Generating news summary from %s (%d chars)", content_source, len(content_text))

    response = adapter.complete(
        user_prompt,
        system_prompt=NEWS_SUMMARY_SYSTEM_PROMPT,
        max_tokens=150,
        temperature=0.2,
    )

    if not response.success:
        return NewsSummaryResult.failure(response.error or "News summary generation failed")

    summary_text = _clean_output(response.text)

    # Check if LLM indicated insufficient context
    if INSUFFICIENT_CONTEXT_MARKER in summary_text.upper():
        logger.info("News summary: LLM indicated insufficient context for title: %s", title)
        return NewsSummaryResult.no_context()

    if not summary_text:
        return NewsSummaryResult.failure("News summary generation returned empty")

    word_count = _word_count(summary_text)
    new_digit_flag = _has_new_digits(f"{title} {content_text}", summary_text)

    # Simple confidence calculation
    confidence = 0.70
    if 30 <= word_count <= 60:
        confidence += 0.1
    elif word_count > 100 or word_count < 15:
        confidence -= 0.15
    if new_digit_flag:
        confidence -= 0.15  # Penalize hallucinated numbers

    confidence = max(0.0, min(1.0, confidence))

    return NewsSummaryResult(
        summary=summary_text,
        confidence=confidence,
        model=response.model,
        success=True,
        word_count=word_count,
    )
