"""Citation validation for AI-generated content.

This module verifies that claims in AI-generated takeaways and deep-dives
are supported by the source material, flagging potential overstatements.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from curious_now.ai.llm_adapter import LLMAdapter, LLMResponse, get_llm_adapter

logger = logging.getLogger(__name__)


class FlagType(str, Enum):
    """Types of citation flags."""

    OVERSTATEMENT = "overstatement"
    UNSUPPORTED = "unsupported"
    MISATTRIBUTION = "misattribution"
    SPECULATION = "speculation"
    HYPE = "hype"


@dataclass
class CitationFlag:
    """A flag indicating a potential issue with a claim."""

    flag_type: FlagType
    claim: str
    issue: str
    suggestion: str | None = None


@dataclass
class CheckedClaim:
    """A claim that has been validated against sources."""

    claim: str
    supported: bool
    source: str | None = None
    confidence: float = 1.0


@dataclass
class CitationCheckInput:
    """Input data for citation checking."""

    generated_content: str
    source_texts: list[SourceText]
    content_type: str = "takeaway"  # takeaway, intuition, deep_dive


@dataclass
class SourceText:
    """A source text to validate against."""

    text: str
    source_name: str
    source_type: str | None = None  # journalism, journal, preprint


@dataclass
class CitationCheckResult:
    """Result of citation validation."""

    validated: bool
    confidence: float
    flags: list[CitationFlag]
    checked_claims: list[CheckedClaim]
    model: str
    success: bool = True
    error: str | None = None

    @staticmethod
    def failure(error: str) -> CitationCheckResult:
        """Create a failure result."""
        return CitationCheckResult(
            validated=False,
            confidence=0.0,
            flags=[],
            checked_claims=[],
            model="unknown",
            success=False,
            error=error,
        )


CITATION_CHECK_SYSTEM_PROMPT = """You are a fact-checker verifying AI-generated \
science summaries against source material.

Your job is to:
1. Extract key claims from the generated content
2. Check if each claim is supported by the source material
3. Flag any overstatements, unsupported claims, or hype

Be strict but fair:
- A claim is "supported" if the source material contains the same information
- Minor phrasing differences are OK if the meaning is preserved
- Flag claims that go beyond what sources say
- Flag use of hype words (breakthrough, revolutionary, cure, miracle)"""


CITATION_CHECK_USER_PROMPT_TEMPLATE = """Validate this {content_type} against the source material.

Generated Content:
{generated_content}

Source Material:
{source_texts}

Analyze the generated content and respond with a JSON object:
{{
  "validated": true/false,
  "overall_confidence": 0.0-1.0,
  "claims": [
    {{
      "claim": "the specific claim text",
      "supported": true/false,
      "source": "name of supporting source or null",
      "confidence": 0.0-1.0
    }}
  ],
  "flags": [
    {{
      "type": "overstatement|unsupported|misattribution|speculation|hype",
      "claim": "the problematic claim",
      "issue": "description of the problem",
      "suggestion": "how to fix it"
    }}
  ]
}}

Set "validated" to true if no major issues found.
Set "validated" to false if any unsupported or significantly overstated claims.

Respond with ONLY the JSON object."""


def _format_source_texts(sources: list[SourceText]) -> str:
    """Format source texts for the prompt."""
    formatted = ""
    for i, source in enumerate(sources, 1):
        header = f"{i}. {source.source_name}"
        if source.source_type:
            header += f" ({source.source_type})"
        text = source.text[:800] + "..." if len(source.text) > 800 else source.text
        formatted += f"{header}:\n{text}\n\n"
    return formatted


def _parse_citation_check_json(text: str) -> dict[str, Any] | None:
    """Parse citation check JSON from LLM response."""
    text = text.strip()

    # Handle markdown code blocks
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse citation check JSON: %s", e)
        return None


def _parse_flag(flag_data: dict[str, Any]) -> CitationFlag | None:
    """Parse a flag from JSON data."""
    flag_type_str = flag_data.get("type", "")
    try:
        flag_type = FlagType(flag_type_str)
    except ValueError:
        flag_type = FlagType.UNSUPPORTED

    claim = flag_data.get("claim", "")
    issue = flag_data.get("issue", "")

    if not claim or not issue:
        return None

    return CitationFlag(
        flag_type=flag_type,
        claim=claim,
        issue=issue,
        suggestion=flag_data.get("suggestion"),
    )


def _parse_checked_claim(claim_data: dict[str, Any]) -> CheckedClaim | None:
    """Parse a checked claim from JSON data."""
    claim = claim_data.get("claim", "")
    if not claim:
        return None

    return CheckedClaim(
        claim=claim,
        supported=bool(claim_data.get("supported", False)),
        source=claim_data.get("source"),
        confidence=float(claim_data.get("confidence", 0.5)),
    )


def check_citations(
    input_data: CitationCheckInput,
    *,
    adapter: LLMAdapter | None = None,
) -> CitationCheckResult:
    """
    Validate AI-generated content against source material.

    Args:
        input_data: The content and sources to validate
        adapter: LLM adapter to use (defaults to configured adapter)

    Returns:
        CitationCheckResult with validation results
    """
    if not input_data.generated_content:
        return CitationCheckResult.failure("No generated content provided")

    if not input_data.source_texts:
        return CitationCheckResult.failure("No source texts provided")

    # Get adapter
    if adapter is None:
        adapter = get_llm_adapter()

    # Build the prompt
    source_texts = _format_source_texts(input_data.source_texts)

    user_prompt = CITATION_CHECK_USER_PROMPT_TEMPLATE.format(
        content_type=input_data.content_type,
        generated_content=input_data.generated_content,
        source_texts=source_texts,
    )

    # Try complete_json first for reliable JSON parsing
    raw_json = adapter.complete_json(
        user_prompt,
        system_prompt=CITATION_CHECK_SYSTEM_PROMPT,
        max_tokens=1000,
    )

    # Get model name for result
    model_name = getattr(adapter, "model", adapter.name)

    if raw_json is None:
        # Fallback: try regular complete with manual parsing
        response: LLMResponse = adapter.complete(
            user_prompt,
            system_prompt=CITATION_CHECK_SYSTEM_PROMPT,
            max_tokens=1000,
            temperature=0.3,  # Low temp for consistent validation
        )

        if not response.success:
            logger.warning("Citation check failed: %s", response.error)
            return CitationCheckResult.failure(response.error or "Unknown error")

        model_name = response.model
        raw_json = _parse_citation_check_json(response.text)
        if raw_json is None:
            return CitationCheckResult.failure("Failed to parse JSON response")

    # Extract results
    validated = bool(raw_json.get("validated", False))
    confidence = float(raw_json.get("overall_confidence", 0.5))

    # Parse flags
    flags: list[CitationFlag] = []
    for flag_data in raw_json.get("flags", []):
        flag = _parse_flag(flag_data)
        if flag:
            flags.append(flag)

    # Parse checked claims
    checked_claims: list[CheckedClaim] = []
    for claim_data in raw_json.get("claims", []):
        claim = _parse_checked_claim(claim_data)
        if claim:
            checked_claims.append(claim)

    # Recalculate validation based on flags
    has_critical_flags = any(
        f.flag_type in (FlagType.UNSUPPORTED, FlagType.OVERSTATEMENT)
        for f in flags
    )
    if has_critical_flags and validated:
        validated = False

    return CitationCheckResult(
        validated=validated,
        confidence=confidence,
        flags=flags,
        checked_claims=checked_claims,
        model=model_name,
        success=True,
    )


def check_takeaway_citations(
    takeaway: str,
    sources: list[dict[str, Any]],
    *,
    adapter: LLMAdapter | None = None,
) -> CitationCheckResult:
    """
    Convenience function to check a takeaway against sources.

    Args:
        takeaway: The generated takeaway text
        sources: List of source dicts with 'text', 'source_name', 'source_type'
        adapter: LLM adapter to use

    Returns:
        CitationCheckResult with validation results
    """
    source_texts = [
        SourceText(
            text=s.get("text", s.get("snippet", "")),
            source_name=s.get("source_name", "Unknown"),
            source_type=s.get("source_type"),
        )
        for s in sources
        if s.get("text") or s.get("snippet")
    ]

    input_data = CitationCheckInput(
        generated_content=takeaway,
        source_texts=source_texts,
        content_type="takeaway",
    )

    return check_citations(input_data, adapter=adapter)


def check_deep_dive_citations(
    deep_dive_content: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    adapter: LLMAdapter | None = None,
) -> CitationCheckResult:
    """
    Convenience function to check deep-dive content against sources.

    Args:
        deep_dive_content: The deep-dive JSON content
        sources: List of source dicts with 'text', 'source_name', 'source_type'
        adapter: LLM adapter to use

    Returns:
        CitationCheckResult with validation results
    """
    # Combine deep-dive sections for checking
    sections = []
    for key in ["what_happened", "why_it_matters", "background", "whats_next"]:
        if key in deep_dive_content:
            sections.append(f"{key}: {deep_dive_content[key]}")

    if "limitations" in deep_dive_content:
        limitations = deep_dive_content["limitations"]
        if isinstance(limitations, list):
            sections.append("Limitations: " + "; ".join(limitations))

    combined_content = "\n\n".join(sections)

    source_texts = [
        SourceText(
            text=s.get("text", s.get("snippet", "")),
            source_name=s.get("source_name", "Unknown"),
            source_type=s.get("source_type"),
        )
        for s in sources
        if s.get("text") or s.get("snippet")
    ]

    input_data = CitationCheckInput(
        generated_content=combined_content,
        source_texts=source_texts,
        content_type="deep_dive",
    )

    return check_citations(input_data, adapter=adapter)


def citation_check_to_json(result: CitationCheckResult) -> dict[str, Any]:
    """Convert CitationCheckResult to JSON-serializable dict for storage."""
    return {
        "validated": result.validated,
        "confidence": result.confidence,
        "flags": [
            {
                "type": f.flag_type.value,
                "claim": f.claim,
                "issue": f.issue,
                "suggestion": f.suggestion,
            }
            for f in result.flags
        ],
        "checked_claims": [
            {
                "claim": c.claim,
                "supported": c.supported,
                "source": c.source,
                "confidence": c.confidence,
            }
            for c in result.checked_claims
        ],
    }
