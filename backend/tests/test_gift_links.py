from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.gift_links import SharedGift
from test_auth import BOT_TOKEN, USER, bearer, login


@pytest.fixture
def settings(tmp_path):
    return Settings(BOT_TOKEN, f"sqlite:///{(tmp_path / 'gift-links.db').as_posix()}", (), showcase_mode=True)


def test_featured_grant_is_once_and_does_not_reappear_after_withdrawal(settings):
    with TestClient(create_app(settings)) as client:
        headers = bearer(login(client)['access_token'])
        first = client.get('/api/inventory', headers=headers).json()
        gift = next(g for g in first['inventory'] if g['catalogId'] == 90001)
        assert gift['price'] == '43.950' and gift['testGrant'] is True
        assert client.get('/api/inventory', headers=headers).json() == first
        other = bearer(login(client, {**USER, 'id': USER['id'] + 1})['access_token'])
        second = client.get('/api/inventory', headers=other).json()
        other_gift = next(g for g in second['inventory'] if g['catalogId'] == 90001)
        assert other_gift['id'] != gift['id']
        result = client.post('/api/inventory/demo-withdraw', headers={**headers, 'Idempotency-Key': 'remove-test-gift'}, json={'ids': [gift['id']]})
        assert result.status_code == 200
        assert not any(g['catalogId'] == 90001 for g in client.get('/api/inventory', headers=headers).json()['inventory'])


def test_share_is_exact_read_only_deduplicated_and_survives_removal(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        headers = bearer(login(client)['access_token'])
        original = client.get('/api/inventory', headers=headers).json()['inventory'][0]
        body = {'source': 'inventory', 'gift_id': original['id']}
        response = client.post('/api/gifts/share', headers=headers, json=body)
        assert response.status_code == 200
        token = response.json()['share_ref']
        assert client.post('/api/gifts/share', headers=headers, json=body).json() == response.json()
        public = client.get(f'/api/gifts/shared/{token}').json()['gift']
        assert {key: public[key] for key in original} == original
        assert public['sharedReadOnly'] is True
        assert 'user_id' not in public
        other = bearer(login(client, {**USER, 'id': USER['id'] + 1})['access_token'])
        assert client.post('/api/gifts/share', headers=other, json=body).status_code == 404
        client.post('/api/inventory/demo-withdraw', headers={**headers, 'Idempotency-Key': 'withdraw-after-share'}, json={'ids': [original['id']]})
        assert client.get(f'/api/gifts/shared/{token}').json()['gift'] == public
        assert client.get('/api/gifts/shared/not-a-token').status_code == 404
        assert client.post('/api/gifts/share', json=body).status_code == 401
        with Session(app.state.engine) as db:
            shared = db.get(SharedGift, token)
            shared.expires_at = 0
            db.commit()
        assert client.get(f'/api/gifts/shared/{token}').status_code == 404
