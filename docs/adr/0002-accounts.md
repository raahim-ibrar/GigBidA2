# ADR 0002: Accounts and persistent profile settings

Use SQLAlchemy with explicit Alembic migrations and Postgres in development/deployment. SQLite is a fallback only for isolated local tests and the disposable browser test server.

The API owns opaque cookie sessions. Store only token digests, expire sessions and revoke them on sign-out. Browser storage does not contain a bearer token. Use Argon2 via pwdlib for passwords, as illustrated in the official FastAPI security documentation. Authenticated mutations require a session-specific CSRF token; browser Origins must match the configured frontend. Cookies are HttpOnly and SameSite=Lax, with Secure required in production.

Each individual freelancer account owns a tenant. The profile endpoints derive ownership from the authenticated user and accept no target user ID. Future portfolio, job, run, approval and memory records must follow the same ownership discipline; those features are not implemented yet.

The initial authentication rate limiter is bounded and process-local. It is sufficient for local development but must become Redis-backed, proxy-aware and shared across instances before public deployment. Email verification, account recovery and deployment hardening are also pending.

References: [SQLAlchemy sessions](https://docs.sqlalchemy.org/en/20/orm/session_basics.html), [FastAPI password hashing](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/), [Alembic migrations](https://alembic.sqlalchemy.org/en/latest/tutorial.html).
