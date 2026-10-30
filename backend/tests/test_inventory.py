"""Persistent DEMO inventory contracts through the authenticated API."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from test_auth import USER, bearer, login


@pytest.fixture
def settings(tmp_path):
    from test_auth import BOT_TOKEN
    return Settings(bot_token=BOT_TOKEN,
                    database_url=f"sqlite:///{(tmp_path / 'inventory.sqlite3').as_posix()}",
                    allowed_origins=('http://localhost:5173',))


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        client.headers.update(bearer(login(client)["access_token"]))
        yield client


def snapshot(client):
    response = client.get("/api/inventory")
    assert response.status_code == 200, response.text
    return response.json()


def post(client, action, body, key="test-key"):
    return client.post(f"/api/inventory/demo-{action}", json=body,
                       headers={"Idempotency-Key": key})


def test_seed_once_even_after_emptying_and_restart(client, settings):
    original = snapshot(client)
    assert len(original["inventory"]) == 5
    assert original["pledged"] == []
    assert [g["pledgeSupported"] for g in original["inventory"]] == [True] * 3 + [False] * 2
    assert [g["catalogId"] for g in original["inventory"]] == [g["id"] for g in original["catalog"][:5]]
    assert snapshot(client) == original
    ids = [g["id"] for g in original["inventory"]]
    assert post(client, "withdraw", {"ids": ids}).status_code == 200
    assert snapshot(client)["inventory"] == []
    with TestClient(create_app(settings)) as reopened:
        reopened.headers.update({"Authorization": client.headers["Authorization"]})
        assert snapshot(reopened)["inventory"] == []


def test_deposit_receipt_persists_and_conflicts(client, settings):
    before = snapshot(client)
    response = post(client, "deposit", {})
    assert response.status_code == 200, response.text
    after = response.json()
    assert len(after["inventory"]) == len(before["inventory"]) + 1
    assert post(client, "deposit", {}).json() == after
    assert post(client, "withdraw", {"ids": [after["inventory"][0]["id"]]}).status_code == 409
    # Retry A after B returns B's canonical state without another deposit.
    later = post(client, "deposit", {}, key="later")
    assert later.status_code == 200
    assert post(client, "deposit", {}).json() == later.json()
    with TestClient(create_app(settings)) as reopened:
        reopened.headers.update({"Authorization": client.headers["Authorization"]})
        assert post(reopened, "deposit", {}).json() == later.json()
        assert len(snapshot(reopened)["inventory"]) == 7


def test_actor_ownership_and_per_user_keys(client):
    first = snapshot(client)
    first_headers = client.headers["Authorization"]
    other = login(client, {**USER, "id": USER["id"] + 1})
    client.headers.update(bearer(other["access_token"]))
    second = snapshot(client)
    assert set(g["id"] for g in first["inventory"]).isdisjoint(g["id"] for g in second["inventory"])
    foreign = first["inventory"][0]["id"]
    for action, body in [
        ("withdraw", {"ids": [second["inventory"][0]["id"], foreign]}),
        ("exchange", {"offered_ids": [foreign], "received_ids": [second["catalog"][1]["id"]]}),
        ("pledge", {"id": foreign}), ("release", {"id": foreign}),
    ]:
        assert post(client, action, body).status_code == 409
        assert snapshot(client) == second
    assert post(client, "deposit", {}).status_code == 200
    client.headers["Authorization"] = first_headers
    assert snapshot(client) == first
    assert post(client, "deposit", {}).status_code == 200


def test_pledge_release_and_reserved_restrictions(client):
    before = snapshot(client)
    supported = before["inventory"][0]["id"]
    unsupported = before["inventory"][-1]["id"]
    assert post(client, "pledge", {"id": unsupported}).status_code == 409
    assert snapshot(client) == before
    response = post(client, "pledge", {"id": supported}, key="pledge")
    assert response.status_code == 200
    pledged = response.json()
    assert [g["id"] for g in pledged["pledged"]] == [supported]
    for action, body in [
        ("withdraw", {"ids": [unsupported, supported]}),
        ("exchange", {"offered_ids": [supported], "received_ids": [before["catalog"][1]["id"]]}),
        ("pledge", {"id": supported}),
    ]:
        assert post(client, action, body, key="reserved-" + action).status_code == 409
        assert snapshot(client) == pledged
    released = post(client, "release", {"id": supported}, key="release")
    assert released.status_code == 200
    assert released.json() == before
    assert post(client, "release", {"id": supported}, key="again").status_code == 409


def test_exchange_server_templates_atomic_and_idempotent(client):
    before = snapshot(client)
    offered = before["inventory"][0]["id"]
    blocked, allowed = [g["id"] for g in before["catalog"][:2]]
    assert before["catalog"][0]["blockTradeGift"] is True
    for received in ([allowed, blocked], [allowed, 999999999], [allowed, allowed]):
        response = post(client, "exchange", {"offered_ids": [offered], "received_ids": received})
        assert response.status_code in {409, 422}
        assert snapshot(client) == before
    body = {"offered_ids": [offered], "received_ids": [allowed]}
    response = post(client, "exchange", body)
    assert response.status_code == 200, response.text
    after = response.json()
    assert len(after["inventory"]) == 5
    assert offered not in [g["id"] for g in after["inventory"]]
    new = after["inventory"][-1]
    assert new["catalogId"] == allowed
    assert new["name"] == before["catalog"][1]["name"]
    assert new["id"] not in [g["id"] for g in before["inventory"]]
    assert post(client, "exchange", body).json() == after
    assert post(client, "exchange", {**body, "received_ids": [before["catalog"][2]["id"]]}).status_code == 409
    assert snapshot(client) == after


def test_replay_does_not_resurrect_gift_removed_by_later_mutation(client):
    snapshot(client)
    deposited = post(client, "deposit", {}, key="A")
    assert deposited.status_code == 200
    gift_id = deposited.json()["inventory"][-1]["id"]
    withdrawn = post(client, "withdraw", {"ids": [gift_id]}, key="B")
    assert withdrawn.status_code == 200
    replay = post(client, "deposit", {}, key="A")
    assert replay.status_code == 200
    assert replay.json() == withdrawn.json() == snapshot(client)
    assert gift_id not in [g["id"] for g in replay.json()["inventory"]]


@pytest.mark.parametrize("action,body", [
    ("deposit", {"id": 1}), ("withdraw", {"ids": []}),
    ("withdraw", {"ids": [1, 1]}), ("withdraw", {"ids": [1, 999999999]}),
    ("withdraw", {"ids": [True]}), ("withdraw", {"ids": ["1"]}),
    ("withdraw", {"ids": [-1]}), ("withdraw", {"ids": [0]}),
    ("exchange", {"offered_ids": [], "received_ids": [2]}),
    ("exchange", {"offered_ids": [1], "received_ids": []}),
    ("exchange", {"offered_ids": [1, 1], "received_ids": [2]}),
    ("pledge", {"id": 1, "price": "0"}), ("release", {"id": None}),
])
def test_invalid_mutations_are_atomic(client, action, body):
    before = snapshot(client)
    response = post(client, action, body)
    assert response.status_code in {409, 422}, response.text
    assert snapshot(client) == before
    # Rejection must not consume the key.
    assert post(client, "deposit", {}).status_code == 200


@pytest.mark.parametrize("action,body", [
    ("deposit", {}), ("withdraw", {"ids": [1]}),
    ("exchange", {"offered_ids": [1], "received_ids": [2]}),
    ("pledge", {"id": 1}), ("release", {"id": 1}),
])
def test_mutations_require_idempotency_key(client, action, body):
    before = snapshot(client)
    response = client.post(f"/api/inventory/demo-{action}", json=body)
    assert response.status_code == 422
    assert snapshot(client) == before


def test_inventory_requires_authentication(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/inventory").status_code == 401
        assert post(client, "deposit", {}).status_code == 401


def test_inventory_mutation_cors_preflight(client):
    response = client.options('/api/inventory/demo-deposit', headers={
        'Origin': 'http://localhost:5173',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'authorization,content-type,idempotency-key',
    })
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
    denied = client.options('/api/inventory/demo-deposit', headers={
        'Origin': 'https://untrusted.example',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'authorization,idempotency-key',
    })
    assert denied.status_code == 400
