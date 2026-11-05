"""Configurable variant registry. No retrieval quality is claimed by this scaffold."""

from importlib import import_module

VARIANTS = {
    "v0": "v0_naive",
    "v1": "v1_requirements",
    "v2": "v2_hybrid",
    "v3": "v3_reranker",
    "v8": "v8_corrective",
}


def get_retriever(variant: str):
    if variant not in VARIANTS:
        raise ValueError(f"Unknown retrieval variant: {variant}")
    return import_module(f"rag.variants.{VARIANTS[variant]}").retrieve
