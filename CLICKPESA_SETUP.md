# HarakaPay Collection and ClickPesa Payout Setup for Talkroom

Talkroom uses **HarakaPay's Collection API (USSD-PUSH)** to collect mobile-money payments directly on customer devices across Tanzania.

It continues to use ClickPesa's **Mobile Money Payout API** to withdraw a teacher's earnings. For that API, the teacher's verified mobile-money number is the payout **beneficiary**; it is not a separate merchant account or a beneficiary-registration record.

Instead of redirecting to an external hosted checkout link, the customer provides their mobile money phone number inside Talkroom, receives an interactive USSD prompt on their handset to enter their PIN, and Talkroom confirms the transaction in real time via live status polling and verified server-to-server webhooks.

---

## 1. Configure Credentials

Ensure your `.env` contains:

```env
TALKROOM_SECRET_KEY=dev-secret-key-3918204918230918230192830192
TALKROOM_DATABASE_URL=sqlite:///./talkroom.db

# HarakaPay Collection API credentials
HARAKAPAY_API_KEY=hpk_your_api_key_here
HARAKAPAY_WEBHOOK_URL=https://YOUR-PUBLIC-DOMAIN/api/payments/harakapay/webhook

# ClickPesa Payout API credentials
CLICKPESA_CLIENT_ID=your-client-id
CLICKPESA_API_KEY=your-api-key
CLICKPESA_CHECKSUM_KEY=your-checksum-key
CLICKPESA_WEBHOOK_URL=https://YOUR-PUBLIC-DOMAIN/api/payments/clickpesa/webhook
```

> **Security Note:** Never commit `.env` to source control.

---

## 2. HarakaPay Collection Configuration

1. Create or open your HarakaPay account and generate an API key.
2. Set `HARAKAPAY_API_KEY` only on the server; never place it in browser JavaScript.
3. Set the callback URL to `https://YOUR-PUBLIC-DOMAIN/api/payments/harakapay/webhook` in `HARAKAPAY_WEBHOOK_URL`. Talkroom verifies every callback with HarakaPay's status endpoint before marking a payment as paid.

## 3. ClickPesa Payout Configuration

1. Log in to the [ClickPesa Portal](https://portal.clickpesa.com/).
2. Under **Developers / Applications**, create or select your application.
3. Ensure **Disbursement / Mobile Money Payout** access is enabled. Payout access normally requires ClickPesa approval and sufficient wallet balance.
4. Set the Application Webhook URL to:
   ```
   https://YOUR-PUBLIC-DOMAIN/api/payments/clickpesa/webhook
   ```
   (In local development, use your public ngrok URL, e.g. `https://<subdomain>.ngrok-free.dev/api/payments/clickpesa/webhook`).
5. Subscribe to `PAYOUT INITIATED`, `PAYOUT REVERSED`, and `PAYOUT REFUNDED` events.

---

## 4. How the USSD-Push Payment Flow Works

```
[Learner]               [Talkroom Server]                [HarakaPay API]             [Customer Phone]
   |                           |                               |                           |
   |--- 1. Enter Phone ------->|                               |                           |
   |    (e.g. 255712345678)    |                               |                           |
   |                           |--- 2. POST /collect ---------->|                           |
   |                           |    (amount, phone, callback)  |                           |
   |                           |<-- 200 OK (PROCESSING) -------|--- 4. Push USSD Prompt -->|
   |<-- 5. Show Waiting Screen-|                               |                           |
   |                           |                               |                           |
   |=== 6. Poll /status ======>|--- 7. GET /status/{orderId} -->|    Customer enters PIN    |
   |    (every 5s)             |<-- Status (PROCESSING) -------|    on their phone         |
   |                           |                               |            |              |
   |                           |<-- 8. Webhook Notification ---|<-----------+              |
   |                           |    (completed / failed)       |                           |
   |<-- 9. Status = SUCCESS ---|                               |                           |
```

1. **Initiation**: The customer enters their mobile money number. The frontend calls `POST /api/bookings/{id}/payment` with `provider: "harakapay"` and `phone_number`.
2. **Push Request**: The backend calls HarakaPay's `POST /api/v1/collect` using its server-side API key.
3. **Interactive Prompt**: The customer receives a prompt on their handset asking to confirm the transfer to Talkroom with their PIN.
4. **Real-Time Polling**: The checkout page queries `GET /api/payments/{id}/status` every 5 seconds, which queries HarakaPay's `GET /api/v1/status/{order_id}`.
5. **Webhook Confirmation**: HarakaPay posts to `/api/payments/harakapay/webhook`; Talkroom uses the supplied order ID to query HarakaPay before marking a booking as paid.

---

## 5. Teacher Withdrawal / Beneficiary Flow

1. A teacher enters the number that should receive their earnings.
2. Talkroom calls `POST /payouts/preview-mobile-money-payout` to validate the number, amount, available balance, fees, and (when returned) the registered account name.
3. If validation succeeds, Talkroom calls `POST /payouts/create-mobile-money-payout` with the same amount, number, currency, and unique order reference.
4. Talkroom saves the beneficiary number and resolved name, then marks the withdrawal as completed or processing. Payout reversal/refund webhooks restore the teacher's wallet balance.

No additional beneficiary API key, merchant ID, or beneficiary-creation endpoint is required for a mobile-money withdrawal. The merchant is your ClickPesa application/account; the beneficiary is the teacher's `255...` mobile-money number.

---

## 6. Run Locally

Ensure uvicorn and your ngrok tunnel are running:

```powershell
# In terminal 1:
python -m uvicorn app:app --reload

# In terminal 2:
ngrok http 8000
```

---

## 7. Security & Idempotency Features

- **Amount & Currency Validation**: Strict enforcement of currency (`TZS`) and verification that the webhook's collected amount matches the booking's exact amount.
- **Reference Constraints**: `orderReference` is generated uniquely and constrained to <= 20 alphanumeric characters as required by ClickPesa.
- **HMAC-SHA256 Checksum**: When `CLICKPESA_CHECKSUM_KEY` is present, all outgoing payloads and incoming webhooks are cryptographically validated.
- **Tamper Protection**: Browser-side confirmation cannot mark a ClickPesa payment as paid; only verified webhooks or verified upstream queries can settle a payment.
