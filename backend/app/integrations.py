"""Fail-closed contracts for future custody/payment adapters, never settlement code."""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from fastapi import Depends, HTTPException


class IntegrationUnavailable(RuntimeError):
    pass


class PaymentState(str, Enum):
    PENDING = 'pending'
    CONFIRMED = 'confirmed'
    FAILED = 'failed'


@dataclass(frozen=True)
class VerifiedPayment:
    """Only created by a signature-verifying, provider-specific adapter.

    A receipt alone MUST NOT credit a wallet: settlement must match a persisted
    invoice's user, asset, amount, network and recipient inside one transaction.
    """
    provider: str
    event_id: str
    invoice_id: str
    asset: str
    amount_nano: int
    state: PaymentState

    def __post_init__(self):
        for value in (self.provider, self.event_id, self.invoice_id):
            if not isinstance(value, str) or not value or len(value) > 128 or not value.isascii() or any(c.isspace() for c in value):
                raise ValueError('Invalid provider receipt identity')
        if self.asset != 'TON' or type(self.amount_nano) is not int or not 0 < self.amount_nano < 2**63:
            raise ValueError('A receipt requires an exact positive TON nano amount')
        if not isinstance(self.state, PaymentState):
            raise ValueError('Invalid payment state')


class PaymentProvider(Protocol):
    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> VerifiedPayment: ...


class DisabledPaymentProvider:
    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> VerifiedPayment:
        raise IntegrationUnavailable('A live payment adapter is not configured')


def integration_status(settings):
    return {
        'deployment_mode': settings.deployment_mode,
        'financial_asset': 'DEMO_TON' if settings.deployment_mode == 'demo' else None,
        'real_payments': False, 'real_gift_transfers': False, 'real_loans': False,
        'payments': {'ton': 'not_configured', 'cryptobot': 'not_configured'},
        'custody': 'not_configured',
        'live_activation': 'requires_adapter_implementation_and_acceptance_tests',
    }


# These routes initialize demo accounts even on some GETs. Production must not
# read/write them until live ledgers and custody have separate settlement paths.
DEMO_ROUTE_PREFIXES = ('/api/wallet', '/api/loans', '/api/trades', '/api/inventory', '/api/referrals')


def demo_route(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + '/') for prefix in DEMO_ROUTE_PREFIXES)


def register_integration_routes(app, settings, current_session):
    @app.get('/api/integrations/status')
    def status(session=Depends(current_session)):
        return integration_status(settings)

    # No generic webhook accepts unauthenticated or nominally "verified" JSON.
    # A future provider must implement its own signature/network verification.
    @app.post('/api/webhooks/{provider}')
    def unavailable_webhook(provider: str):
        raise HTTPException(503, 'Live payment and custody adapters are not configured')
