"""Authenticated, persistent DEMO loan contracts and atomic wallet effects."""

import time
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from test_auth import BOT_TOKEN, USER, bearer, login


DAY = 86400
PRINCIPAL = 1_200_000_000


def test_autopay_reports_failure_rolls_back_one_user_and_continues(client, monkeypatch, caplog):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app import loans
    from app.models import User
    from app.inventory_models import InventoryGift
    from app.loan_models import DemoLoan
    from app.wallet_models import WalletAccount, WalletTransaction
    from app.ledger import ensure_wallet, post_transfer
    from app.ledger_audit import audit_ledger
    now = int(time.time())
    monkeypatch.setattr(loans.time, 'time', lambda: now)
    engine = client.app.state.engine
    gifts = {}
    with Session(engine) as db:
        for identity in (1, 2):
            db.add(User(id=identity, first_name='Failure test', referral_code=f'failure-{identity}'))
        db.flush()
        for identity in (1, 2):
            ensure_wallet(db, identity)
            post_transfer(db, identity, 'fund', 'test', 'topup', 1_240_000_000,
                          'treasury', 'wallet', 1_240_000_000)
            gift = InventoryGift(user_id=identity, catalog_id=1, pledged=True)
            db.add(gift)
            db.flush()
            gifts[identity] = gift.id
            db.add(DemoLoan(id=f'{identity:032x}', user_id=identity, gift_id=gift.id,
                weeks=1, principal=PRINCIPAL, repayment=1_240_000_000, created_at=now - 8 * DAY,
                due_at=now - DAY, autopay=True, status='active', legacy=False))
        db.commit()
    original = loans.process_user_autopay
    def fail_after_settlement(db, identity):
        original(db, identity)
        if identity == 1:
            raise RuntimeError('PRIVATE_AUTOPAY_SENTINEL')
    monkeypatch.setattr(loans, 'process_user_autopay', fail_after_settlement)
    assert loans.process_due_loans(engine) == {'selected': 2, 'processed': 1, 'failed': 1, 'discovery_failed': False}
    assert 'PRIVATE_AUTOPAY_SENTINEL' not in caplog.text
    with Session(engine) as db:
        assert db.get(DemoLoan, f'{1:032x}').status == 'active'
        assert db.get(WalletAccount, (1, 'wallet')).balance == 1_240_000_000
        assert db.get(InventoryGift, gifts[1]).pledged
        assert db.get(DemoLoan, f'{2:032x}').status == 'repaid'
    monkeypatch.setattr(loans, 'process_user_autopay', original)
    assert loans.process_due_loans(engine) == {'selected': 1, 'processed': 1, 'failed': 0, 'discovery_failed': False}
    with Session(engine) as db:
        assert db.get(DemoLoan, f'{1:032x}').status == 'repaid'
        assert len(db.scalars(select(WalletTransaction).where(WalletTransaction.kind == 'loan_repay')).all()) == 2
    with engine.connect() as connection:
        assert audit_ledger(connection)['ok']


def test_autopay_batch_moves_past_users_in_retry_cooldown(client, monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app import loans
    from app.models import User
    from app.inventory_models import InventoryGift
    from app.loan_models import DemoLoan
    from app.ledger import ensure_wallet, post_transfer
    now = int(time.time())
    monkeypatch.setattr(loans.time, 'time', lambda: now)
    engine = client.app.state.engine
    with Session(engine) as db:
        for identity in range(1, 102):
            db.add(User(id=identity, first_name='Batch test', referral_code=f'batch-{identity}'))
        db.flush()
        for identity in range(1, 102):
            ensure_wallet(db, identity)
            gift = InventoryGift(user_id=identity, catalog_id=1, pledged=True)
            db.add(gift)
            db.flush()
            db.add(DemoLoan(id=f'{identity:032x}', user_id=identity, gift_id=gift.id,
                weeks=1, principal=PRINCIPAL, repayment=1_240_000_000, created_at=now - 8 * DAY,
                due_at=now - DAY, autopay=True, status='active', legacy=False))
        post_transfer(db, 101, 'fund', 'test', 'topup', 1_240_000_000,
                      'treasury', 'wallet', 1_240_000_000)
        db.commit()
    loans.process_due_loans(engine)
    with Session(engine) as db:
        assert db.get(DemoLoan, f'{101:032x}').status == 'active'
        assert db.get(DemoLoan, f'{1:032x}').last_autopay_attempt == now
    loans.process_due_loans(engine)
    loans.process_due_loans(engine)
    with Session(engine) as db:
        target = db.get(DemoLoan, f'{101:032x}')
        assert target.status == 'repaid'
        assert not db.get(InventoryGift, target.gift_id).pledged
        assert len(db.scalars(select(DemoLoan).where(DemoLoan.status == 'repaid')).all()) == 1


@pytest.fixture
def settings(tmp_path):
    return Settings(bot_token=BOT_TOKEN,
                    database_url=f"sqlite:///{(tmp_path / 'loans.sqlite3').as_posix()}",
                    allowed_origins=(), session_ttl=365 * DAY)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        client.headers.update(bearer(login(client)["access_token"]))
        yield client


def read(client):
    response = client.get("/api/loans")
    assert response.status_code == 200, response.text
    result = response.json()
    assert {"loans", "terms", "wallet", "inventory", "revision"} <= result.keys()
    for snapshot in (result, result["wallet"], result["inventory"]):
        assert type(snapshot["revision"]) is int and snapshot["revision"] >= 0
        assert snapshot["revision"] == result["revision"]
    assert result["wallet"]["asset"] == "DEMO_TON"
    assert isinstance(result["wallet"]["balance_nano"], str)
    ids = []
    for item in result["loans"]:
        assert isinstance(item["id"], str)
        UUID(item["id"])
        ids.append(item["id"])
    assert len(ids) == len(set(ids))
    return result


def post(client, action, body, key="loan-key"):
    return client.post(f"/api/loans/{action}", json=body, headers={"Idempotency-Key": key})


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def gift_ids(state):
    return [gift["id"] for gift in state["inventory"]["inventory"] if gift["pledgeSupported"]]


def loan(state, gift_id):
    return next(item for item in state["loans"] if item["gift_id"] == gift_id)


def balance(state):
    return int(state["wallet"]["balance_nano"])


def fund(client, amount="10000000000"):
    ok(client.post("/api/wallet/demo-topup", json={"amount_nano": amount, "source": "wallet"},
                   headers={"Idempotency-Key": "fund"}))


@pytest.mark.parametrize("weeks,repayment", [(1, 1_240_000_000), (2, 1_280_000_000)])
def test_create_single_principal_and_repay_persist(client, settings, monkeypatch, weeks, repayment):
    now = int(time.time())
    monkeypatch.setattr(time, "time", lambda: now)
    initial = read(client)
    terms = {term["weeks"]: term for term in initial["terms"]}
    assert int(terms[weeks]["principal_nano"]) == PRINCIPAL
    assert int(terms[weeks]["repayment_nano"]) == repayment
    gift = gift_ids(initial)[0]
    body = {"gift_id": gift, "weeks": weeks}
    ok(post(client, "create", body, "create"))
    created = read(client)
    assert created["revision"] > initial["revision"]
    active = loan(created, gift)
    assert active["status"] == "active"
    assert active["legacy"] is False
    assert active["weeks"] == weeks
    assert int(active["principal_nano"]) == PRINCIPAL
    assert int(active["repayment_nano"]) == repayment
    assert type(active["due_at"]) is int
    assert active["due_at"] == now + weeks * 7 * DAY
    assert balance(created) == balance(initial) + PRINCIPAL
    assert gift in [g["id"] for g in created["inventory"]["pledged"]]
    ok(post(client, "create", body, "create"))
    assert read(client) == created
    assert post(client, "create", body, "fresh").status_code == 409
    assert post(client, "create", {**body, "weeks": 3 - weeks}, "create").status_code == 409
    assert read(client) == created
    # Principal alone cannot repay principal plus interest; rejection is atomic.
    assert post(client, "repay", {"gift_id": gift}, "repay").status_code == 409
    assert read(client) == created
    fund(client)
    funded = read(client)
    ok(post(client, "repay", {"gift_id": gift}, "repay"))
    repaid = read(client)
    assert repaid["revision"] > funded["revision"]
    assert balance(repaid) == balance(funded) - repayment
    assert loan(repaid, gift)["status"] == "repaid"
    assert gift in [g["id"] for g in repaid["inventory"]["inventory"]]
    assert gift not in [g["id"] for g in repaid["inventory"]["pledged"]]
    ok(post(client, "repay", {"gift_id": gift}, "repay"))
    ok(post(client, "create", body, "create"))
    assert read(client) == repaid
    assert post(client, "repay", {"gift_id": gift}, "again").status_code == 409
    kinds = [tx["kind"] for tx in repaid["wallet"]["transactions"]]
    assert kinds.count("loan_credit") == 1
    assert kinds.count("loan_repay") == 1
    with TestClient(create_app(settings)) as reopened:
        reopened.headers.update({"Authorization": client.headers["Authorization"]})
        assert read(reopened) == repaid


@pytest.mark.parametrize("weeks,interest", [(1, 40_000_000), (2, 80_000_000)])
@pytest.mark.parametrize("overdue", [False, True])
def test_interest_extends_original_term_without_fee(client, monkeypatch, weeks, interest, overdue):
    now = int(time.time())
    monkeypatch.setattr(time, "time", lambda: now)
    gift = gift_ids(read(client))[0]
    ok(post(client, "create", {"gift_id": gift, "weeks": weeks}))
    before = read(client)
    due = loan(before, gift)["due_at"]
    current = due + DAY if overdue else now + DAY
    monkeypatch.setattr(time, "time", lambda: current)
    ok(post(client, "pay-interest", {"gift_id": gift}, "interest"))
    after = read(client)
    assert after["revision"] > before["revision"]
    assert balance(after) == balance(before) - interest
    assert loan(after, gift)["due_at"] == max(current, due) + weeks * 7 * DAY
    assert loan(after, gift)["status"] == "active"
    ok(post(client, "pay-interest", {"gift_id": gift}, "interest"))
    assert read(client) == after
    entries = [tx for tx in after["wallet"]["transactions"] if tx["kind"] == "loan_interest"]
    assert len(entries) == 1 and int(entries[0]["amount_nano"]) == -interest


def test_batch_quote_extension_fee_once_and_atomicity(client, monkeypatch):
    now = int(time.time())
    monkeypatch.setattr(time, "time", lambda: now)
    first, second = gift_ids(read(client))[:2]
    for gift, weeks in ((first, 1), (second, 2)):
        ok(post(client, "create", {"gift_id": gift, "weeks": weeks}, str(gift)))
    before = read(client)
    quote = ok(client.post("/api/loans/quote", json={"gift_ids": [first, second]}))
    assert {k: int(quote[k]) for k in ("interest_nano", "fee_nano", "total_nano")} == {
        "interest_nano": 120_000_000, "fee_nano": 10_000_000, "total_nano": 130_000_000}
    assert read(client) == before
    for ids in ([first, first], [first, 999999999]):
        assert post(client, "extend", {"gift_ids": ids}, "extend").status_code in {409, 422}
        assert read(client) == before
    ok(post(client, "extend", {"gift_ids": [first, second]}, "extend"))
    after = read(client)
    assert balance(after) == balance(before) - 130_000_000
    for gift in (first, second):
        assert loan(after, gift)["due_at"] == loan(before, gift)["due_at"] + 14 * DAY
    ok(post(client, "extend", {"gift_ids": [first, second]}, "extend"))
    assert read(client) == after
    entries = [tx for tx in after["wallet"]["transactions"] if tx["kind"] == "loan_extend"]
    assert sum(int(tx["amount_nano"]) for tx in entries) == -130_000_000


def test_legacy_pledge_import_once_no_principal_and_no_release_bypass(client, settings, monkeypatch):
    now = int(time.time())
    monkeypatch.setattr(time, "time", lambda: now)
    inventory = ok(client.get("/api/inventory"))
    gift = next(g["id"] for g in inventory["inventory"] if g["pledgeSupported"])
    ok(client.post("/api/inventory/demo-pledge", json={"id": gift}, headers={"Idempotency-Key": "legacy"}))
    state = read(client)
    assert balance(state) == 0
    assert loan(state, gift)["legacy"] is True
    assert loan(state, gift)["principal_nano"] == "0"
    assert loan(state, gift)["repayment_nano"] == "0"
    assert loan(state, gift)["weeks"] == 1
    assert loan(state, gift)["due_at"] == now + 7 * DAY
    assert not any(tx["kind"] == "loan_credit" for tx in state["wallet"]["transactions"])
    monkeypatch.setattr(time, "time", lambda: now + DAY)
    with TestClient(create_app(settings)) as reopened:
        reopened.headers.update({"Authorization": client.headers["Authorization"]})
        assert read(reopened) == state
        response = reopened.post("/api/inventory/demo-release", json={"id": gift},
                                 headers={"Idempotency-Key": "bypass"})
        assert response.status_code == 409
        assert read(reopened) == state
        assert post(reopened, "pay-interest", {"gift_id": gift}, "interest").status_code == 409
        assert post(reopened, "extend", {"gift_ids": [gift]}, "extend").status_code == 409
        assert reopened.post("/api/loans/quote", json={"gift_ids": [gift]}).status_code == 409
        assert read(reopened) == state
        ok(post(reopened, "repay", {"gift_id": gift}, "free-release"))
        released = read(reopened)
        assert {k: v for k, v in released["wallet"].items() if k != "revision"} == {
            k: v for k, v in state["wallet"].items() if k != "revision"}
        assert released["revision"] > state["revision"]
        assert loan(released, gift)["status"] == "repaid"
        assert loan(released, gift)["id"] == loan(state, gift)["id"]
        assert gift in [g["id"] for g in released["inventory"]["inventory"]]
        assert gift not in [g["id"] for g in released["inventory"]["pledged"]]
        ok(post(reopened, "repay", {"gift_id": gift}, "free-release"))
        assert read(reopened) == released
    with TestClient(create_app(settings)) as reopened:
        reopened.headers.update({"Authorization": client.headers["Authorization"]})
        assert read(reopened) == released


def test_ownership_unsupported_and_ineligible_gifts(client):
    initial = read(client)
    unsupported = next(g["id"] for g in initial["inventory"]["inventory"] if not g["pledgeSupported"])
    for gift in (unsupported, 999999999):
        assert post(client, "create", {"gift_id": gift, "weeks": 1}).status_code == 409
        assert read(client) == initial
    gift = gift_ids(initial)[0]
    ok(post(client, "create", {"gift_id": gift, "weeks": 1}))
    first = read(client)
    auth = client.headers["Authorization"]
    client.headers.update(bearer(login(client, {**USER, "id": USER["id"] + 1})["access_token"]))
    second = read(client)
    for action, body in [
        ("create", {"gift_id": gift, "weeks": 1}), ("repay", {"gift_id": gift}),
        ("pay-interest", {"gift_id": gift}), ("autopay", {"gift_id": gift, "enabled": True}),
        ("extend", {"gift_ids": [gift]}), ("quote", {"gift_ids": [gift]}),
    ]:
        assert post(client, action, body).status_code == 409
        assert read(client) == second
    # The same key belongs to this actor, not the first actor.
    own = gift_ids(second)[0]
    ok(post(client, "create", {"gift_id": own, "weeks": 1}))
    client.headers["Authorization"] = auth
    assert read(client) == first


def test_insufficient_batch_extension_rolls_back_all_loans_and_key(client, monkeypatch):
    now = int(time.time())
    monkeypatch.setattr(time, "time", lambda: now)
    gifts = gift_ids(read(client))[:2]
    for gift in gifts:
        ok(post(client, "create", {"gift_id": gift, "weeks": 1}, f"create-{gift}"))
    ok(client.post("/api/wallet/demo-withdraw",
                   json={"amount_nano": str(2 * PRINCIPAL), "destination": "demo"},
                   headers={"Idempotency-Key": "drain"}))
    before = read(client)
    assert balance(before) == 0
    assert post(client, "extend", {"gift_ids": gifts}, "retry").status_code == 409
    assert read(client) == before
    fund(client)
    funded = read(client)
    current = max(loan(before, gift)["due_at"] for gift in gifts) + DAY
    monkeypatch.setattr(time, "time", lambda: current)
    ok(post(client, "extend", {"gift_ids": gifts}, "retry"))
    after = read(client)
    assert balance(after) == balance(funded) - 90_000_000
    for gift in gifts:
        assert loan(after, gift)["due_at"] == current + 14 * DAY
    ok(post(client, "extend", {"gift_ids": gifts}, "retry"))
    assert read(client) == after


@pytest.mark.parametrize("catchup", ["read", "helper"])
def test_autopay_maturity_persisted_and_exactly_once(client, settings, monkeypatch, catchup):
    now = int(time.time())
    monkeypatch.setattr(time, "time", lambda: now)
    gift = gift_ids(read(client))[0]
    ok(post(client, "create", {"gift_id": gift, "weeks": 1}))
    fund(client)
    ok(post(client, "autopay", {"gift_id": gift, "enabled": True}, "autopay"))
    before = read(client)
    assert loan(before, gift)["autopay"] is True
    with TestClient(create_app(settings)) as reopened:
        reopened.headers.update({"Authorization": client.headers["Authorization"]})
        assert read(reopened) == before
        monkeypatch.setattr(time, "time", lambda: loan(before, gift)["due_at"])
        if catchup == "helper":
            from app.loans import process_due_loans
            process_due_loans(reopened.app.state.engine)
            process_due_loans(reopened.app.state.engine)
        after = read(reopened)
        assert loan(after, gift)["status"] == "repaid"
        assert balance(after) == balance(before) - 1_240_000_000
        assert gift in [g["id"] for g in after["inventory"]["inventory"]]
        assert read(reopened) == after
        assert len([tx for tx in after["wallet"]["transactions"] if tx["kind"] == "loan_repay"]) == 1


@pytest.mark.parametrize("enabled", [False, True])
def test_maturity_without_funds_or_autopay_never_partially_repays(client, monkeypatch, enabled):
    now = int(time.time())
    monkeypatch.setattr(time, "time", lambda: now)
    gift = gift_ids(read(client))[0]
    ok(post(client, "create", {"gift_id": gift, "weeks": 1}))
    if not enabled:
        fund(client)
    ok(post(client, "autopay", {"gift_id": gift, "enabled": enabled}, "auto"))
    before = read(client)
    monkeypatch.setattr(time, "time", lambda: loan(before, gift)["due_at"] + 1)
    assert read(client) == before


def test_autopay_discovery_failure_recovers_on_next_tick(client, monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app import loans
    from app.loan_models import DemoLoan

    now = int(time.time())
    monkeypatch.setattr(time, "time", lambda: now)
    gift = gift_ids(read(client))[0]
    ok(post(client, "create", {"gift_id": gift, "weeks": 1}))
    fund(client)
    ok(post(client, "autopay", {"gift_id": gift, "enabled": True}, "auto"))
    before = read(client)
    monkeypatch.setattr(time, "time", lambda: loan(before, gift)["due_at"])
    original_session = loans.Session
    attempts = 0

    def fail_first_session(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("test discovery unavailable")
        return original_session(*args, **kwargs)

    monkeypatch.setattr(loans, "Session", fail_first_session)
    loans.process_due_loans(client.app.state.engine)
    assert attempts == 1
    # Do not GET: read catch-up would mask a broken subsequent helper tick.
    with Session(client.app.state.engine) as db:
        record = db.scalar(select(DemoLoan).where(DemoLoan.user_id == USER["id"], DemoLoan.gift_id == gift))
        assert record.status == "active"
    loans.process_due_loans(client.app.state.engine)
    assert attempts > 1
    with Session(client.app.state.engine) as db:
        record = db.scalar(select(DemoLoan).where(DemoLoan.user_id == USER["id"], DemoLoan.gift_id == gift))
        assert record.status == "repaid"
    loans.process_due_loans(client.app.state.engine)
    after = read(client)
    assert balance(after) == balance(before) - 1_240_000_000
    assert len([tx for tx in after["wallet"]["transactions"] if tx["kind"] == "loan_repay"]) == 1
    assert read(client) == after


@pytest.mark.parametrize("action,body", [
    ("create", {"gift_id": True, "weeks": 1}), ("create", {"gift_id": "1", "weeks": 1}),
    ("create", {"gift_id": 1, "weeks": True}), ("create", {"gift_id": 1, "weeks": "1"}),
    ("create", {"gift_id": 1, "weeks": 0}), ("create", {"gift_id": 1, "weeks": 3}),
    ("create", {"gift_id": 1, "weeks": 1, "principal_nano": "999"}),
    ("repay", {"gift_id": -1}), ("repay", {"gift_id": 1, "user_id": 1}),
    ("pay-interest", {"gift_id": 1.5}), ("extend", {"gift_ids": []}),
    ("extend", {"gift_ids": [1, 1]}), ("extend", {"gift_ids": ["1"]}),
    ("autopay", {"gift_id": 1, "enabled": "true"}),
    ("autopay", {"gift_id": 1, "enabled": 1}),
    ("quote", {"gift_ids": []}), ("quote", {"gift_ids": [1, 1]}),
    ("quote", {"gift_ids": [True]}), ("quote", {"gift_ids": [1], "fee_nano": "0"}),
])
def test_strict_inputs_rejected_atomically(client, action, body):
    before = read(client)
    assert post(client, action, body).status_code == 422
    assert read(client) == before
    gift = gift_ids(before)[0]
    ok(post(client, "create", {"gift_id": gift, "weeks": 1}))


@pytest.mark.parametrize("action,body", [
    ("create", {"gift_id": 1, "weeks": 1}), ("repay", {"gift_id": 1}),
    ("pay-interest", {"gift_id": 1}), ("extend", {"gift_ids": [1]}),
    ("autopay", {"gift_id": 1, "enabled": True}),
])
def test_key_required_and_bearer_required(client, settings, action, body):
    assert client.post(f"/api/loans/{action}", json=body).status_code == 422
    with TestClient(create_app(settings)) as anonymous:
        assert post(anonymous, action, body).status_code == 401
        assert anonymous.get("/api/loans").status_code == 401
        assert anonymous.post("/api/loans/quote", json={"gift_ids": [1]}).status_code == 401
