"""Grounded generation for Curious Now v2.

The evidence packet classifies and records what the source can support. The
reader-facing layers are independent plain-text summaries of the retrieved
source itself; the packet routes depths but does not plan or constrain prose.
"""

from curious_now_v2.generation.client import (
    CodexGenerator,
    Completion,
    Generator,
    TextCompletion,
    Usage,
)
from curious_now_v2.generation.direct import DirectLayer, generate_layer
from curious_now_v2.generation.packet import ExtractedPacket, extract_packet

__all__ = [
    "CodexGenerator",
    "Completion",
    "DirectLayer",
    "ExtractedPacket",
    "Generator",
    "TextCompletion",
    "Usage",
    "extract_packet",
    "generate_layer",
]
