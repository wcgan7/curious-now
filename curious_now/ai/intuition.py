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
