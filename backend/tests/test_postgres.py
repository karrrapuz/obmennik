"""Optional PostgreSQL integration smoke test, enabled explicitly by CI."""

import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import LoginSession, User
from app.inventory_models import InventoryGift, InventoryInit, InventoryReceipt
from concurrent.futures import ThreadPoolExecutor


POSTGRES_URL = os.environ.get("GIFT_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="GIFT_TEST_POSTGRES_URL is not set")
BOT_TOKEN = "123456789:POSTGRES_TEST_ONLY_NOT_A_SERVER_SECRET"


@pytest.fixture
def settings():
    # The shared autouse fixture migrates this database before the test runs.
    return Settings(
        bot_token=BOT_TOKEN,
        database_url=POSTGRES_URL,
        allowed_origins=("http://localhost:5173",),
    )


def test_postgres_new_user_retry_me_and_logout(settings):
    user_id = secrets.randbelow(2**52 - 1) + 1
    fields = {
        "query_id": secrets.token_hex(16),
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": user_id, "first_name": "Postgres Test"}),
    }
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    launch = urlencode(fields)
    app = create_app(settings)

    with TestClient(app) as client:
        try:
            with Session(app.state.engine) as db:
                assert db.get(User, user_id) is None

            response = client.post("/api/auth/telegram", json={"init_data": launch})
            assert response.status_code == 200
            payload = response.json()
            token = payload["access_token"]
            assert isinstance(token, str) and token
            assert payload["user"]["id"] == user_id
            assert payload["user"]["first_name"] == "Postgres Test"
            for private_value in (BOT_TOKEN, launch, fields["hash"], fields["query_id"]):
                assert private_value not in response.text

            repeated = client.post("/api/auth/telegram", json={"init_data": launch})
            assert repeated.status_code == 200
            assert repeated.json() == payload
            with Session(app.state.engine) as db:
                assert db.get(User, user_id).first_name == "Postgres Test"
                sessions = db.scalars(select(LoginSession).where(LoginSession.user_id == user_id)).all()
                assert len(sessions) == 1
                assert sessions[0].token_hash == hashlib.sha256(token.encode()).hexdigest()

            headers = {"Authorization": f"Bearer {token}"}
            me = client.get("/api/me", headers=headers)
            assert me.status_code == 200
            assert me.json() == payload["user"]
            assert token not in me.text
            initial = client.get('/api/inventory', headers=headers)
            assert initial.status_code == 200
            assert len(initial.json()['inventory']) == 5
            deposit_headers = {**headers, 'Idempotency-Key': 'pg-deposit'}
            deposited = client.post('/api/inventory/demo-deposit', json={}, headers=deposit_headers)
            assert deposited.status_code == 200
            assert len(deposited.json()['inventory']) == 6
            assert client.post('/api/inventory/demo-deposit', json={}, headers=deposit_headers).json() == deposited.json()
            gift_id = initial.json()['inventory'][0]['id']

            def competing_action(action):
                body = {'id': gift_id} if action == 'pledge' else {'ids': [gift_id]}
                return client.post('/api/inventory/demo-' + action, json=body,
                                   headers={**headers, 'Idempotency-Key': 'race-' + action}).status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(competing_action, ['pledge', 'withdraw']))
            assert sorted(outcomes) == [200, 409]
            final = client.get('/api/inventory', headers=headers).json()
            assert gift_id not in [g['id'] for g in final['inventory']]
            assert len(final['pledged']) == (1 if outcomes[0] == 200 else 0)
            logout = client.post("/api/auth/logout", headers=headers)
            assert logout.status_code == 204
            assert logout.content == b""
            assert client.get("/api/me", headers=headers).status_code == 401
        finally:
            # Remove only this test's random identity, never shared database state.
            with Session(app.state.engine) as db:
                db.execute(delete(InventoryReceipt).where(InventoryReceipt.user_id == user_id))
                db.execute(delete(InventoryGift).where(InventoryGift.user_id == user_id))
                db.execute(delete(InventoryInit).where(InventoryInit.user_id == user_id))
                db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
                db.execute(delete(User).where(User.id == user_id))
                db.commit()
