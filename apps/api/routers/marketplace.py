import asyncio

from fastapi import APIRouter, Request
from mcp.shared.memory import create_connected_server_and_client_session

from agent.marketplace_client import MarketplaceMCP
from apps.api.auth.dependencies import CurrentUser
from apps.api.schemas.marketplace import (
    ConnectionStatus,
    ConnectionUpdate,
    ImportedJobs,
    MarketplaceSearch,
    SyncResult,
)
from mcp_servers.marketplace.adapters.student_sim import MarketplaceRejected, MarketplaceUnavailable
from mcp_servers.marketplace.factory import create_marketplace_server
from mcp_servers.marketplace.service import MarketplaceService

router = APIRouter(tags=["marketplace"])


@router.get("/marketplace", response_model=ConnectionStatus)
async def status(user: CurrentUser, request: Request):
    accounts = request.app.state.marketplace
    result = await asyncio.to_thread(accounts.status, user.id)
    if result["mode"] == "upwork":
        # Status polling never polls the remote marketplace or financial endpoint.
        result["available"] = result["connected"] and not result["error"]
        return result
    if result["connected"]:
        try:
            result["balance"] = (await accounts.adapter(user.id).get_connects_balance()).data[
                "connects"
            ]
            result["available"], result["error"] = True, None
        except (MarketplaceUnavailable, MarketplaceRejected):
            result["available"] = False
            result["error"] = (
                "Student simulator unavailable. Saved jobs, approvals and drafts remain available."
            )
    return result


@router.put("/marketplace", response_model=ConnectionStatus)
async def connect(body: ConnectionUpdate, user: CurrentUser, request: Request):
    accounts = request.app.state.marketplace
    if body.mode == "student_sim":
        await accounts.adapter(user.id, "student_sim").get_connects_balance()
    await asyncio.to_thread(accounts.set_mode, user.id, body.mode)
    return await status(user, request)


@router.post("/marketplace/search", response_model=ImportedJobs)
async def search(body: MarketplaceSearch, user: CurrentUser, request: Request):
    app = request.app
    service = MarketplaceService(
        app.state.engine,
        app.state.settings,
        user.id,
        adapter=app.state.marketplace.adapter(user.id),
    )
    server = create_marketplace_server(service, user.id)
    try:
        async with create_connected_server_and_client_session(server) as session:
            result = await MarketplaceMCP(session).search(body.query, body.limit)
    except (MarketplaceUnavailable, MarketplaceRejected):
        await asyncio.to_thread(
            app.state.marketplace.failure,
            user.id,
            "Marketplace unavailable or authorization requires reconnect",
        )
        raise
    jobs = [
        await asyncio.to_thread(app.state.marketplace.import_job, user.id, item)
        for item in result["items"]
    ]
    await asyncio.to_thread(app.state.marketplace.failure, user.id, "")
    return {
        "jobs": [job.model_dump(mode="json") for job in jobs],
        "synthetic": service.provider != "upwork",
        "provider": service.provider,
    }


@router.get("/marketplace/balance")
async def balance(user: CurrentUser, request: Request):
    accounts = request.app.state.marketplace
    if not accounts.status(user.id)["connected"]:
        from agent.run_store import RunConflict

        raise RunConflict("Connect the student simulator first")
    return (await accounts.adapter(user.id).get_connects_balance()).data


@router.delete("/marketplace/upwork", response_model=ConnectionStatus)
async def disconnect_upwork(user: CurrentUser, request: Request):
    from apps.api.auth.token_store import EncryptedTokenStorage

    store = EncryptedTokenStorage(request.app.state.engine, request.app.state.settings, user.id)
    data = await asyncio.to_thread(store.read)
    await asyncio.to_thread(store.disconnect)
    # Erase/fence locally first; provider revocation is best-effort and never restores access.
    import httpx

    try:
        token = data.get("tokens", {}).get("refresh_token") or data.get("tokens", {}).get(
            "access_token"
        )
        if token:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    "https://www.upwork.com/api/v3/oauth2/token/revoke",
                    data={"token": token, "client_id": data.get("client", {}).get("client_id", "")},
                )
    except httpx.HTTPError:
        pass
    if request.app.state.marketplace.status(user.id)["mode"] == "upwork":
        await asyncio.to_thread(request.app.state.marketplace.set_mode, user.id, "manual")
    return await status(user, request)


@router.post("/marketplace/sync", response_model=SyncResult)
async def sync(user: CurrentUser, request: Request):
    from worker.simulator_sync import sync_account

    return await sync_account(
        request.app.state.engine,
        request.app.state.settings,
        user.id,
        enqueue=request.app.state.enqueue_run,
    )
