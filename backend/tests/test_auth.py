"""Black-box auth contract tests; no environment files or model internals needed."""

import hashlib
import hmac
import json
import time
from dataclasses import replace
from urllib.parse import parse_qsl, urlencode

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


BOT_TOKEN = "123456789:TEST_ONLY_BOT_SECRET_DO_NOT_RETURN"
USER = {
    "id": 9876543210,
    "first_name": "Alice + & = /",
    "last_name": "Example",
    "username": "alice_example",
    "language_code": "en",
}


def signed(fields, token=BOT_TOKEN):
    # Independent Telegram signer: HMAC key and message order are significant.
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode([*fields.items(), ("hash", digest)])


def fields_for(user=USER, age=0):
    return {
        "query_id": "TEST_QUERY_PRIVATE_SENTINEL",
        "user": json.dumps(user, ensure_ascii=True, separators=(",", ":")),
        "auth_date": str(int(time.time()) - age),
    }


@pytest.fixture
def settings(tmp_path):
    return Settings(
        bot_token=BOT_TOKEN,
        database_url=f"sqlite:///{(tmp_path / 'auth.sqlite3').as_posix()}",
        allowed_origins=("http://localhost:5173",),
        init_data_max_age=300,
        session_ttl=86400,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def assert_no_secrets(response, init_data=None, access_token=None):
    body = response.text
    for secret in (BOT_TOKEN, "TEST_QUERY_PRIVATE_SENTINEL", init_data, access_token):
        if secret:
            assert secret not in body
    if init_data:
        digest = dict(parse_qsl(init_data)).get("hash")
        if digest:
            assert digest not in body
    if response.content:
        payload = response.json()
        forbidden = {"bot_token", "init_data", "token_hash", "session_hash", "hash"}

        def check(value):
            if isinstance(value, dict):
                assert forbidden.isdisjoint(value)
                for item in value.values():
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)

        check(payload)


def login(client, user=USER, *, init_data=None):
    if init_data is None:
        init_data = signed(fields_for(user))
    response = client.post("/api/auth/telegram", json={"init_data": init_data})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload["access_token"], str) and payload["access_token"]
    assert isinstance(payload["user"], dict)
    assert_no_secrets(response, init_data)
    return payload


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_valid_telegram_login_and_authenticated_me(client):
    payload = login(client)
    assert payload["user"]["first_name"] == USER["first_name"]
    assert payload["user"]["username"] == USER["username"]
    response = client.get("/api/me", headers=bearer(payload["access_token"]))
    assert response.status_code == 200, response.text
    assert response.json() == payload["user"]
    assert_no_secrets(response, access_token=payload["access_token"])


def test_user_is_persisted_and_updated_without_changing_identity(settings):
    with TestClient(create_app(settings)) as first:
        original = login(first)
    updated_user = {**USER, "first_name": "Updated", "username": "updated_alice"}
    with TestClient(create_app(settings)) as second:
        # A fresh app must recover both the session and user from the database.
        persisted = second.get("/api/me", headers=bearer(original["access_token"]))
        assert persisted.status_code == 200, persisted.text
        assert persisted.json() == original["user"]
        updated = login(second, updated_user)
        assert updated["user"]["id"] == original["user"]["id"]
        assert updated["user"]["first_name"] == "Updated"
        assert updated["user"]["username"] == "updated_alice"
        current = second.get("/api/me", headers=bearer(original["access_token"]))
        assert current.status_code == 200
        assert current.json() == updated["user"]
    with TestClient(create_app(settings)) as third:
        response = third.get("/api/me", headers=bearer(updated["access_token"]))
        assert response.status_code == 200
        assert response.json() == updated["user"]


def invalid_init_data(case):
    fields = fields_for()
    if case == "tampered_user":
        pairs = dict(parse_qsl(signed(fields)))
        pairs["user"] = json.dumps({**USER, "id": 42})
        return urlencode(pairs)
    if case == "wrong_bot":
        return signed(fields, token="other-bot-token")
    if case in {"expired", "future"}:
        return signed(fields_for(age=600 if case == "expired" else -3600))
    if case == "missing_user":
        del fields["user"]
    elif case == "missing_auth_date":
        del fields["auth_date"]
    elif case == "invalid_auth_date":
        fields["auth_date"] = "not-a-timestamp"
    elif case == "malformed_user":
        fields["user"] = '{"id":'
    elif case == "null_user":
        fields["user"] = "null"
    elif case == "array_user":
        fields["user"] = "[]"
    elif case == "missing_user_id":
        fields["user"] = '{"first_name":"Alice"}'
    elif case == "invalid_user_id":
        fields["user"] = '{"id":"not-an-id","first_name":"Alice"}'
    raw = signed(fields)
    pairs = list(parse_qsl(raw))
    if case == "missing_hash":
        return urlencode([(key, value) for key, value in pairs if key != "hash"])
    if case in {"empty_hash", "malformed_hash", "incorrect_hash"}:
        replacement = {"empty_hash": "", "malformed_hash": "z" * 64,
                       "incorrect_hash": "0" * 64}[case]
        return urlencode([(key, replacement if key == "hash" else value)
                          for key, value in pairs])
    if case.startswith("duplicate_"):
        key = case.removeprefix("duplicate_")
        return raw + "&" + urlencode({key: dict(pairs)[key]})
    if case == "empty":
        return ""
    if case == "malformed_query":
        return "user=%ZZ&auth_date&hash=broken"
    return raw


@pytest.mark.parametrize("case", [
    "tampered_user", "wrong_bot", "expired", "future", "missing_user",
    "missing_auth_date", "invalid_auth_date", "malformed_user", "null_user",
    "array_user", "missing_user_id", "invalid_user_id", "missing_hash",
    "empty_hash", "malformed_hash", "incorrect_hash", "duplicate_user",
    "duplicate_auth_date", "duplicate_query_id", "duplicate_hash", "empty",
    "malformed_query",
])
def test_invalid_telegram_data_is_rejected(client, case):
    raw = invalid_init_data(case)
    response = client.post("/api/auth/telegram", json={"init_data": raw})
    assert response.status_code in {400, 401, 422}, response.text
    assert "access_token" not in response.json()
    assert_no_secrets(response, raw)
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize("authorization", [None, "Bearer invalid-token", "Bearer", "Basic abc"])
def test_me_requires_valid_bearer_session(client, authorization):
    headers = {} if authorization is None else {"Authorization": authorization}
    response = client.get("/api/me", headers=headers)
    assert response.status_code == 401, response.text
    assert_no_secrets(response, access_token="invalid-token")


def test_logout_revokes_only_the_presented_session_and_persists(settings):
    with TestClient(create_app(settings)) as client:
        first_launch = signed({**fields_for(), "query_id": "logout-launch-one"})
        second_launch = signed({**fields_for(), "query_id": "logout-launch-two"})
        first = login(client, init_data=first_launch)["access_token"]
        second = login(client, init_data=second_launch)["access_token"]
        assert first != second
        response = client.post("/api/auth/logout", headers=bearer(first))
        assert response.status_code == 204, response.text
        assert response.content == b""
        assert client.get("/api/me", headers=bearer(first)).status_code == 401
        assert client.get("/api/me", headers=bearer(second)).status_code == 200
    with TestClient(create_app(settings)) as reopened:
        assert reopened.get("/api/me", headers=bearer(first)).status_code == 401
        assert reopened.get("/api/me", headers=bearer(second)).status_code == 200


def test_logout_requires_authentication(client):
    assert client.post("/api/auth/logout").status_code == 401
    assert client.post("/api/auth/logout", headers=bearer("unknown")).status_code == 401


def test_same_signed_launch_reuses_session_across_restarts(settings):
    launch = signed(fields_for())
    with TestClient(create_app(settings)) as client:
        original = login(client, init_data=launch)
        assert login(client, init_data=launch) == original
    with TestClient(create_app(settings)) as reopened:
        assert login(reopened, init_data=launch) == original
        response = reopened.get("/api/me", headers=bearer(original["access_token"]))
        assert response.status_code == 200
        assert response.json() == original["user"]


def test_revoked_launch_cannot_resurrect_session(settings):
    launch = signed(fields_for())
    with TestClient(create_app(settings)) as client:
        token = login(client, init_data=launch)["access_token"]
        assert client.post("/api/auth/logout", headers=bearer(token)).status_code == 204
        response = client.post("/api/auth/telegram", json={"init_data": launch})
        assert response.status_code == 401, response.text
        assert_no_secrets(response, launch, token)
        assert client.get("/api/me", headers=bearer(token)).status_code == 401
    with TestClient(create_app(settings)) as reopened:
        response = reopened.post("/api/auth/telegram", json={"init_data": launch})
        assert response.status_code == 401, response.text
        assert_no_secrets(response, launch, token)
        assert reopened.get("/api/me", headers=bearer(token)).status_code == 401


def test_expired_session_rejects_bearer_and_launch_replay(settings, monkeypatch):
    now = int(time.time())
    monkeypatch.setattr(time, "time", lambda: now)
    settings = replace(settings, session_ttl=60)
    launch = signed(fields_for())
    with TestClient(create_app(settings)) as client:
        token = login(client, init_data=launch)["access_token"]
        assert client.get("/api/me", headers=bearer(token)).status_code == 200
        # The launch is still fresh; only its session has expired.
        monkeypatch.setattr(time, "time", lambda: now + 61)
        response = client.get("/api/me", headers=bearer(token))
        assert response.status_code == 401, response.text
        assert_no_secrets(response, access_token=token)
        assert client.post("/api/auth/logout", headers=bearer(token)).status_code == 401
        replay = client.post("/api/auth/telegram", json={"init_data": launch})
        assert replay.status_code == 401, replay.text
        assert_no_secrets(replay, launch, token)
        fresh_launch = signed({**fields_for(), "query_id": "fresh-after-expiry"})
        fresh = login(client, init_data=fresh_launch)
        assert client.get("/api/me", headers=bearer(fresh["access_token"])).status_code == 200


@pytest.mark.parametrize("body_kind", ["wrong_type", "missing_field", "oversized", "invalid_json"])
def test_malformed_request_does_not_echo_secrets(client, body_kind):
    launch = signed(fields_for())
    secret = f"{BOT_TOKEN}|{launch}"
    if body_kind == "wrong_type":
        response = client.post("/api/auth/telegram", json={"init_data": {"secret": secret}})
    elif body_kind == "missing_field":
        response = client.post("/api/auth/telegram", json={"secret": secret})
    elif body_kind == "oversized":
        response = client.post("/api/auth/telegram", json={"init_data": secret + "x" * 20000})
    else:
        response = client.post(
            "/api/auth/telegram",
            content='{"secret":' + json.dumps(secret) + ',"init_data":',
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 422, response.text
    assert_no_secrets(response, launch)
    assert "access_token" not in response.json()
