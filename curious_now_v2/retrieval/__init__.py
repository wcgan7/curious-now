"""Full-text retrieval for Curious Now v2.

Retrieval fetches the text that grounds every generated presentation. A story
that cannot be explained is never published, so this layer decides what the
reader ever sees.
"""

from curious_now_v2.retrieval.fetch import (
    Fetcher,
    FetchOutcome,
    FetchResult,
    RobotsCache,
)

__all__ = [
    "FetchOutcome",
    "FetchResult",
    "Fetcher",
    "RobotsCache",
]
