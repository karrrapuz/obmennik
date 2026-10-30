"""Black-box contracts for the persistent DEMO_TON wallet."""

import re
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from test_auth import BOT_TOKEN, USER, bearer, login


REFERRAL = 5_000_000_000
MAX_TOPUP = 10_000_000_000_000
BALANCE_CAP = 100_000_000_000_000


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token=BOT_TOKEN,
                    database_url=f"sqlite:///{(tmp_path / 'wallet.sqlite3').as_posix()}",
                    allowed_origins=())


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        client.headers.update(bearer(login(client)["access_token"]))
        yield client


def checked(response):
    assert response.status_code == 200, response.text
    value = response.json()
    assert set(value) == {"asset", "balance_nano", "referral_nano", "transactions", "revision"}
    assert type(value["revision"]) is int and value["revision"] >= 0
    assert value["asset"] == "DEMO_TON"
    for field in ("balance_nano", "referral_nano"):
        assert isinstance(value[field], str)
        assert re.fullmatch(r"0|[1-9][0-9]*", value[field])
    assert isinstance(value["transactions"], list)
    ids = []
    for transaction in value["transactions"]:
        assert isinstance(transaction["id"], str) and transaction["id"]
        ids.append(transaction["id"])
        assert transaction["kind"] in {"seed", "topup", "withdraw", "referral"}
        assert isinstance(transaction["amount_nano"], str)
        assert re.fullmatch(r"0|-?[1-9][0-9]*", transaction["amount_nano"])
        assert type(transaction["created_at"]) is int
        assert 0 < transaction["created_at"] <= int(time.time()) + 5
    assert len(ids) == len(set(ids))
    assert sum(int(tx["amount_nano"]) for tx in value["transactions"]) == int(value["balance_nano"])
    assert BOT_TOKEN not in response.text
    return value


def wallet(client):
    return checked(client.get("/api/wallet"))


def post(client, action, body, key="test-key"):
    return client.post(f"/api/wallet/demo-{action}", json=body,
                       headers={"Idempotency-Key": key})


def topup(client, amount="1", key="topup", source="wallet"):
    return post(client, "topup", {"amount_nano": amount, "source": source}, key)


def test_initial_wallet_and_referral_seed_persist_once(client, settings):
    initial = wallet(client)
    assert initial["balance_nano"] == "0"
    assert initial["referral_nano"] == str(REFERRAL)
    assert wallet(client) == initial
    with TestClient(create_app(settings)) as reopened:
        reopened.headers.update({"Authorization": client.headers["Authorization"]})
        assert wallet(reopened) == initial


@pytest.mark.parametrize("source", ["wallet", "cryptobot"])
def test_exact_one_nano_topup_and_withdraw(client, source):
    before = wallet(client)
    funded = checked(topup(client, source=source))
    assert funded["balance_nano"] == "1"
    assert funded["revision"] > before["revision"]
    added = [tx for tx in funded["transactions"] if tx["id"] not in {t["id"] for t in before["transactions"]}]
    assert len(added) == 1
    assert added[0]["kind"] == "topup"
    assert added[0]["amount_nano"] == "1"
    withdrawn = checked(post(client, "withdraw", {"amount_nano": "1", "destination": "demo"}, "withdraw"))
    assert withdrawn["balance_nano"] == "0"
    assert withdrawn["revision"] > funded["revision"]
    negative = [tx for tx in withdrawn["transactions"] if tx["kind"] == "withdraw"]
    assert len(negative) == 1 and negative[0]["amount_nano"] == "-1"
    assert withdrawn["referral_nano"] == str(REFERRAL)


def test_idempotency_current_snapshot_payload_binding_and_restart(client, settings):
    first = checked(topup(client, "10", "A"))
    assert checked(topup(client, "10", "A")) == first
    assert topup(client, "11", "A").status_code == 409
    assert topup(client, "10", "A", source="cryptobot").status_code == 409
    assert post(client, "referral", {}, "A").status_code == 409
    latest = checked(post(client, "withdraw", {"amount_nano": "3", "destination": "demo"}, "B"))
    assert latest["balance_nano"] == "7"
    assert latest["revision"] > first["revision"]
    assert checked(topup(client, "10", "A")) == latest
    assert checked(post(client, "withdraw", {"amount_nano": "3", "destination": "demo"}, "B")) == latest
    assert post(client, "withdraw", {"amount_nano": "3", "destination": "other"}, "B").status_code == 409
    with TestClient(create_app(settings)) as reopened:
        reopened.headers.update({"Authorization": client.headers["Authorization"]})
        assert wallet(reopened) == latest
        assert checked(topup(reopened, "10", "A")) == latest


def test_referral_claim_once_and_replay_after_spending(client, settings):
    claimed = checked(post(client, "referral", {}, "claim"))
    assert claimed["balance_nano"] == str(REFERRAL)
    assert claimed["referral_nano"] == "0"
    referrals = [tx for tx in claimed["transactions"] if tx["kind"] == "referral"]
    assert len(referrals) == 1 and referrals[0]["amount_nano"] == str(REFERRAL)
    assert checked(post(client, "referral", {}, "claim")) == claimed
    assert post(client, "referral", {}, "fresh-claim").status_code == 409
    spent = checked(post(client, "withdraw", {"amount_nano": str(REFERRAL), "destination": "demo"}, "spend"))
    assert spent["balance_nano"] == "0"
    assert checked(post(client, "referral", {}, "claim")) == spent
    with TestClient(create_app(settings)) as reopened:
        reopened.headers.update({"Authorization": client.headers["Authorization"]})
        assert wallet(reopened) == spent
        assert post(reopened, "referral", {}, "fresh-again").status_code == 409


def test_user_balances_history_and_idempotency_keys_are_isolated(client):
    first = checked(topup(client, "123", "shared"))
    first_auth = client.headers["Authorization"]
    other = login(client, {**USER, "id": USER["id"] + 1})
    client.headers.update(bearer(other["access_token"]))
    second = wallet(client)
    assert second["balance_nano"] == "0"
    assert second["referral_nano"] == str(REFERRAL)
    assert not any(tx["kind"] == "topup" for tx in second["transactions"])
    second = checked(topup(client, "456", "shared"))
    assert second["balance_nano"] == "456"
    assert {tx["id"] for tx in first["transactions"]}.isdisjoint(tx["id"] for tx in second["transactions"])
    assert post(client, "withdraw", {"amount_nano": "457", "destination": "demo"}, "fail").status_code == 409
    assert wallet(client) == second
    client.headers["Authorization"] = first_auth
    assert wallet(client) == first


def test_insufficient_withdraw_rolls_back_and_does_not_consume_key(client):
    before = wallet(client)
    body = {"amount_nano": "2", "destination": "demo"}
    assert post(client, "withdraw", body, "retry").status_code == 409
    assert wallet(client) == before
    checked(topup(client, "2"))
    result = checked(post(client, "withdraw", body, "retry"))
    assert result["balance_nano"] == "0"
    assert len([tx for tx in result["transactions"] if tx["kind"] == "withdraw"]) == 1


def test_balance_cap_and_rejected_key_can_be_retried(client):
    for index in range(BALANCE_CAP // MAX_TOPUP):
        full = checked(topup(client, str(MAX_TOPUP), f"fill-{index}"))
    assert full["balance_nano"] == str(BALANCE_CAP)
    assert topup(client, "1", "overflow").status_code == 409
    assert wallet(client) == full
    assert post(client, "referral", {}, "claim-overflow").status_code == 409
    assert wallet(client) == full
    checked(post(client, "withdraw", {"amount_nano": str(REFERRAL + 1), "destination": "demo"}, "space"))
    checked(topup(client, "1", "overflow"))
    claimed = checked(post(client, "referral", {}, "claim-overflow"))
    assert claimed["balance_nano"] == str(BALANCE_CAP)
    assert claimed["referral_nano"] == "0"


@pytest.mark.parametrize("amount", [
    1, 0, -1, 1.5, True, None, "", "0", "-1", "1.5", "NaN", "nan",
    "Infinity", "1e9", " 1", "1 ", "9" * 100,
])
@pytest.mark.parametrize("action", ["topup", "withdraw"])
def test_invalid_amounts_rejected_without_writes_or_consumed_key(client, action, amount):
    before = wallet(client)
    body = {"amount_nano": amount}
    body.update({"source": "wallet"} if action == "topup" else {"destination": "demo"})
    assert post(client, action, body, "retry").status_code == 422
    assert wallet(client) == before
    assert topup(client, "1", "retry").status_code == 200


def test_topup_above_request_limit_is_rejected(client):
    before = wallet(client)
    assert topup(client, str(MAX_TOPUP + 1), "retry").status_code == 422
    assert wallet(client) == before
    assert topup(client, "1", "retry").status_code == 200


@pytest.mark.parametrize("action,body", [
    ("topup", {"amount_nano": "1", "source": "unknown"}),
    ("topup", {"amount_nano": "1"}),
    ("topup", {"amount_nano": "1", "source": "wallet", "balance_nano": "999"}),
    ("withdraw", {"amount_nano": "1", "destination": ""}),
    ("withdraw", {"amount_nano": "1", "destination": "x" * 257}),
    ("withdraw", {"amount_nano": "1", "destination": 123}),
    ("withdraw", {"amount_nano": "1"}),
    ("withdraw", {"amount_nano": "1", "destination": "demo", "user_id": USER["id"]}),
    ("referral", {"amount_nano": "1"}),
])
def test_invalid_payloads_are_atomic(client, action, body):
    before = wallet(client)
    assert post(client, action, body).status_code == 422
    assert wallet(client) == before
    assert topup(client, key="test-key").status_code == 200


@pytest.mark.parametrize("destination", ["x", "x" * 256])
def test_destination_length_boundaries(client, destination):
    checked(topup(client))
    result = checked(post(client, "withdraw", {"amount_nano": "1", "destination": destination}))
    assert result["balance_nano"] == "0"


@pytest.mark.parametrize("action,body", [
    ("topup", {"amount_nano": "1", "source": "wallet"}),
    ("withdraw", {"amount_nano": "1", "destination": "demo"}),
    ("referral", {}),
])
def test_mutations_require_idempotency_key(client, action, body):
    before = wallet(client)
    assert client.post(f"/api/wallet/demo-{action}", json=body).status_code == 422
    assert wallet(client) == before


def test_wallet_and_history_require_authentication(settings):
    with TestClient(create_app(settings)) as client:
        for headers in ({}, bearer("invalid-session")):
            assert client.get("/api/wallet", headers=headers).status_code == 401
            for action, body in [
                ("topup", {"amount_nano": "1", "source": "wallet"}),
                ("withdraw", {"amount_nano": "1", "destination": "demo"}),
                ("referral", {}),
            ]:
                response = client.post(f"/api/wallet/demo-{action}", json=body,
                                       headers={**headers, "Idempotency-Key": "unauth"})
                assert response.status_code == 401


def test_sql_ledger_postings_balance_and_match_accounts(client):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.wallet_models import WalletAccount, WalletPosting, WalletTransaction

    wallet(client)
    checked(topup(client, "17", "ledger-topup"))
    checked(post(client, "referral", {}, "ledger-referral"))
    final = checked(post(client, "withdraw", {"amount_nano": "3", "destination": "demo"}, "ledger-withdraw"))
    with Session(client.app.state.engine) as db:
        transactions = db.scalars(select(WalletTransaction).where(WalletTransaction.user_id == USER["id"])).all()
        postings = db.scalars(select(WalletPosting).where(WalletPosting.user_id == USER["id"])).all()
        accounts = db.scalars(select(WalletAccount).where(WalletAccount.user_id == USER["id"])).all()
        assert {tx.id for tx in transactions} == {tx["id"] for tx in final["transactions"]}
        assert {account.kind for account in accounts} == {"wallet", "referral", "treasury"}
        for transaction in transactions:
            entries = [posting for posting in postings if posting.transaction_id == transaction.id]
            assert len(entries) >= 2
            assert all(posting.amount != 0 for posting in entries)
            assert sum(posting.amount for posting in entries) == 0
            assert sum(posting.amount for posting in entries if posting.account_kind == "wallet") == transaction.amount_nano
        for account in accounts:
            assert account.balance == sum(posting.amount for posting in postings if posting.account_kind == account.kind)
        balances = {account.kind: account.balance for account in accounts}
        assert balances["wallet"] == int(final["balance_nano"])
        assert balances["referral"] == int(final["referral_nano"])
        assert sum(balances.values()) == 0
