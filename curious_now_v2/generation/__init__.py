"""Grounded generation for Curious Now v2.

Two steps, deliberately separate. First the evidence packet records which
claims the sources support, each behind a verbatim quote. Then the reader-facing
layers are written from those claims, not from the source at large.

Splitting them is what makes abstention checkable: absence of a mechanism claim
is a fact the pipeline can test, where a generator's sense of whether it could
explain something is not.
"""

from curious_now_v2.generation.client import (
    CodexGenerator,
    Completion,
    Generator,
    Usage,
)
from curious_now_v2.generation.packet import ExtractedPacket, extract_packet
from curious_now_v2.generation.present import (
    Presentation,
    generate_presentation,
    validate,
)

__all__ = [
    "CodexGenerator",
    "Completion",
    "ExtractedPacket",
    "Generator",
    "Presentation",
    "Usage",
    "extract_packet",
    "generate_presentation",
    "validate",
]
