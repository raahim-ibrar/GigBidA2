"""Implement separate tenant-scoped LangGraph store namespaces for style and outcomes."""


def memory_namespace(tenant_id: str, kind: str) -> tuple[str, str]:
    if not tenant_id or kind not in {"style", "outcome"}:
        raise ValueError("A tenant and a valid memory kind are required")
    return tenant_id, kind


async def promote_memory(*args, **kwargs):
    raise NotImplementedError("Connect a LangGraph store and enforce promotion_rules first")
