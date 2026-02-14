"""Extraction pipelines for paper source content (HTML/PDF/arXiv)."""

from curious_now.extractors.paper_sources import (
    extract_arxiv_html_body_text,
    extract_arxiv_html_image_url,
    extract_html_body_text,
    extract_html_image_url,
    extract_pdf_text,
    fetch_arxiv_html_full_text,
    fetch_arxiv_pdf_full_text,
    fetch_pdf_text,
)

__all__ = [
    "extract_arxiv_html_body_text",
    "extract_arxiv_html_image_url",
    "extract_html_body_text",
    "extract_html_image_url",
    "extract_pdf_text",
    "fetch_arxiv_html_full_text",
    "fetch_arxiv_pdf_full_text",
    "fetch_pdf_text",
]
