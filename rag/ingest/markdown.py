"""Markdown case studies and reviews."""

from rag.ingest.parse import parse_document


def load(content: bytes):
    return parse_document("case.md", content)
