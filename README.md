# CashMyMobile — Python / FastAPI Backend

A full Python rewrite of the Node.js backend using **FastAPI** + **Beanie ODM** + **MongoDB**.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI 0.115 |
| Database | MongoDB (via Beanie ODM + Motor) |
| Auth | JWT (python-jose) + OTP email |
| File Storage | AWS S3 (boto3) |
| Email | SMTP (smtplib) |
| Server | Uvicorn |

---

## Project Structure

```
python_backend/
├── main.py                   # FastAPI app entry point
├── requirements.txt
├── .env.example
└── app/
    ├── config/
    │   ├── settings.py       # Pydantic settings (reads .env)
    │   ├── database.py       # MongoDB / Beanie init
    │   └── constants.py      # Enums, status codes, error messages
    ├── models/               # Beanie Document models (MongoDB collections)
    │   ├── admin.py
    │   ├── order.py
    │   ├── device.py
    │   ├── pricing.py
    │   ├── counter_offer.py
    │   ├── contact_submission.py
    │   ├── partner.py
    │   ├── otp.py
    │   ├── api_log.py
    │   ├── ip_whitelist.py
    │   ├── network.py
    │   ├── storage_option.py
    │   └── device_condition.py
    ├── schemas/              # Pydantic request/response schemas
    │   ├── auth.py
    │   ├── order.py
    │   ├── device.py
    │   ├── pricing.py
    │   ├── contact.py
    │   ├── counter_offer.py
    │   ├── partner.py
    │   └── utility.py
    ├── routers/              # FastAPI route handlers (= Node controllers + routes)
    │   ├── __init__.py       # Aggregates all routers
    │   ├── auth.py           # POST /api/auth/request-otp, /verify-otp, GET /me
    │   ├── orders.py         # GET/POST/PUT/PATCH/DELETE /api/orders
    │   ├── devices.py        # GET/POST/PUT/PATCH/DELETE /api/devices
    │   ├── pricing.py        # GET/POST/PUT/DELETE /api/pricing
    │   ├── utilities.py      # Networks, storage options, device conditions
    │   ├── api_gateway.py    # Partner API: POST/GET /api/gateway/orders
    │   ├── api_logs.py       # GET/DELETE /api/api-logs
    │   ├── dashboard.py      # GET /api/dashboard
    │   ├── contact.py        # POST/GET /api/contact
    │   ├── upload.py         # POST /api/upload/image
    │   ├── export.py         # GET /api/export/orders|devices (CSV)
    │   ├── counter_offers.py # Full counter offer flow
    │   ├── partners.py       # Partner CRUD + API key management
    │   └── ip_whitelist.py   # IP whitelist CRUD
    ├── middleware/
    │   ├── auth.py           # JWT Bearer dependency
    │   ├── partner_auth.py   # X-Partner-Key header dependency
    │   ├── request_logger.py # ASGI middleware — logs every request
    │   ├── rate_limiter.py   # ASGI middleware — in-memory rate limiting
    │   └── ip_whitelist.py   # FastAPI dependency — IP whitelist check
    ├── services/
    │   ├── email_service.py  # All transactional emails (SMTP)
    │   ├── otp_service.py    # OTP generation & verification
    │   ├── s3_service.py     # AWS S3 upload / delete
    │   ├── order_service.py  # Order stats & pricing lookup
    │   ├── pricing_service.py# Upsert & max-price helpers
    │   ├── analytics_service.py # Dashboard stats aggregation
    │   ├── export_service.py # CSV export for orders & devices
    │   └── import_service.py # CSV import for devices & pricing
    └── utils/
        ├── logger.py         # Python logging setup
        ├── response.py       # Consistent JSON response helpers
        ├── helpers.py        # Validation & string utilities
        └── order_number.py   # Unique CMM-XXXXXX order number generator
```

---

## API Endpoints

All routes are prefixed with `/api`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/request-otp` | Public | Request admin login OTP |
| POST | `/auth/verify-otp` | Public | Verify OTP, receive JWT |
| GET | `/auth/me` | Admin | Get current admin |
| GET | `/devices` | Public | List devices |
| GET | `/devices/:id` | Public | Device + pricing |
| POST | `/devices` | Admin | Create device |
| PUT | `/devices/:id` | Admin | Update device |
| PATCH | `/devices/:id/toggle` | Admin | Toggle active status |
| DELETE | `/devices/:id` | Admin | Delete device |
| POST | `/devices/import` | Admin | CSV import |
| GET | `/pricing` | Public | All pricing |
| GET | `/pricing/device/:id` | Public | Pricing for device |
| POST | `/pricing` | Admin | Create pricing entry |
| POST | `/pricing/bulk-upsert` | Admin | Bulk upsert |
| GET | `/orders` | Admin | All orders (paginated) |
| POST | `/orders` | Public | Create order |
| PUT | `/orders/:id` | Admin | Update order |
| PATCH | `/orders/:id/status` | Admin | Update status |
| DELETE | `/orders/:id` | Admin | Delete order |
| POST | `/orders/bulk-update` | Admin | Bulk update |
| GET/POST | `/contact` | Public/Admin | Contact form |
| GET | `/dashboard` | Admin | Dashboard stats |
| GET | `/export/orders` | Admin | CSV export |
| GET | `/export/devices` | Admin | CSV export |
| POST | `/upload/image` | Admin | Upload to S3 |
| POST | `/counter-offers` | Admin | Create counter offer |
| POST | `/counter-offers/token/:token/accept` | Public | Accept offer |
| POST | `/counter-offers/token/:token/reject` | Public | Reject offer |
| GET/POST | `/partners` | Admin | Partner management |
| GET/POST | `/ip-whitelist` | Admin | IP whitelist |
| GET | `/api-logs` | Admin | Request logs |
| GET | `/utilities/networks` | Public | Networks |
| GET | `/utilities/storage-options` | Public | Storage options |
| GET | `/utilities/device-conditions` | Public | Device conditions |
| POST | `/gateway/orders` | Partner Key | Create order via API |
| GET | `/gateway/orders` | Partner Key | Get own orders |

---

## Setup

### 1. Clone & create virtual environment

```bash
cd python_backend
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your MongoDB URI, JWT secret, SMTP credentials, AWS keys
```

### 4. Run development server

```bash
python main.py
# or
uvicorn main:app --reload --port 8000
```

### 5. API Docs (auto-generated)

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Create First Admin

Connect to MongoDB and insert an admin directly (OTP login doesn't require a password):

```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"])
# Insert into 'admins' collection:
{
  "email": "admin@cashmymobile.co.uk",
  "password_hash": pwd_context.hash("unused"),
  "name": "Admin",
  "role": "admin",
  "is_active": True
}
```

Or run the seed script (coming soon).

---

## Production Deployment

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

Set `ENVIRONMENT=production` in `.env` to disable `/docs` and `/redoc`.
