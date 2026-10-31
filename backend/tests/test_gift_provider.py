"""Public stub-provider contract and disabled-mode safety boundaries."""

from dataclasses import replace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import config
from app.config import Settings
from app.gift_provider import create_gift_provider
from app.main import create_app
from test_auth import BOT_TOKEN, bearer, login


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token=BOT_TOKEN,
                    database_url=f"sqlite:///{(tmp_path / 'provider.sqlite3').as_posix()}",
                    allowed_origins=())


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def authenticate(client):
    client.headers.update(bearer(login(client)["access_token"]))


def mutate(client, path, body, key):
    return client.post(path, json=body, headers={"Idempotency-Key": key})


@pytest.mark.parametrize("mode", ["demo", "disabled"])
def test_provider_public_contract(mode):
    provider = create_gift_provider(mode)
    assert provider.mode == mode
    assert provider.status() == {"mode": mode, "available": mode == "demo",
                                 "simulated": True, "real_transfers": False}
    assert isinstance(provider.catalog, (tuple, list))
    assert len(provider.catalog) >= 5
    assert all(isinstance(item, dict) for item in provider.catalog)
    ids = [item["id"] for item in provider.catalog]
    assert len(ids) == len(set(ids))
    if mode == "demo":
        assert provider.require_available() is None
        assert provider.initial_gifts() == tuple((id, index < 3) for index, id in enumerate(ids[:5]))
        assert provider.deposit_catalog_id() == ids[1]
    else:
        assert provider.initial_gifts() == ()
        for method in (provider.require_available, provider.deposit_catalog_id):
            with pytest.raises(HTTPException) as error:
                method()
            assert error.value.status_code == 503


@pytest.mark.parametrize("mode", ["live", "telegram", "DEMO", "", "demo "])
def test_unknown_modes_rejected_by_constructor_and_app(settings, mode):
    with pytest.raises(ValueError):
        create_gift_provider(mode)
    with pytest.raises(ValueError):
        create_app(replace(settings, gift_provider_mode=mode))


def test_settings_defaults_to_demo(settings):
    assert settings.gift_provider_mode == "demo"


@pytest.mark.parametrize("mode", [None, "", "demo", "disabled"])
def test_settings_reads_provider_mode_without_dotenv(settings, monkeypatch, mode):
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", settings.bot_token)
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    if mode is None:
        monkeypatch.delenv("GIFT_PROVIDER_MODE", raising=False)
    else:
        monkeypatch.setenv("GIFT_PROVIDER_MODE", mode)
    configured = Settings.from_env()
    assert configured.gift_provider_mode == ("demo" if mode is None else mode)
    if mode == "":
        with pytest.raises(ValueError):
            create_app(configured)


@pytest.mark.parametrize("mode", ["demo", "disabled"])
def test_integration_status_requires_auth_and_reports_no_real_transfers(settings, mode):
    with TestClient(create_app(replace(settings, gift_provider_mode=mode))) as client:
        assert client.get("/api/integrations/gifts").status_code == 401
        assert client.get("/api/integrations/gifts", headers=bearer("invalid")).status_code == 401
        authenticate(client)
        status = ok(client.get("/api/integrations/gifts"))
        assert status == {"mode": mode, "available": mode == "demo",
                          "simulated": True, "real_transfers": False}


def test_disabled_inventory_does_not_seed_or_change_funds(settings):
    disabled = replace(settings, gift_provider_mode="disabled")
    with TestClient(create_app(disabled)) as client:
        authenticate(client)
        wallet = ok(client.get("/api/wallet"))
        inventory = ok(client.get("/api/inventory"))
        assert inventory["inventory"] == inventory["pledged"] == []
        assert ok(client.get("/api/inventory")) == inventory
        for index, (action, body) in enumerate([
            ("deposit", {}), ("withdraw", {"ids": [1]}),
            ("exchange", {"offered_ids": [1], "received_ids": [2]}),
            ("pledge", {"id": 1}), ("release", {"id": 1}),
        ]):
            response = mutate(client, "/api/inventory/demo-" + action, body, f"disabled-{index}")
            assert response.status_code == (410 if action == "exchange" else 503), response.text
            assert ok(client.get("/api/inventory")) == inventory
            assert ok(client.get("/api/wallet")) == wallet
        response = mutate(client, "/api/loans/create", {"gift_id": 1, "weeks": 1}, "disabled-loan")
        assert response.status_code == 503, response.text
        assert ok(client.get("/api/wallet")) == wallet
        auth = client.headers["Authorization"]
    with TestClient(create_app(disabled)) as reopened:
        reopened.headers["Authorization"] = auth
        assert ok(reopened.get("/api/inventory")) == inventory
    # Disabled reads must not consume the once-only demo seed marker.
    with TestClient(create_app(settings)) as enabled:
        enabled.headers["Authorization"] = auth
        seeded = ok(enabled.get("/api/inventory"))
        assert len(seeded["inventory"]) == 5
        current_wallet = ok(enabled.get("/api/wallet"))
        assert {k: v for k, v in current_wallet.items() if k != "revision"} == {
            k: v for k, v in wallet.items() if k != "revision"}


def test_disabled_existing_loan_repayment_preserves_accounting_and_inventory(settings):
    with TestClient(create_app(settings)) as client:
        authenticate(client)
        initial = ok(client.get("/api/inventory"))
        gift = next(g["id"] for g in initial["inventory"] if g["pledgeSupported"])
        ok(mutate(client, "/api/wallet/demo-topup", {"amount_nano": "40000000", "source": "wallet"}, "fund"))
        ok(mutate(client, "/api/loans/create", {"gift_id": gift, "weeks": 1}, "create"))
        before = ok(client.get("/api/loans"))
        assert before["wallet"]["balance_nano"] == "1240000000"
        auth = client.headers["Authorization"]
    disabled = replace(settings, gift_provider_mode="disabled")
    with TestClient(create_app(disabled)) as client:
        client.headers["Authorization"] = auth
        assert ok(client.get("/api/loans")) == before
        other = next(g["id"] for g in before["inventory"]["inventory"] if g["pledgeSupported"])
        assert mutate(client, "/api/loans/create", {"gift_id": other, "weeks": 1}, "blocked").status_code == 503
        assert ok(client.get("/api/loans")) == before
        ok(mutate(client, "/api/loans/repay", {"gift_id": gift}, "repay"))
        after = ok(client.get("/api/loans"))
        assert after["wallet"]["balance_nano"] == "0"
        assert after["wallet"]["referral_nano"] == before["wallet"]["referral_nano"]
        assert next(item for item in after["loans"] if item["gift_id"] == gift)["status"] == "repaid"
        assert {g["id"] for g in after["inventory"]["inventory"]} == {g["id"] for g in initial["inventory"]}
        assert after["inventory"]["pledged"] == []
        txs = after["wallet"]["transactions"]
        assert sum(int(tx["amount_nano"]) for tx in txs) == 0
        assert len([tx for tx in txs if tx["kind"] == "loan_credit"]) == 1
        repayments = [tx for tx in txs if tx["kind"] == "loan_repay"]
        assert len(repayments) == 1 and repayments[0]["amount_nano"] == "-1240000000"
        ok(mutate(client, "/api/loans/repay", {"gift_id": gift}, "repay"))
        assert ok(client.get("/api/loans")) == after
    with TestClient(create_app(disabled)) as reopened:
        reopened.headers["Authorization"] = auth
        assert ok(reopened.get("/api/loans")) == after
