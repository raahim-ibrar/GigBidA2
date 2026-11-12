"""Authenticated encryption with tenant/provider binding and revocation fencing."""

import asyncio
import json
from datetime import datetime, timedelta
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy.orm import Session

from apps.api.models import OAuthCredential, utcnow


class OAuthUnavailable(RuntimeError):
    pass


class EncryptedTokenStorage:
    def __init__(self, engine, settings, tenant, *, generation=None, allow_create=False):
        try:
            self.cipher = Fernet(settings.oauth_encryption_key.get_secret_value().encode())
        except (ValueError, TypeError):
            raise OAuthUnavailable(
                "Configure a valid OAUTH_ENCRYPTION_KEY before connecting Upwork"
            ) from None
        self.engine, self.tenant = engine, tenant
        self.generation, self.allow_create = generation, allow_create

    def _decode(self, row):
        try:
            value = json.loads(self.cipher.decrypt(row.encrypted_payload.encode()))
            if value["tenant"] != self.tenant or value["provider"] != "upwork":
                raise ValueError()
            return value
        except (InvalidToken, ValueError, KeyError):
            raise OAuthUnavailable(
                "Stored Upwork authorization cannot be decrypted; reconnect"
            ) from None

    def read(self):
        with Session(self.engine) as db:
            row = db.get(OAuthCredential, (self.tenant, "upwork"))
            if not row:
                return {}
            if self.generation and row.generation != self.generation:
                raise OAuthUnavailable("Upwork connection changed; reconnect or restart this run")
            self.generation = row.generation
            return self._decode(row)

    def update(self, values):
        with Session(self.engine) as db, db.begin():
            row = db.get(OAuthCredential, (self.tenant, "upwork"), with_for_update=True)
            if row is None:
                if not self.allow_create:
                    raise OAuthUnavailable("Connect Upwork on the host laptop first")
                row = OAuthCredential(
                    user_id=self.tenant,
                    provider="upwork",
                    generation=str(uuid4()),
                    connected=False,
                    schema_snapshot=[],
                    capabilities={},
                )
                value = {"tenant": self.tenant, "provider": "upwork"}
                db.add(row)
            else:
                if self.generation and row.generation != self.generation:
                    raise OAuthUnavailable("Upwork connection was disconnected or replaced")
                value = self._decode(row)
            self.generation = row.generation
            value.update(values)
            row.encrypted_payload = self.cipher.encrypt(json.dumps(value).encode()).decode()
            row.updated_at = utcnow()

    async def get_tokens(self):
        data = await asyncio.to_thread(self.read)
        if not data.get("tokens"):
            return None
        tokens = dict(data["tokens"])
        if data.get("expires_at"):
            tokens["expires_in"] = max(
                0, int((datetime.fromisoformat(data["expires_at"]) - utcnow()).total_seconds())
            )
        return OAuthToken.model_validate(tokens)

    async def set_tokens(self, tokens):
        expiry = (
            (utcnow() + timedelta(seconds=tokens.expires_in)).isoformat()
            if tokens.expires_in is not None
            else None
        )
        previous = await asyncio.to_thread(self.read)
        body = tokens.model_dump(mode="json")
        if not body.get("refresh_token"):
            body["refresh_token"] = previous.get("tokens", {}).get("refresh_token")
        await asyncio.to_thread(self.update, {"tokens": body, "expires_at": expiry})

    async def get_client_info(self):
        data = await asyncio.to_thread(self.read)
        return (
            OAuthClientInformationFull.model_validate(data["client"])
            if data.get("client")
            else None
        )

    async def set_client_info(self, client_info):
        await asyncio.to_thread(self.update, {"client": client_info.model_dump(mode="json")})

    def disconnect(self):
        with Session(self.engine) as db, db.begin():
            row = db.get(OAuthCredential, (self.tenant, "upwork"), with_for_update=True)
            if row:
                row.generation = str(uuid4())
                row.connected, row.schema_snapshot, row.capabilities = False, [], {}
                row.encrypted_payload = self.cipher.encrypt(
                    json.dumps({"tenant": self.tenant, "provider": "upwork"}).encode()
                ).decode()
                row.updated_at = utcnow()
