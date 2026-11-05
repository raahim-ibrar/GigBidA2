import hashlib
import hmac
import secrets
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from pwdlib import PasswordHash

PASSWORDS = PasswordHash.recommended()
DUMMY_HASH = PASSWORDS.hash("This dummy password is never used for an account")


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_for(token: str) -> str:
    return hmac.new(token.encode(), b"gigbid-csrf-v1", hashlib.sha256).hexdigest()


@dataclass
class Attempt:
    count: int
    expires: float


class AuthLimiter:
    """Bounded process-local limit. Use a Redis-wide limit before public deployment."""

    def __init__(self):
        self.attempts: dict[str, Attempt] = {}
        self.lock = Lock()

    def allow(self, key: str) -> bool:
        now = monotonic()
        with self.lock:
            self.attempts = {k: v for k, v in self.attempts.items() if v.expires > now}
            record = self.attempts.get(key)
            if record is None:
                if len(self.attempts) >= 10000:
                    return False
                record = self.attempts[key] = Attempt(0, now + 900)
            record.count += 1
            return record.count <= 20
