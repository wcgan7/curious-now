"""Full-text retrieval for Curious Now v2.

Retrieval fetches the text that grounds every generated presentation. A story
that cannot be explained is never published, so this layer decides what the
reader ever sees.

Extraction preserves structure rather than flattening to a blob: Technical is
required to cite the sections, figures, and tables it draws on, and Explain is
eligible only when the sources carry a mechanism to explain.
"""

from curious_now_v2.retrieval.document import (
    Document,
    Figure,
    Section,
    SectionKind,
    Table,
    classify_section,
    inherit_section_kinds,
)
from curious_now_v2.retrieval.extract_article import extract_article
from curious_now_v2.retrieval.extract_arxiv import extract_arxiv_html
from curious_now_v2.retrieval.extract_jats import extract_jats
from curious_now_v2.retrieval.extract_pdf import extract_pdf
from curious_now_v2.retrieval.fetch import (
    Fetcher,
    FetchOutcome,
    FetchResult,
    RobotsCache,
)
from curious_now_v2.retrieval.quality import (
    TextAssessment,
    TextVerdict,
    assess_text,
)
from curious_now_v2.retrieval.resolve import (
    Resolution,
    ResolutionStatus,
    TextKind,
    resolve_item_text,
)
from curious_now_v2.retrieval.select import score_document

__all__ = [
    "Document",
    "FetchOutcome",
    "FetchResult",
    "Fetcher",
    "Figure",
    "RobotsCache",
    "Section",
    "SectionKind",
    "Table",
    "TextAssessment",
    "TextVerdict",
    "Resolution",
    "ResolutionStatus",
    "TextKind",
    "assess_text",
    "classify_section",
    "extract_article",
    "extract_arxiv_html",
    "extract_jats",
    "extract_pdf",
    "inherit_section_kinds",
    "resolve_item_text",
    "score_document",
]
