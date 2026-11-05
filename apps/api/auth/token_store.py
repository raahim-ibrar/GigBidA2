"""Future encrypted per-user OAuth storage. Never fall back to plaintext."""


async def store_oauth_token(*, tenant_id: str, provider: str, token: str):
    raise NotImplementedError("Implement encryption, key validation and tenant-scoped storage")
