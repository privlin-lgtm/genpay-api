from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CardAuthorizationEvent(BaseModel):
    """Payload for the legacy synchronous /webhooks/card-auth demo endpoint."""

    event_type: str
    amount: float
    record_id: str
    user_id: str | None = None


ProcessorEventType = Literal[
    "authorization.created",
    "authorization.approved",
    "authorization.declined",
    "settlement.completed",
]


class ProcessorEventEnvelope(BaseModel):
    """
    Generic envelope for every processor -> GenPay webhook. `data` is validated
    against the event-specific schema below once event_type is known, mirroring
    how real processors (Stripe, Marqeta, Adyen) shape their webhook payloads.
    """

    event_id: str
    event_type: ProcessorEventType
    occurred_at: datetime
    data: dict


class MerchantReference(BaseModel):
    """Echoes back the GenPay-domain identifiers we supplied when initiating the authorization."""

    research_record_id: str
    user_id: str


class AuthorizationCreatedData(BaseModel):
    authorization_id: str
    merchant_reference: MerchantReference
    amount_cents: int
    currency: str = "USD"
    card_last4: str
    card_network: str


class AuthorizationApprovedData(BaseModel):
    authorization_id: str
    hold_expires_at: datetime


class AuthorizationDeclinedData(BaseModel):
    authorization_id: str
    decline_reason: str


class SettlementCompletedData(BaseModel):
    settlement_batch_id: str
    authorization_ids: list[str]
    total_amount_cents: int
