"""Talkroom API and local development server."""
import os
import base64
import hashlib
import hmac
import secrets
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
from dotenv import load_dotenv
import mzungu_chat_engine as mzungu_engine
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import DateTime, ForeignKey, Integer, String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)
DATABASE_URL = os.getenv("TALKROOM_DATABASE_URL", "sqlite:///./talkroom.db")
# Railway/Render provide 'postgres://' — SQLAlchemy requires 'postgresql://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
SECRET_KEY = os.getenv("TALKROOM_SECRET_KEY", "local-development-secret-change-before-production")
ALGORITHM = "HS256"
TOKEN_MINUTES = 60 * 24 * 7
CLICKPESA_BASE_URL = "https://api.clickpesa.com/third-parties"  # Base for all ClickPesa third-party calls
HARAKAPAY_BASE_URL = "https://harakapay.net/api/v1"
TEACHER_JOINING_FEE_TSH = 16000


def get_clickpesa_config():
    load_dotenv(BASE_DIR / ".env", override=True)
    return {
        "base_url": CLICKPESA_BASE_URL,
        "client_id": os.getenv("CLICKPESA_CLIENT_ID", ""),
        "api_key": os.getenv("CLICKPESA_API_KEY", ""),
        "checksum_key": os.getenv("CLICKPESA_CHECKSUM_KEY", ""),
        "webhook_url": os.getenv("CLICKPESA_WEBHOOK_URL", ""),
    }


def get_harakapay_config():
    load_dotenv(BASE_DIR / ".env", override=True)
    return {
        "base_url": HARAKAPAY_BASE_URL,
        "api_key": os.getenv("HARAKAPAY_API_KEY", ""),
        "webhook_url": os.getenv("HARAKAPAY_WEBHOOK_URL", ""),
    }


_engine_kwargs = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
bearer = HTTPBearer()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="learner")
    phone_number = mapped_column(String(20), nullable=True)
    balance_tsh: Mapped[int] = mapped_column(Integer, default=0)
    teacher_status: Mapped[str] = mapped_column(String(24), nullable=True)
    teacher_city: Mapped[str] = mapped_column(String(80), nullable=True)
    teacher_bio: Mapped[str] = mapped_column(String(400), nullable=True)
    payout_phone_number: Mapped[str] = mapped_column(String(20), nullable=True)
    teacher_profile_completed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_tsh: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(32))
    phone_number: Mapped[str] = mapped_column(String(20))
    beneficiary_name = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="completed")
    reference: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ChatEarning(Base):
    __tablename__ = "chat_earnings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    partner_name: Mapped[str] = mapped_column(String(80))
    amount_tsh: Mapped[int] = mapped_column(Integer)
    minutes_spent: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    teacher_name: Mapped[str] = mapped_column(String(80))
    topic: Mapped[str] = mapped_column(String(120))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="TZS")
    status: Mapped[str] = mapped_column(String(24), default="pending_payment")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_reference: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    paid_at = mapped_column(DateTime(timezone=True), nullable=True)


class TeacherEnrollmentPayment(Base):
    __tablename__ = "teacher_enrollment_payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="harakapay")
    provider_reference: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    paid_at = mapped_column(DateTime(timezone=True), nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(String(1200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RegisterInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone_number: str | None = None
    role: Literal["learner", "teacher"] = "learner"


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOutput(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    phone_number: str | None = None
    balance_tsh: int = 0
    teacher_status: str | None = None
    teacher_profile_completed: bool = False


class TokenOutput(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOutput


class BookingInput(BaseModel):
    teacher_name: str = Field(min_length=2, max_length=80)
    topic: str = Field(min_length=2, max_length=120)


class BookingOutput(BaseModel):
    id: int
    teacher_name: str
    topic: str
    duration_minutes: int
    amount_cents: int
    currency: str
    status: str


class PaymentInput(BaseModel):
    provider: str = "harakapay"
    phone_number: Any = None
    phoneNumber: Any = None

    @field_validator("provider", mode="before")
    @classmethod
    def clean_provider(cls, v: Any) -> str:
        if not v:
            return "harakapay"
        return str(v).lower().strip().replace("-", "_").replace(" ", "_")

    def get_phone_number(self) -> str | None:
        val = self.phone_number if self.phone_number is not None else self.phoneNumber
        if val is None or val == "":
            return None
        digits = "".join(ch for ch in str(val) if ch.isdigit())
        # Strip redundant 0 after 255 (e.g. 2550712345678 -> 255712345678)
        if digits.startswith("2550") and len(digits) == 13:
            digits = "255" + digits[4:]
        # Local format (e.g. 0712345678 or 0621123456) -> 255...
        elif digits.startswith("0") and len(digits) == 10:
            digits = "255" + digits[1:]
        # 9-digit format without leading 0 (e.g. 712345678) -> 255...
        elif len(digits) == 9 and digits.startswith(("6", "7")):
            digits = "255" + digits
        return digits or None


class PaymentOutput(BaseModel):
    id: int
    booking_id: int
    provider: str
    provider_reference: str
    status: str
    # USSD-PUSH: upstream status returned by ClickPesa (PROCESSING / SUCCESS / FAILED)
    ussd_status: str | None = None


class TeacherEnrollmentPaymentOutput(BaseModel):
    id: int
    amount_tsh: int = TEACHER_JOINING_FEE_TSH
    provider: str
    provider_reference: str
    status: str
    teacher_status: str
    ussd_status: str | None = None


class ProfileUpdateInput(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    email: EmailStr | None = None
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=128)


class TeacherOnboardingInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    city: str = Field(min_length=2, max_length=80)
    bio: str = Field(min_length=10, max_length=400)
    payout_phone_number: str = Field(min_length=9, max_length=20)


class TeacherBookingOutput(BookingOutput):
    learner_name: str


class LearnerBookingOutput(BookingOutput):
    created_at: datetime
    conversation_id: int | None = None


class ConversationOutput(BaseModel):
    id: int
    booking_id: int
    teacher_name: str
    learner_name: str
    status: str


class MessageInput(BaseModel):
    body: str = Field(min_length=1, max_length=1200)


class MessageOutput(BaseModel):
    id: int
    body: str
    sender_id: int
    sender_name: str
    created_at: datetime


def get_db():
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()


def user_output(user: User) -> UserOutput:
    return UserOutput(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        phone_number=user.phone_number,
        balance_tsh=user.balance_tsh or 0,
        teacher_status=user.teacher_status,
        teacher_profile_completed=bool(user.teacher_profile_completed),
    )


def booking_output(booking: Booking) -> BookingOutput:
    return BookingOutput(id=booking.id, teacher_name=booking.teacher_name, topic=booking.topic, duration_minutes=booking.duration_minutes, amount_cents=booking.amount_cents, currency=booking.currency, status=booking.status)


def payment_output(payment: Payment, ussd_status: str | None = None) -> PaymentOutput:
    return PaymentOutput(id=payment.id, booking_id=payment.booking_id, provider=payment.provider, provider_reference=payment.provider_reference, status=payment.status, ussd_status=ussd_status)


def enrollment_payment_output(payment: TeacherEnrollmentPayment, user: User, ussd_status: str | None = None) -> TeacherEnrollmentPaymentOutput:
    return TeacherEnrollmentPaymentOutput(id=payment.id, provider=payment.provider, provider_reference=payment.provider_reference, status=payment.status, teacher_status=user.teacher_status or "pending_payment", ussd_status=ussd_status)


def clickpesa_enabled() -> bool:
    cfg = get_clickpesa_config()
    return bool(cfg["client_id"] and cfg["api_key"] and cfg["webhook_url"])


def harakapay_enabled() -> bool:
    """HarakaPay needs a server-side API key; a callback URL is optional per request."""
    return bool(get_harakapay_config()["api_key"])


def harakapay_headers() -> dict[str, str]:
    return {"X-API-Key": get_harakapay_config()["api_key"], "Content-Type": "application/json"}


def harakapay_phone_number(phone_number: str) -> str:
    """HarakaPay documents Tanzanian collection numbers in local 0XXXXXXXXX form."""
    digits = "".join(ch for ch in phone_number if ch.isdigit())
    if digits.startswith("255") and len(digits) == 12:
        return "0" + digits[3:]
    return digits


async def create_harakapay_collection(amount_tsh: int, phone_number: str, description: str) -> tuple[str, str]:
    """Start a HarakaPay USSD collection and return its provider order ID."""
    cfg = get_harakapay_config()
    payload: dict[str, Any] = {"phone": harakapay_phone_number(phone_number), "amount": amount_tsh, "description": description}
    if cfg["webhook_url"]:
        payload["webhook_url"] = cfg["webhook_url"]
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{cfg['base_url']}/collect", headers=harakapay_headers(), json=payload)
    if response.is_error:
        try:
            detail = response.json().get("error") or response.json().get("message") or "HarakaPay could not start this payment"
        except Exception:
            detail = "HarakaPay could not start this payment"
        safe_phone = payload["phone"][:3] + "****" + payload["phone"][-3:]
        print(f"[HarakaPay Collection Failed] HTTP {response.status_code}; phone={safe_phone}; amount={amount_tsh}; response={response.text[:1000]}")
        raise HTTPException(status_code=400 if response.status_code < 500 else 502, detail=str(detail))
    data = response.json()
    if not data.get("success") or not data.get("order_id"):
        detail = str(data.get("error") or data.get("message") or "HarakaPay returned no order ID")
        safe_phone = payload["phone"][:3] + "****" + payload["phone"][-3:]
        print(f"[HarakaPay Collection Rejected] phone={safe_phone}; amount={amount_tsh}; response={detail}")
        raise HTTPException(status_code=400, detail=detail)
    return str(data["order_id"]), str(data.get("status") or "PENDING").upper()


async def query_harakapay_payment(order_id: str) -> dict:
    """Retrieve an authoritative collection status from HarakaPay."""
    cfg = get_harakapay_config()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{cfg['base_url']}/status/{order_id}", headers=harakapay_headers())
    if response.status_code == 404:
        return {"status": "PENDING"}
    if response.is_error:
        raise HTTPException(status_code=502, detail="HarakaPay payment status query failed")
    data = response.json()
    return data.get("payment") or {"status": data.get("status", "PENDING")}


def clickpesa_checksum(payload: dict) -> str:
    cfg = get_clickpesa_config()
    compact_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(cfg["checksum_key"].encode(), compact_payload.encode(), hashlib.sha256).hexdigest()


async def clickpesa_token() -> str:
    """Obtain a short-lived JWT from ClickPesa using the stored client credentials."""
    cfg = get_clickpesa_config()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{cfg['base_url']}/generate-token",
            headers={"client-id": cfg["client_id"], "api-key": cfg["api_key"]},
        )
    if response.is_error:
        raise HTTPException(status_code=502, detail="ClickPesa could not authorize this payment request")
    token = response.json().get("token")
    if not token:
        raise HTTPException(status_code=502, detail="ClickPesa returned no authorization token")
    return token


def clickpesa_auth_header(token: str) -> str:
    """ClickPesa accepts a Bearer token; tolerate accounts returning the prefix already."""
    return token if token.lower().startswith("bearer ") else f"Bearer {token}"


def _clickpesa_order_ref(booking: Booking) -> str:
    """Generate a unique alphanumeric order reference ≤ 20 chars (provider limit)."""
    suffix = secrets.token_hex(4).upper()  # 8 hex chars
    ref = f"TR{booking.id}{suffix}"        # e.g. TR12ABCD1234
    return ref[:20]                         # hard-cap at 20


async def create_clickpesa_ussd_push(booking: Booking, phone_number: str) -> tuple[str, str]:
    """Initiate a USSD-PUSH collection via the ClickPesa Collection API.

    Returns (order_reference, ussd_status) where ussd_status is the immediate
    upstream value (usually 'PROCESSING').
    """
    cfg = get_clickpesa_config()
    token = await clickpesa_token()
    order_reference = _clickpesa_order_ref(booking)
    # Collection API amounts are in TZS as a string; booking.amount_cents stores
    # the value already in the smallest unit of the display currency.
    # For TZS there are no sub-units, so we pass the integer directly.
    amount_str = str(int(booking.amount_cents))
    payload: dict = {
        "amount": amount_str,
        "currency": booking.currency,      # must be "TZS"
        "orderReference": order_reference,
        "phoneNumber": phone_number,
    }
    if cfg["checksum_key"]:
        payload["checksum"] = clickpesa_checksum(payload)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{cfg['base_url']}/payments/initiate-ussd-push-request",
            headers={"Authorization": clickpesa_auth_header(token), "Content-Type": "application/json"},
            json=payload,
        )
    if response.is_error:
        print(f"[ClickPesa Initiate Failed] HTTP {response.status_code}: {response.text}")
        try:
            data = response.json()
            raw_msg = data.get("message") or data.get("error")
            if isinstance(raw_msg, list):
                detail = ", ".join(str(m) for m in raw_msg)
            elif isinstance(raw_msg, str):
                detail = raw_msg
            else:
                detail = "ClickPesa could not initiate the USSD-PUSH request"
        except Exception:
            detail = f"ClickPesa responded with HTTP {response.status_code}"

        if "not active" in detail.lower():
            detail += ". (Your ClickPesa application has not activated this method yet. Please try an Airtel Money or Tigo Pesa number, or activate this channel in your ClickPesa portal)."
            raise HTTPException(status_code=400, detail=detail)
        elif "phonenumber" in detail.lower() or "phone number" in detail.lower():
            raise HTTPException(status_code=400, detail=detail)
        elif "unable to initiate" in detail.lower():
            detail += " (Please try an Airtel Money or Tigo Pesa number)."
            raise HTTPException(status_code=400, detail=detail)

        raise HTTPException(status_code=502, detail=detail)
    data = response.json()
    ussd_status = data.get("status", "PROCESSING")
    return order_reference, ussd_status


async def create_teacher_enrollment_push(user: User, phone_number: str) -> tuple[str, str]:
    """Collect the one-time TSh 16,000 teacher activation fee via ClickPesa."""
    cfg = get_clickpesa_config()
    token = await clickpesa_token()
    order_reference = f"JOIN{user.id}{secrets.token_hex(4).upper()}"[:20]
    payload: dict = {
        "amount": str(TEACHER_JOINING_FEE_TSH),
        "currency": "TZS",
        "orderReference": order_reference,
        "phoneNumber": phone_number,
    }
    if cfg["checksum_key"]:
        payload["checksum"] = clickpesa_checksum(payload)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{cfg['base_url']}/payments/initiate-ussd-push-request",
            headers={"Authorization": clickpesa_auth_header(token), "Content-Type": "application/json"},
            json=payload,
        )
    if response.is_error:
        try:
            data = response.json()
            detail = data.get("message") or data.get("error") or "ClickPesa could not initiate the joining payment"
            if isinstance(detail, list):
                detail = ", ".join(map(str, detail))
        except Exception:
            detail = "ClickPesa could not initiate the joining payment"
        raise HTTPException(status_code=400 if response.status_code < 500 else 502, detail=str(detail))
    return order_reference, response.json().get("status", "PROCESSING")


async def query_clickpesa_payment(order_reference: str) -> dict:
    """Query the ClickPesa Collection API for the current status of a payment."""
    token = await clickpesa_token()
    cfg = get_clickpesa_config()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{cfg['base_url']}/payments/{order_reference}",
            headers={"Authorization": clickpesa_auth_header(token)},
        )
    if response.status_code == 404:
        return {"status": "PENDING", "message": "Not found yet"}
    if response.is_error:
        raise HTTPException(status_code=502, detail="ClickPesa payment status query failed")
    results = response.json()
    # API returns an array; take first matching record
    if isinstance(results, list) and results:
        return results[0]
    return {"status": "PENDING"}


def clickpesa_payout_payload(amount_tsh: int, phone_number: str, order_reference: str) -> dict:
    """Build the documented Mobile Money Payout payload.

    For this ClickPesa endpoint the mobile number is the beneficiary; there is
    no separate beneficiary-registration request.
    """
    payload: dict = {
        "amount": amount_tsh,
        "phoneNumber": phone_number,
        "currency": "TZS",
        "orderReference": order_reference,
    }
    if get_clickpesa_config()["checksum_key"]:
        payload["checksum"] = clickpesa_checksum(payload)
    return payload


async def preview_clickpesa_mobile_payout(amount_tsh: int, phone_number: str, order_reference: str) -> str | None:
    """Validate the beneficiary number and return its registered name when available."""
    cfg = get_clickpesa_config()
    token = await clickpesa_token()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{cfg['base_url']}/payouts/preview-mobile-money-payout",
            headers={"Authorization": clickpesa_auth_header(token), "Content-Type": "application/json"},
            json=clickpesa_payout_payload(amount_tsh, phone_number, order_reference),
        )
    if response.is_error:
        try:
            detail = response.json().get("message") or response.json().get("error") or "ClickPesa could not verify this beneficiary"
        except Exception:
            detail = "ClickPesa could not verify this beneficiary"
        raise HTTPException(status_code=400 if response.status_code < 500 else 502, detail=str(detail))
    receiver = response.json().get("receiver") or {}
    return receiver.get("accountName") or None


async def create_clickpesa_mobile_payout(amount_tsh: int, phone_number: str, order_reference: str) -> str:
    """Send a teacher's earned balance to their mobile wallet through ClickPesa."""
    cfg = get_clickpesa_config()
    token = await clickpesa_token()
    payload = clickpesa_payout_payload(amount_tsh, phone_number, order_reference)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{cfg['base_url']}/payouts/create-mobile-money-payout",
            headers={"Authorization": clickpesa_auth_header(token), "Content-Type": "application/json"},
            json=payload,
        )
    if response.is_error:
        try:
            detail = response.json().get("message") or response.json().get("error") or "ClickPesa could not start this payout"
        except Exception:
            detail = "ClickPesa could not start this payout"
        raise HTTPException(status_code=400 if response.status_code < 500 else 502, detail=str(detail))
    return response.json().get("status", "AUTHORIZED")


def teacher_booking_output(booking: Booking, learner: User) -> TeacherBookingOutput:
    return TeacherBookingOutput(**booking_output(booking).model_dump(), learner_name=learner.name)


def require_teacher(user: User) -> User:
    if user.role != "teacher":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Teacher account required")
    if user.teacher_status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lipa ada ya kujiunga TSh 16,000 ili ku-activate akaunti ya mwalimu")
    return user


def can_access_booking(booking: Booking, user: User) -> bool:
    return booking.learner_id == user.id or (user.role == "teacher" and booking.teacher_name == user.name)


def make_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES)
    return jwt.encode({"sub": str(user.id), "exp": expires}, SECRET_KEY, algorithm=ALGORITHM)


def hash_password(password: str) -> str:
    """Create a salted scrypt hash using only the Python standard library."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, encoded_salt, encoded_digest = stored_hash.split("$", 2)
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(encoded_salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(digest, base64.b64decode(encoded_digest))
    except (ValueError, TypeError):
        return False


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", ""))
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired login token")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return user


optional_bearer = HTTPBearer(auto_error=False)


def optional_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer), db: Session = Depends(get_db)) -> Optional[User]:
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", ""))
        return db.get(User, user_id)
    except Exception:
        return None


app = FastAPI(title="ChatPay API", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    messages = []
    for err in errors:
        loc = " -> ".join(str(l) for l in err.get("loc", []) if l != "body")
        field = f"{loc}: " if loc else ""
        messages.append(f"{field}{err.get('msg', 'invalid value')}")
    friendly_msg = "; ".join(messages) or "Invalid request parameters"
    print(f"[422 Validation Error] {request.method} {request.url.path} -> {friendly_msg}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": friendly_msg, "errors": errors},
    )


@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        try:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN phone_number VARCHAR(20)")
        except Exception:
            pass
        try:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN balance_tsh INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN teacher_status VARCHAR(24)")
        except Exception:
            pass
        for column in (
            "teacher_city VARCHAR(80)",
            "teacher_bio VARCHAR(400)",
            "payout_phone_number VARCHAR(20)",
            "teacher_profile_completed INTEGER DEFAULT 0",
        ):
            try:
                conn.exec_driver_sql(f"ALTER TABLE users ADD COLUMN {column}")
            except Exception:
                pass
        try:
            conn.exec_driver_sql("ALTER TABLE withdrawals ADD COLUMN beneficiary_name VARCHAR(160)")
        except Exception:
            pass

    ensure_test_accounts()


def ensure_test_accounts():
    """Ensure reliable, active test accounts for both teacher and learner with pre-seeded chatroom session."""
    with SessionLocal() as db:
        pw_hash = hash_password("Password123!")

        # 1. Teacher Account
        teacher = db.scalar(select(User).where(User.email == "teacher@talkroom.com"))
        if not teacher:
            teacher = User(
                name="Neema M.",
                email="teacher@talkroom.com",
                password_hash=pw_hash,
                role="teacher",
                teacher_status="active",
                teacher_profile_completed=1,
                teacher_city="Dar es Salaam",
                teacher_bio="Mwalimu mzoefu wa Kiswahili na utamaduni. Karibu tujifunze pamoja!",
                payout_phone_number="255712345678",
                phone_number="255712345678",
                balance_tsh=150000,
            )
            db.add(teacher)
            db.commit()
            db.refresh(teacher)
        else:
            teacher.password_hash = pw_hash
            teacher.role = "teacher"
            teacher.teacher_status = "active"
            teacher.teacher_profile_completed = 1
            teacher.name = "Neema M."
            db.commit()

        # Update legacy test.teacher@talkroom.local as well if present
        legacy_teacher = db.scalar(select(User).where(User.email == "test.teacher@talkroom.local"))
        if legacy_teacher:
            legacy_teacher.password_hash = pw_hash
            legacy_teacher.teacher_status = "active"
            legacy_teacher.teacher_profile_completed = 1
            db.commit()

        # 2. Learner Account
        learner = db.scalar(select(User).where(User.email == "learner@talkroom.com"))
        if not learner:
            learner = User(
                name="Test Learner",
                email="learner@talkroom.com",
                password_hash=pw_hash,
                role="learner",
                phone_number="255787654321",
                balance_tsh=50000,
            )
            db.add(learner)
            db.commit()
            db.refresh(learner)
        else:
            learner.password_hash = pw_hash
            learner.role = "learner"
            db.commit()

        # Update legacy test.learner@talkroom.local as well if present
        legacy_learner = db.scalar(select(User).where(User.email == "test.learner@talkroom.local"))
        if legacy_learner:
            legacy_learner.password_hash = pw_hash
            db.commit()

        # 3. Accepted Booking & Active Conversation for direct chatroom testing
        booking_accepted = db.scalar(
            select(Booking).where(
                Booking.learner_id == learner.id,
                Booking.teacher_name == teacher.name,
                Booking.status == "accepted",
            )
        )
        if not booking_accepted:
            booking_accepted = Booking(
                learner_id=learner.id,
                teacher_name=teacher.name,
                topic="Kiswahili cha Mazungumzo & Safari",
                duration_minutes=30,
                amount_cents=30000,
                currency="TZS",
                status="accepted",
            )
            db.add(booking_accepted)
            db.commit()
            db.refresh(booking_accepted)

        conv = db.scalar(select(Conversation).where(Conversation.booking_id == booking_accepted.id))
        if not conv:
            conv = Conversation(booking_id=booking_accepted.id)
            db.add(conv)
            db.commit()
            db.refresh(conv)

        # Ensure seed messages
        msg_count = db.scalar(select(func.count(Message.id)).where(Message.conversation_id == conv.id))
        if not msg_count or msg_count == 0:
            db.add_all([
                Message(conversation_id=conv.id, sender_id=teacher.id, body="Habari ya leo! Karibu sana kwenye chumba chetu cha mazungumzo ya Kiswahili."),
                Message(conversation_id=conv.id, sender_id=learner.id, body="Habari mwalimu Neema! Asante sana, nimefurahi sana kuanza kipindi hiki na wewe."),
                Message(conversation_id=conv.id, sender_id=teacher.id, body="Vizuri mno! Tunaweza kuanza kwa mazoezi ya safari za wanyama Serengeti au mazungumzo ya sokoni."),
            ])
            db.commit()

        # 4. Requested booking for testing teacher "Accept request" workflow
        booking_requested = db.scalar(
            select(Booking).where(
                Booking.learner_id == learner.id,
                Booking.teacher_name == teacher.name,
                Booking.status == "requested",
            )
        )
        if not booking_requested:
            booking_requested = Booking(
                learner_id=learner.id,
                teacher_name=teacher.name,
                topic="Mazoezi ya Matamshi na Msamiati wa Kiswahili",
                duration_minutes=30,
                amount_cents=30000,
                currency="TZS",
                status="requested",
            )
            db.add(booking_requested)
            db.commit()


@app.post("/api/auth/register", response_model=TokenOutput, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterInput, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists")
    user = User(
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        phone_number=payload.phone_number.strip() if payload.phone_number else None,
        balance_tsh=0,
        teacher_status="pending_payment" if payload.role == "teacher" else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOutput(access_token=make_token(user), user=user_output(user))


@app.post("/api/auth/login", response_model=TokenOutput)
def login(payload: LoginInput, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email or password is incorrect")
    return TokenOutput(access_token=make_token(user), user=user_output(user))


@app.get("/api/auth/me", response_model=UserOutput)
def me(user: User = Depends(current_user)):
    return user_output(user)


@app.put("/api/auth/profile", response_model=TokenOutput)
def update_profile(payload: ProfileUpdateInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.name:
        user.name = payload.name.strip()
    if payload.email:
        new_email = payload.email.lower()
        if new_email != user.email:
            existing = db.scalar(select(User).where(User.email == new_email))
            if existing:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists")
            user.email = new_email
    if payload.new_password:
        if not payload.current_password or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
        user.password_hash = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)
    return TokenOutput(access_token=make_token(user), user=user_output(user))


@app.get("/api/teacher/onboarding")
def get_teacher_onboarding(user: User = Depends(current_user)):
    require_teacher(user)
    return {
        "name": user.name,
        "city": user.teacher_city or "",
        "bio": user.teacher_bio or "",
        "payout_phone_number": user.payout_phone_number or user.phone_number or "",
        "completed": bool(user.teacher_profile_completed),
    }


@app.put("/api/teacher/onboarding", response_model=TokenOutput)
def complete_teacher_onboarding(payload: TeacherOnboardingInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_teacher(user)
    payout_phone = PaymentInput(phone_number=payload.payout_phone_number).get_phone_number()
    if not payout_phone or len(payout_phone) < 12:
        raise HTTPException(status_code=422, detail="Weka namba halali ya kupokea pesa")
    user.name = payload.name.strip()
    user.teacher_city = payload.city.strip()
    user.teacher_bio = payload.bio.strip()
    user.payout_phone_number = payout_phone
    user.teacher_profile_completed = 1
    db.commit()
    db.refresh(user)
    return TokenOutput(access_token=make_token(user), user=user_output(user))


@app.post("/api/teacher/enrollment/payment", response_model=TeacherEnrollmentPaymentOutput, status_code=status.HTTP_201_CREATED)
async def initiate_teacher_enrollment_payment(payload: PaymentInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher accounts can pay the joining fee")
    if user.teacher_status == "active":
        raise HTTPException(status_code=409, detail="Your teacher account is already active")
    if not harakapay_enabled():
        raise HTTPException(status_code=503, detail="HarakaPay is not configured. Add HARAKAPAY_API_KEY to .env.")
    phone = payload.get_phone_number() or user.phone_number
    if not phone or len(phone) < 12:
        raise HTTPException(status_code=422, detail="Weka namba halali ya mobile money")
    order_reference, ussd_status = await create_harakapay_collection(TEACHER_JOINING_FEE_TSH, phone, "Talkroom teacher activation fee")
    payment = db.scalar(select(TeacherEnrollmentPayment).where(TeacherEnrollmentPayment.user_id == user.id))
    if payment:
        payment.provider = "harakapay"
        payment.provider_reference = order_reference
        payment.status = "pending"
    else:
        payment = TeacherEnrollmentPayment(user_id=user.id, provider="harakapay", provider_reference=order_reference)
        db.add(payment)
    user.phone_number = phone
    user.teacher_status = "pending_payment"
    db.commit()
    db.refresh(payment)
    db.refresh(user)
    return enrollment_payment_output(payment, user, ussd_status)


@app.get("/api/teacher/enrollment/payment/{payment_id}/status", response_model=TeacherEnrollmentPaymentOutput)
async def poll_teacher_enrollment_payment(payment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    payment = db.get(TeacherEnrollmentPayment, payment_id)
    if not payment or payment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Joining payment not found")
    if payment.status in {"paid", "failed"}:
        return enrollment_payment_output(payment, user)
    upstream = await query_harakapay_payment(payment.provider_reference) if payment.provider == "harakapay" else await query_clickpesa_payment(payment.provider_reference)
    upstream_status = str(upstream.get("status", "PROCESSING")).upper()
    if upstream_status in {"SUCCESS", "SETTLED", "COMPLETED"}:
        payment.status = "paid"
        payment.paid_at = datetime.now(timezone.utc)
        user.teacher_status = "active"
        db.commit()
    elif upstream_status in {"FAILED", "CANCELLED", "CANCELED"}:
        payment.status = "failed"
        user.teacher_status = "payment_failed"
        db.commit()
    db.refresh(payment)
    db.refresh(user)
    return enrollment_payment_output(payment, user, upstream_status)


@app.post("/api/teacher/enrollment/payment/{payment_id}/cancel", response_model=TeacherEnrollmentPaymentOutput)
async def cancel_teacher_enrollment_payment(payment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Cancel a pending activation payment locally after checking HarakaPay."""
    payment = db.get(TeacherEnrollmentPayment, payment_id)
    if not payment or payment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Joining payment not found")
    if payment.status == "paid":
        raise HTTPException(status_code=409, detail="This payment is already complete and cannot be cancelled")
    if payment.provider == "harakapay":
        upstream = await query_harakapay_payment(payment.provider_reference)
        if str(upstream.get("status", "PENDING")).upper() == "COMPLETED":
            payment.status = "paid"
            payment.paid_at = datetime.now(timezone.utc)
            user.teacher_status = "active"
            db.commit()
            raise HTTPException(status_code=409, detail="This payment was already completed")
    payment.status = "cancelled"
    user.teacher_status = "payment_cancelled"
    db.commit()
    db.refresh(payment)
    db.refresh(user)
    return enrollment_payment_output(payment, user, "CANCELLED")


@app.get("/api/learner/bookings", response_model=list[LearnerBookingOutput])
def learner_bookings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    bookings = db.scalars(select(Booking).where(Booking.learner_id == user.id).order_by(Booking.created_at.desc())).all()
    results = []
    for b in bookings:
        conv = db.scalar(select(Conversation).where(Conversation.booking_id == b.id))
        conv_id = conv.id if conv else None
        results.append(LearnerBookingOutput(**booking_output(b).model_dump(), created_at=b.created_at, conversation_id=conv_id))
    return results


# Prices in TZS (Tanzania Shilling) — the Collection API only accepts TZS
TEACHER_PRICES = {"Neema M.": 30000, "Baraka J.": 35000, "Asha K.": 28000}


@app.post("/api/bookings", response_model=BookingOutput, status_code=status.HTTP_201_CREATED)
def create_booking(payload: BookingInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.teacher_name not in TEACHER_PRICES:
        raise HTTPException(status_code=404, detail="That teacher is not available")
    booking = Booking(learner_id=user.id, teacher_name=payload.teacher_name, topic=payload.topic.strip(), amount_cents=TEACHER_PRICES[payload.teacher_name])
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking_output(booking)


@app.get("/api/bookings/{booking_id}", response_model=BookingOutput)
def get_booking(booking_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking or booking.learner_id != user.id:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking_output(booking)


@app.post("/api/bookings/{booking_id}/payment", response_model=PaymentOutput, status_code=status.HTTP_201_CREATED)
async def initiate_payment(booking_id: int, payload: PaymentInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking or booking.learner_id != user.id:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status != "pending_payment":
        raise HTTPException(status_code=409, detail="This booking has already been paid")

    phone = payload.get_phone_number()
    provider = payload.provider
    is_harakapay = provider in {"harakapay", "mpesa", "airtel_money", "tigo_pesa", "halopesa"}

    if is_harakapay:
        if not harakapay_enabled():
            raise HTTPException(
                status_code=503,
                detail="HarakaPay is not configured. Add HARAKAPAY_API_KEY to .env.",
            )
        if not phone or len(phone) < 10:
            raise HTTPException(
                status_code=422,
                detail="A valid mobile money phone number is required (e.g. 255712345678 or 0712345678).",
            )

    existing = db.scalar(select(Payment).where(Payment.booking_id == booking.id))
    if existing and existing.status != "paid":
        if is_harakapay:
            order_reference, ussd_status = await create_harakapay_collection(booking.amount_cents, phone, f"Talkroom session with {booking.teacher_name}")
            existing.provider = "harakapay"
            existing.provider_reference = order_reference
            db.commit()
            db.refresh(existing)
            return payment_output(existing, ussd_status)
        else:
            existing.provider = provider
            db.commit()
            db.refresh(existing)
            return payment_output(existing)

    if is_harakapay:
        order_reference, ussd_status = await create_harakapay_collection(booking.amount_cents, phone, f"Talkroom session with {booking.teacher_name}")
        payment = Payment(booking_id=booking.id, provider="harakapay", provider_reference=order_reference)
    else:
        payment = Payment(booking_id=booking.id, provider=provider, provider_reference=f"TR-{secrets.token_hex(5).upper()}")
        ussd_status = None
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment_output(payment, ussd_status)


@app.post("/api/payments/{payment_id}/confirm", response_model=PaymentOutput)
def confirm_test_payment(payment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Development-only confirmation. Replace with a verified provider webhook in production."""
    payment = db.get(Payment, payment_id)
    booking = db.get(Booking, payment.booking_id) if payment else None
    if not payment or not booking or booking.learner_id != user.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status == "paid":
        return payment_output(payment)
    if payment.provider in {"clickpesa", "harakapay"}:
        raise HTTPException(status_code=403, detail="Provider payments are confirmed by a verified status check or webhook")
    payment.status = "paid"
    payment.paid_at = datetime.now(timezone.utc)
    booking.status = "requested"
    db.commit()
    db.refresh(payment)
    return payment_output(payment)


@app.post("/api/payments/{payment_id}/cancel", response_model=PaymentOutput)
async def cancel_payment(payment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Cancel a pending checkout locally after checking the provider's real status.

    HarakaPay does not publish an API for retracting an already-issued USSD
    prompt. If a customer later approves that prompt, the webhook still records
    the completed payment so no money is lost.
    """
    payment = db.get(Payment, payment_id)
    booking = db.get(Booking, payment.booking_id) if payment else None
    if not payment or not booking or booking.learner_id != user.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status == "paid":
        raise HTTPException(status_code=409, detail="This payment is already complete and cannot be cancelled")
    if payment.provider == "harakapay":
        upstream = await query_harakapay_payment(payment.provider_reference)
        upstream_status = str(upstream.get("status", "PENDING")).upper()
        if upstream_status == "COMPLETED":
            payment.status = "paid"
            payment.paid_at = datetime.now(timezone.utc)
            booking.status = "requested"
            db.commit()
            raise HTTPException(status_code=409, detail="This payment was already completed")
    payment.status = "cancelled"
    db.commit()
    db.refresh(payment)
    return payment_output(payment, "CANCELLED")


@app.get("/api/payments/{payment_id}/status", response_model=PaymentOutput)
async def poll_payment_status(payment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Poll the collection provider for the current status of a USSD-PUSH payment.

    The frontend calls this every few seconds while waiting for the customer to
    enter their PIN. When the provider confirms via webhook the local status is
    already updated; this endpoint is a convenience fallback.
    """
    payment = db.get(Payment, payment_id)
    booking = db.get(Booking, payment.booking_id) if payment else None
    if not payment or not booking or booking.learner_id != user.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.provider not in {"clickpesa", "harakapay"}:
        return payment_output(payment)
    # If already resolved locally (via webhook), return immediately
    if payment.status in {"paid", "failed"}:
        return payment_output(payment)
    upstream = await query_harakapay_payment(payment.provider_reference) if payment.provider == "harakapay" else await query_clickpesa_payment(payment.provider_reference)
    upstream_status = str(upstream.get("status", "PROCESSING")).upper()
    if upstream_status in {"SUCCESS", "SETTLED", "COMPLETED"}:
        payment.status = "paid"
        payment.paid_at = datetime.now(timezone.utc)
        booking.status = "requested"
        db.commit()
        db.refresh(payment)
    elif upstream_status in {"FAILED", "CANCELLED", "CANCELED"}:
        payment.status = "failed"
        db.commit()
        db.refresh(payment)
    return payment_output(payment, upstream_status)


@app.post("/api/payments/harakapay/webhook")
async def harakapay_webhook(request: Request, db: Session = Depends(get_db)):
    """Reconcile a HarakaPay callback using a server-side status lookup.

    HarakaPay's documented callback has no signature, so its body is used only
    to identify the order. The provider status endpoint is the source of truth.
    """
    try:
        callback = await request.json()
    except Exception:
        return {"received": False, "detail": "Empty or non-JSON body"}
    order_id = callback.get("order_id") if isinstance(callback, dict) else None
    if not order_id:
        return {"received": False, "detail": "Missing order_id"}

    payment = db.scalar(select(Payment).where(Payment.provider_reference == str(order_id), Payment.provider == "harakapay"))
    enrollment = None if payment else db.scalar(select(TeacherEnrollmentPayment).where(TeacherEnrollmentPayment.provider_reference == str(order_id), TeacherEnrollmentPayment.provider == "harakapay"))
    if not payment and not enrollment:
        return {"received": True, "detail": "Unknown order ID"}

    upstream = await query_harakapay_payment(str(order_id))
    upstream_status = str(upstream.get("status", "PENDING")).upper()
    if payment:
        booking = db.get(Booking, payment.booking_id)
        reported_amount = upstream.get("amount")
        if reported_amount is not None and int(float(reported_amount)) != booking.amount_cents:
            raise HTTPException(status_code=400, detail="HarakaPay amount does not match this booking")
        if upstream_status == "COMPLETED" and payment.status != "paid":
            payment.status = "paid"
            payment.paid_at = datetime.now(timezone.utc)
            booking.status = "requested"
        elif upstream_status in {"FAILED", "CANCELLED", "CANCELED"} and payment.status != "paid":
            payment.status = "failed"
    else:
        teacher = db.get(User, enrollment.user_id)
        reported_amount = upstream.get("amount")
        if reported_amount is not None and int(float(reported_amount)) != TEACHER_JOINING_FEE_TSH:
            raise HTTPException(status_code=400, detail="HarakaPay joining fee amount does not match")
        if upstream_status == "COMPLETED":
            enrollment.status = "paid"
            enrollment.paid_at = datetime.now(timezone.utc)
            teacher.teacher_status = "active"
        elif upstream_status in {"FAILED", "CANCELLED", "CANCELED"}:
            enrollment.status = "failed"
            teacher.teacher_status = "payment_failed"
    db.commit()
    return {"received": True}


@app.post("/api/payments/clickpesa/webhook")
async def clickpesa_webhook(request: Request, db: Session = Depends(get_db)):
    """Idempotently record a ClickPesa Collection API webhook notification.

    The webhook is sent by ClickPesa when a USSD-PUSH payment transitions to
    SUCCESS or FAILED.  We never trust browser-side confirmations.
    """
    cfg = get_clickpesa_config()
    try:
        payload = await request.json()
    except Exception:
        return {"received": False, "detail": "Empty or non-JSON body"}
    if not isinstance(payload, dict):
        return {"received": False, "detail": "Payload must be a JSON object"}

    received_checksum = payload.pop("checksum", None)
    payload.pop("checksumMethod", None)
    if cfg["checksum_key"] and (
        not received_checksum
        or not hmac.compare_digest(received_checksum, clickpesa_checksum(payload))
    ):
        raise HTTPException(status_code=401, detail="Invalid ClickPesa checksum")

    # Collection API webhook payload: top-level orderReference and status fields
    data = payload.get("data", payload)  # some versions nest under "data"
    order_ref = data.get("orderReference") or payload.get("orderReference")
    upstream_status = data.get("status") or payload.get("status", "")
    event = payload.get("event", "")

    payment = db.scalar(
        select(Payment).where(
            Payment.provider_reference == order_ref,
            Payment.provider == "clickpesa",
        )
    )
    if not payment:
        enrollment = db.scalar(
            select(TeacherEnrollmentPayment).where(
                TeacherEnrollmentPayment.provider_reference == order_ref,
                TeacherEnrollmentPayment.provider == "clickpesa",
            )
        )
        if enrollment:
            teacher = db.get(User, enrollment.user_id)
            success = upstream_status in {"SUCCESS", "SETTLED"} or event == "PAYMENT RECEIVED"
            failed = upstream_status == "FAILED" or event == "PAYMENT FAILED"
            collected = str(data.get("collectedAmount", "") or payload.get("collectedAmount", ""))
            if success and collected and collected not in {str(TEACHER_JOINING_FEE_TSH), "16000"}:
                raise HTTPException(status_code=400, detail="ClickPesa joining fee amount does not match")
            if success:
                enrollment.status = "paid"
                enrollment.paid_at = datetime.now(timezone.utc)
                teacher.teacher_status = "active"
            elif failed:
                enrollment.status = "failed"
                teacher.teacher_status = "payment_failed"
            db.commit()
            return {"received": True}
        withdrawal = db.scalar(select(Withdrawal).where(Withdrawal.reference == order_ref))
        if withdrawal:
            payout_success = upstream_status in {"SUCCESS", "SETTLED"}
            payout_failed = upstream_status in {"FAILED", "REVERSED"} or event in {"PAYOUT REVERSED", "PAYOUT REFUNDED"}
            if payout_success:
                withdrawal.status = "completed"
            elif payout_failed and withdrawal.status == "processing":
                withdrawal.status = "failed"
                recipient = db.get(User, withdrawal.user_id)
                recipient.balance_tsh = (recipient.balance_tsh or 0) + withdrawal.amount_tsh
            db.commit()
            return {"received": True}
        # Return 200 so ClickPesa does not keep retrying for unrecognised refs
        return {"received": True, "detail": "Unknown order reference"}
    booking = db.get(Booking, payment.booking_id)

    success = upstream_status in {"SUCCESS", "SETTLED"} or event == "PAYMENT RECEIVED"
    failed = upstream_status == "FAILED" or event == "PAYMENT FAILED"

    if success and payment.status != "paid":
        # Verify the collected amount matches the booking (both stored in TZS)
        collected = str(data.get("collectedAmount", "") or payload.get("collectedAmount", ""))
        expected_variants = {
            str(booking.amount_cents),
            str(int(booking.amount_cents)),
        }
        if collected and collected not in expected_variants and collected != "":
            raise HTTPException(status_code=400, detail="ClickPesa amount does not match this booking")
        payment.status = "paid"
        payment.paid_at = datetime.now(timezone.utc)
        booking.status = "requested"
    elif failed and payment.status != "paid":
        payment.status = "failed"

    db.commit()
    return {"received": True}


@app.get("/api/teacher/bookings", response_model=list[TeacherBookingOutput])
def teacher_bookings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_teacher(user)
    bookings = db.scalars(select(Booking).where(Booking.teacher_name == user.name).order_by(Booking.created_at.desc())).all()
    return [teacher_booking_output(booking, db.get(User, booking.learner_id)) for booking in bookings]


@app.post("/api/teacher/bookings/{booking_id}/accept", response_model=ConversationOutput)
def accept_booking(booking_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_teacher(user)
    booking = db.get(Booking, booking_id)
    if not booking or booking.teacher_name != user.name:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status not in {"requested", "accepted"}:
        raise HTTPException(status_code=409, detail="This booking is not ready to accept")
    conversation = db.scalar(select(Conversation).where(Conversation.booking_id == booking.id))
    if not conversation:
        booking.status = "accepted"
        conversation = Conversation(booking_id=booking.id)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    learner = db.get(User, booking.learner_id)
    return ConversationOutput(id=conversation.id, booking_id=booking.id, teacher_name=booking.teacher_name, learner_name=learner.name, status=booking.status)


@app.get("/api/bookings/{booking_id}/conversation", response_model=ConversationOutput)
def booking_conversation(booking_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking or not can_access_booking(booking, user):
        raise HTTPException(status_code=404, detail="Booking not found")
    conversation = db.scalar(select(Conversation).where(Conversation.booking_id == booking.id))
    if not conversation:
        raise HTTPException(status_code=409, detail="Your teacher has not accepted this chat request yet")
    learner = db.get(User, booking.learner_id)
    return ConversationOutput(id=conversation.id, booking_id=booking.id, teacher_name=booking.teacher_name, learner_name=learner.name, status=booking.status)


@app.get("/api/conversations/{conversation_id}/messages", response_model=list[MessageOutput])
def list_messages(conversation_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    booking = db.get(Booking, conversation.booking_id) if conversation else None
    if not conversation or not booking or not can_access_booking(booking, user):
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at)).all()
    return [MessageOutput(id=message.id, body=message.body, sender_id=message.sender_id, sender_name=db.get(User, message.sender_id).name, created_at=message.created_at) for message in messages]


@app.post("/api/conversations/{conversation_id}/messages", response_model=MessageOutput, status_code=status.HTTP_201_CREATED)
def send_message(conversation_id: int, payload: MessageInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    booking = db.get(Booking, conversation.booking_id) if conversation else None
    if not conversation or not booking or not can_access_booking(booking, user):
        raise HTTPException(status_code=404, detail="Conversation not found")
    message = Message(conversation_id=conversation.id, sender_id=user.id, body=payload.body.strip())
    db.add(message)
    db.commit()
    db.refresh(message)
    return MessageOutput(id=message.id, body=message.body, sender_id=user.id, sender_name=user.name, created_at=message.created_at)


# ────────────────────────────────────────────────────────────────────────────
# ChatPay "Chat na Ulipwe" — Live Partners, Wallet, Withdrawals & Chat Engine
# ────────────────────────────────────────────────────────────────────────────

LIVE_PARTNERS = [
    {
        "id": "emma",
        "name": "Emma Johansson",
        "country": "Sweden",
        "flag": "🇸🇪",
        "topic": "Safari na kutalii",
        "minutes": 10,
        "amount_tsh": 20000,
        "rate_per_min": 2000,
        "avatar": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=400&q=80",
        "status": "online",
        "bio": "Mpenzi wa utalii na safari za asili. Anapenda kujua kuhusu Serengeti na Zanzibar.",
    },
    {
        "id": "james",
        "name": "James Carter",
        "country": "USA",
        "flag": "🇺🇸",
        "topic": "Muziki na tamaduni",
        "minutes": 15,
        "amount_tsh": 25000,
        "rate_per_min": 1666,
        "avatar": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=400&q=80",
        "status": "online",
        "bio": "Mtayarishaji wa muziki New York. Anapenda Bongo Flava na midundo ya Kiafrika.",
    },
    {
        "id": "sophia",
        "name": "Sophia Miller",
        "country": "UK",
        "flag": "🇬🇧",
        "topic": "Chakula na mapishi",
        "minutes": 19,
        "amount_tsh": 30000,
        "rate_per_min": 1578,
        "avatar": "https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=400&q=80",
        "status": "online",
        "bio": "Mwalimu wa mapishi London. Anapenda kujifunza jinsi ya kupika Pilau na Mishkaki.",
    },
    {
        "id": "liam",
        "name": "Liam O'Brien",
        "country": "Ireland",
        "flag": "🇮🇪",
        "topic": "Michezo ya ulaya",
        "minutes": 25,
        "amount_tsh": 35000,
        "rate_per_min": 1400,
        "avatar": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=400&q=80",
        "status": "online",
        "bio": "Mchambuzi wa soka la Premier League na ligi kuu za Ulaya.",
    },
    {
        "id": "olivia",
        "name": "Olivia Brown",
        "country": "Australia",
        "flag": "🇦🇺",
        "topic": "Sinema na vipindi vya TV",
        "minutes": 30,
        "amount_tsh": 40000,
        "rate_per_min": 1333,
        "avatar": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=400&q=80",
        "status": "online",
        "bio": "Mwandishi wa filamu Sydney. Anapenda kubadilishana mawazo kuhusu sinema na series.",
    },
    {
        "id": "noah",
        "name": "Noah Schmidt",
        "country": "Germany",
        "flag": "🇩🇪",
        "topic": "Biashara na uwekezaji",
        "minutes": 35,
        "amount_tsh": 45000,
        "rate_per_min": 1285,
        "avatar": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&fit=crop&w=400&q=80",
        "status": "online",
        "bio": "Mwekezaji kutoka Frankfurt. Anapenda mazungumzo kuhusu biashara na masoko mapya.",
    },
    {
        "id": "charlotte",
        "name": "Charlotte Dubois",
        "country": "France",
        "flag": "🇫🇷",
        "topic": "Teknolojia mpya",
        "minutes": 40,
        "amount_tsh": 50000,
        "rate_per_min": 1250,
        "avatar": "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=400&q=80",
        "status": "online",
        "bio": "Mhandisi wa programu Paris. Anajadili AI, simu janja na mustakabali wa teknolojia.",
    },
    {
        "id": "ethan",
        "name": "Ethan Walker",
        "country": "Canada",
        "flag": "🇨🇦",
        "topic": "Mitindo na mavazi",
        "minutes": 45,
        "amount_tsh": 20000,
        "rate_per_min": 444,
        "avatar": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?auto=format&fit=crop&w=400&q=80",
        "status": "online",
        "bio": "Mbunifu wa mavazi Toronto. Anavutiwa na vitenge na mitindo ya kisasa.",
    },
    {
        "id": "amelia",
        "name": "Amelia Clark",
        "country": "UK",
        "flag": "🇬🇧",
        "topic": "Elimu na kujifunza lugha",
        "minutes": 10,
        "amount_tsh": 25000,
        "rate_per_min": 2500,
        "avatar": "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=400&q=80",
        "status": "online",
        "bio": "Mwalimu wa Kiingereza. Anataka kuboresha Kiswahili chake na kubadilishana lugha.",
    },
    {
        "id": "lucas",
        "name": "Lucas Moreau",
        "country": "France",
        "flag": "🇫🇷",
        "topic": "Afya na mazoezi",
        "minutes": 15,
        "amount_tsh": 30000,
        "rate_per_min": 2000,
        "avatar": "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&w=400&q=80",
        "status": "online",
        "bio": "Kocha wa mazoezi ya viungo na maisha ya afya.",
    },
    {
        "id": "isabella",
        "name": "Isabella Rossi",
        "country": "Italy",
        "flag": "🇮🇹",
        "topic": "Mazingira na hali ya hewa",
        "minutes": 19,
        "amount_tsh": 35000,
        "rate_per_min": 1842,
        "avatar": "https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?auto=format&fit=crop&w=400&q=80",
        "status": "online",
        "bio": "Mtafiti wa viumbe hai Rome. Anapenda kujua kuhusu hifadhi za wanyama Tanzania.",
    },
    {
        "id": "mason",
        "name": "Mason Reed",
        "country": "USA",
        "flag": "🇺🇸",
        "topic": "Sanaa na ubunifu",
        "minutes": 25,
        "amount_tsh": 40000,
        "rate_per_min": 1600,
        "avatar": "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?auto=format&fit=crop&w=400&q=80",
        "status": "online",
        "bio": "Mchoraji na mbunifu wa sanaa za kidijitali Los Angeles.",
    },
]

RECENT_PAYOUTS = [
    {"name": "Mwajuma H.", "city": "Dar es Salaam", "amount_tsh": 180000, "provider": "M-Pesa", "time_ago": "sekunde 24 zilizopita"},
    {"name": "Baraka M.", "city": "Arusha", "amount_tsh": 45000, "provider": "Tigo Pesa", "time_ago": "dakika 1 iliyopita"},
    {"name": "Neema J.", "city": "Mwanza", "amount_tsh": 70000, "provider": "Airtel Money", "time_ago": "dakika 2 zilizopita"},
    {"name": "Salum K.", "city": "Dodoma", "amount_tsh": 120000, "provider": "M-Pesa", "time_ago": "dakika 4 zilizopita"},
    {"name": "Fatuma A.", "city": "Zanzibar", "amount_tsh": 55000, "provider": "Tigo Pesa", "time_ago": "dakika 5 zilizopita"},
    {"name": "Joseph N.", "city": "Morogoro", "amount_tsh": 90000, "provider": "HaloPesa", "time_ago": "dakika 7 zilizopita"},
    {"name": "Grace P.", "city": "Tanga", "amount_tsh": 40000, "provider": "M-Pesa", "time_ago": "dakika 9 zilizopita"},
    {"name": "Emmanuel S.", "city": "Mbeya", "amount_tsh": 85000, "provider": "Airtel Money", "time_ago": "dakika 12 zilizopita"},
]


class WithdrawalInput(BaseModel):
    amount_tsh: int = Field(ge=1000, le=5000000)
    provider: str = Field(min_length=2, max_length=32)
    phone_number: str = Field(min_length=9, max_length=20)


class ChatCreditInput(BaseModel):
    partner_name: str = Field(min_length=2, max_length=80)
    minutes_spent: int = Field(ge=1, le=180)
    amount_tsh: int = Field(ge=100, le=500000)


class BotReplyInput(BaseModel):
    partner_name: str
    user_message: str
    topic: Optional[str] = None
    chat_history: list[dict] = []
    prompt_id: Optional[int] = None


def get_eat_today_start_utc() -> datetime:
    """Returns datetime of 00:00:00 today in East Africa Time (UTC+3), converted to UTC for DB queries."""
    now_utc = datetime.now(timezone.utc)
    eat_now = now_utc + timedelta(hours=3)
    eat_start = eat_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return eat_start - timedelta(hours=3)


def has_user_chatted_with_partner_today(db: Session, user_id: int, partner_name: str) -> bool:
    """Checks whether the user has already completed a chat with this partner today."""
    today_start = get_eat_today_start_utc()
    existing = db.scalar(
        select(ChatEarning)
        .where(
            ChatEarning.user_id == user_id,
            ChatEarning.partner_name.ilike(partner_name.strip()),
            ChatEarning.created_at >= today_start,
        )
    )
    return existing is not None


def get_partners_chatted_today(db: Session, user_id: int) -> List[str]:
    """Returns list of partner names the user has chatted with today."""
    today_start = get_eat_today_start_utc()
    earnings = db.scalars(
        select(ChatEarning.partner_name)
        .where(
            ChatEarning.user_id == user_id,
            ChatEarning.created_at >= today_start,
        )
    ).all()
    return list(set(earnings))


@app.get("/api/live-partners")
def list_live_partners(user: Optional[User] = Depends(optional_current_user), db: Session = Depends(get_db)):
    """Return all live foreign partners available for chatting and earning, including lock status for today."""
    chatted = set()
    if user:
        chatted = {p.strip().lower() for p in get_partners_chatted_today(db, user.id)}

    partners_out = []
    for p in LIVE_PARTNERS:
        item = dict(p)
        is_locked = item["name"].strip().lower() in chatted
        item["chatted_today"] = is_locked
        item["available_again"] = "Kesho" if is_locked else "Sasa"
        partners_out.append(item)

    return {"total_online": 2459, "partners": partners_out}


@app.get("/api/chat/partner-status")
def get_chat_partner_status(
    partner_name: str,
    user: Optional[User] = Depends(optional_current_user),
    db: Session = Depends(get_db),
):
    """Checks whether the current user has already chatted with this partner today."""
    if not user:
        return {"can_chat": True, "chatted_today": False, "partner_name": partner_name, "message": "Tayari kuanza."}

    is_locked = has_user_chatted_with_partner_today(db, user.id, partner_name)
    return {
        "can_chat": not is_locked,
        "chatted_today": is_locked,
        "partner_name": partner_name,
        "next_available": "Kesho",
        "message": (
            f"Umeshakamilisha mazungumzo na {partner_name} leo na kupokea malipo yako ya siku. Mazungumzo mapya na {partner_name} yatafunguliwa kesho!"
            if is_locked
            else f"Mzungu {partner_name} yupo tayari kuanza mazungumzo."
        ),
    }


@app.get("/api/recent-payouts")
def list_recent_payouts():
    """Return live payout ticker items."""
    return {"payouts": RECENT_PAYOUTS}


@app.get("/api/me/wallet")
def get_user_wallet(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Return user's current wallet balance, total earned, total withdrawn, and transaction history."""
    withdrawals = db.scalars(select(Withdrawal).where(Withdrawal.user_id == user.id).order_by(Withdrawal.created_at.desc())).all()
    earnings = db.scalars(select(ChatEarning).where(ChatEarning.user_id == user.id).order_by(ChatEarning.created_at.desc())).all()
    total_earned = sum(e.amount_tsh for e in earnings)
    total_withdrawn = sum(w.amount_tsh for w in withdrawals if w.status != "failed")
    return {
        "balance_tsh": user.balance_tsh or 0,
        "total_earned": total_earned,
        "total_withdrawn": total_withdrawn,
        "phone_number": user.payout_phone_number or user.phone_number or "",
        "withdrawals": [
            {
                "id": w.id,
                "amount_tsh": w.amount_tsh,
                "provider": w.provider,
                "phone_number": w.phone_number,
                "beneficiary_name": w.beneficiary_name,
                "status": w.status,
                "reference": w.reference,
                "created_at": w.created_at.isoformat(),
            }
            for w in withdrawals
        ],
        "earnings": [
            {
                "id": e.id,
                "partner_name": e.partner_name,
                "amount_tsh": e.amount_tsh,
                "minutes_spent": e.minutes_spent,
                "created_at": e.created_at.isoformat(),
            }
            for e in earnings
        ],
    }


@app.post("/api/wallet/withdraw")
async def withdraw_funds(payload: WithdrawalInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Send a teacher's earnings to their mobile-money wallet via ClickPesa."""
    require_teacher(user)
    if not clickpesa_enabled():
        raise HTTPException(status_code=503, detail="ClickPesa is not configured for payouts")
    current_balance = user.balance_tsh or 0
    if payload.amount_tsh > current_balance:
        raise HTTPException(
            status_code=400,
            detail=f"Salio lako haitoshi. Una TSh {current_balance:,}, unajaribu kutoa TSh {payload.amount_tsh:,}.",
        )

    phone = PaymentInput(phone_number=payload.phone_number).get_phone_number()
    if not phone or len(phone) < 12:
        raise HTTPException(status_code=422, detail="Weka namba halali ya mobile money")
    ref = f"WD{secrets.token_hex(8).upper()}"[:20]
    beneficiary_name = await preview_clickpesa_mobile_payout(payload.amount_tsh, phone, ref)
    upstream_status = await create_clickpesa_mobile_payout(payload.amount_tsh, phone, ref)
    user.balance_tsh = current_balance - payload.amount_tsh
    user.phone_number = phone
    user.payout_phone_number = phone
    withdrawal = Withdrawal(
        user_id=user.id,
        amount_tsh=payload.amount_tsh,
        provider=payload.provider.lower(),
        phone_number=phone,
        beneficiary_name=beneficiary_name,
        status="completed" if upstream_status in {"SUCCESS", "SETTLED"} else "processing",
        reference=ref,
    )
    db.add(withdrawal)
    db.commit()
    db.refresh(withdrawal)
    db.refresh(user)
    return {
        "status": "success",
        "message": f"Payout ya TSh {payload.amount_tsh:,} imetumwa ClickPesa kwenda {phone}. Hali: {upstream_status}.",
        "reference": ref,
        "beneficiary_name": beneficiary_name,
        "new_balance_tsh": user.balance_tsh,
        "withdrawal_id": withdrawal.id,
    }


@app.post("/api/chat/credit")
def credit_chat_earnings(payload: ChatCreditInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Credit earned TSh to user's wallet after completing 11 messages with a partner. Enforces 1 session per partner per day."""
    clean_partner = payload.partner_name.strip()
    if has_user_chatted_with_partner_today(db, user.id, clean_partner):
        return {
            "status": "already_credited",
            "credited_amount": 0,
            "new_balance_tsh": user.balance_tsh or 0,
            "chatted_today": True,
            "message": f"Umeshapokea malipo ya mazungumzo na {clean_partner} kwa leo. Mazungumzo mapya na {clean_partner} yatafunguliwa tena kesho!",
        }

    user.balance_tsh = (user.balance_tsh or 0) + payload.amount_tsh
    earning = ChatEarning(
        user_id=user.id,
        partner_name=clean_partner,
        amount_tsh=payload.amount_tsh,
        minutes_spent=payload.minutes_spent,
    )
    db.add(earning)
    db.commit()
    db.refresh(user)
    db.refresh(earning)
    return {
        "status": "success",
        "credited_amount": payload.amount_tsh,
        "new_balance_tsh": user.balance_tsh,
        "chatted_today": True,
        "message": f"Hongera! Umepokea TSh {payload.amount_tsh:,} kwa kukamilisha mazungumzo 11 na {clean_partner}.",
    }


@app.get("/api/chat/session-prompt")
def get_chat_session_prompt(
    partner_name: str = "Emma Johansson",
    prompt_id: Optional[int] = None,
    user: Optional[User] = Depends(optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the next rotational prompt from the 1,000 Mzungu conversations.
    If the user has already completed chatting with this partner today, returns locked status.
    """
    if user and has_user_chatted_with_partner_today(db, user.id, partner_name):
        return {
            "status": "locked",
            "can_chat": False,
            "chatted_today": True,
            "partner_name": partner_name,
            "message": f"Umeshazungumza na {partner_name} leo. Unaweza kuzungumza naye tena kesho!",
        }

    user_id = user.id if user else None
    if prompt_id is not None:
        prompt = mzungu_engine.get_prompt_by_id(prompt_id) or mzungu_engine.get_next_rotational_prompt(user_id)
    else:
        prompt = mzungu_engine.get_next_rotational_prompt(user_id)

    intro_message = mzungu_engine.generate_intro_message(partner_name, prompt)
    return {
        "status": "success",
        "can_chat": True,
        "chatted_today": False,
        "prompt_id": prompt["id"],
        "category": prompt["category"],
        "mzungu_message": prompt["mzungu_message"],
        "partner_name": partner_name,
        "intro_message": intro_message,
    }


@app.post("/api/chat/bot-reply")
async def generate_bot_reply(payload: BotReplyInput):
    """
    Generate realistic, warm, context-aware responses from live foreign chat partners.
    Analyzes what the teacher said and acknowledges the correct answer, with optional Gemini LLM fallback.
    """
    name = payload.partner_name
    prompt = None
    if payload.prompt_id:
        prompt = mzungu_engine.get_prompt_by_id(payload.prompt_id)

    # Optional Gemini LLM integration if GEMINI_API_KEY is configured in .env
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key:
        try:
            target_question = prompt.get("mzungu_message", "") if prompt else (payload.topic or "kujifunza Kiswahili")
            system_prompt = (
                f"Wewe ni {name}, mgeni/mtalii kutoka Sweden/Ulaya unayejifunza Kiswahili nchini Tanzania. "
                f"Uko kwenye mazungumzo na mwalimu wako wa Kitanzania kwenye ChatPay. "
                f"Hapo awali uliuliza: '{target_question}'. "
                f"Mwalimu amekujibu hivi sasa: '{payload.user_message}'. "
                f"Jibu kwa sentensi 1-3 za Kiswahili chenye heshima, bashasha na shauku ya mwanafunzi. "
                f"Tambua maelezo/usahihisho wa mwalimu, shukuru, rudia neno au sentensi sahihi aliyokufundisha, "
                f"na onyesha furaha ya kuelewa vizuri."
            )
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.post(
                    gemini_url,
                    json={
                        "contents": [{"parts": [{"text": system_prompt}]}]
                    },
                )
                if res.status_code == 200:
                    cand = res.json().get("candidates", [])
                    if cand:
                        text = cand[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text:
                            return {"reply": text.strip(), "prompt_id": payload.prompt_id}
        except Exception as e:
            print(f"[Gemini Fallback to Built-in Engine]: {e}")

    # Built-in intelligent conversational response engine
    reply = mzungu_engine.generate_intelligent_reply(
        partner_name=name,
        teacher_message=payload.user_message,
        current_prompt=prompt,
        conversation_history=payload.chat_history,
    )
    is_final = len(payload.chat_history) >= 9 or sum(1 for m in payload.chat_history if m.get("role") == "teacher") >= 5
    return {"reply": reply, "prompt_id": payload.prompt_id, "is_final": is_final}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/")
def homepage():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/{asset_name}")
def static_asset(asset_name: str):
    allowed = {"index.html", "styles.css", "script.js", "auth.html", "auth.js", "checkout.html", "checkout.js", "teacher.html", "teacher.js", "teacher-enrollment.html", "teacher-enrollment.js", "teacher-profile.html", "teacher-profile.js", "chat.html", "chat.js"}
    if asset_name not in allowed:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(BASE_DIR / asset_name)
