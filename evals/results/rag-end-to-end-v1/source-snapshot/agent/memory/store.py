"""Separate logical stores; infrastructure owns persistence, agents receive promoted values."""


def memory_namespace(tenant_id: str, kind: str) -> tuple[str, str]:
    if not tenant_id or kind not in {"style", "outcome"}:
        raise ValueError("A tenant and a valid memory kind are required")
    return tenant_id, kind


async def promote_memory(
    service, tenant_id, kind, *, key=None, confirmed=False, category=None, outcome=None
):
    import asyncio

    memory_namespace(tenant_id, kind)
    if kind == "style":
        return await asyncio.to_thread(service.confirm_style, tenant_id, key, confirmed=confirmed)
    return await asyncio.to_thread(service.promote_outcome, tenant_id, category, outcome)
