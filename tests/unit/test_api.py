def test_liveness_reports_foundation_stage(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "stage": "foundation"}


def test_status_does_not_claim_integrations_exist(client):
    response = client.get("/api/status")
    assert response.json()["stage"] == "foundation"
    assert "GigSim and Upwork adapters" in response.json()["pending"]


def test_no_fake_login(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "reviewer@example.org", "password": "valid-length-password"},
    )
    assert response.status_code == 401


def test_auth_denies_anonymous_reads_and_approvals(client):
    assert client.get("/api/jobs").status_code == 401
    response = client.post("/api/approvals", json={"thread_id": "other-user", "action": "approve"})
    assert response.status_code == 401


def test_openapi_exposes_approval_contract(client):
    schema = client.get("/openapi.json").json()
    assert "/api/approvals" in schema["paths"]
    request = schema["paths"]["/api/approvals"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    contract = schema["components"]["schemas"][request["$ref"].split("/")[-1]]
    assert {"run_id", "version", "draft_digest", "action"} <= set(contract["required"])
    assert contract["properties"]["action"]["enum"] == [
        "approve",
        "reject",
        "edit",
        "regenerate",
    ]
