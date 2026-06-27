# SuperPOS Backend

Django REST API for the SuperPOS point-of-sale system.

## Stack

| Layer | Technology |
|---|---|
| Framework | Django 4.2 + Django REST Framework 3.15 |
| Database | PostgreSQL 14+ |
| Auth | JWT via `djangorestframework-simplejwt` |
| CORS | `django-cors-headers` |
| Filtering | `django-filter` |

## Project structure

```
superpos_backend/
├── manage.py
├── requirements.txt
├── superpos_backend/
│   ├── settings.py        # all config lives here
│   ├── urls.py            # root URL router
│   ├── wsgi.py
│   └── asgi.py
├── accounts/              # custom User model + JWT auth
│   ├── models.py          # User (AbstractUser + role/branch/pin)
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   └── admin.py
└── pos/                   # POS domain
    ├── models.py          # Category, Product, PLUItem, Transaction, TransactionItem
    ├── serializers.py
    ├── views.py
    ├── filters.py         # ProductFilter, TransactionFilter
    ├── urls.py
    └── admin.py
```

## Quick start

### 1 — Prerequisites

- Python 3.11+
- PostgreSQL 14+ running locally

### 2 — Create the database

```sql
-- in psql:
CREATE DATABASE superpos;
```

### 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### 4 — Run migrations

```bash
python manage.py migrate
```

### 5 — Create a superuser

```bash
python manage.py createsuperuser
```

### 6 — Start the dev server

```bash
python manage.py runserver
```

API is available at **http://localhost:8000/api/**

Django admin: **http://localhost:8000/admin/**

---

## API reference

### Auth

| Method | URL | Auth | Description |
|--------|-----|------|-------------|
| POST | `/api/auth/login/` | public | Obtain access + refresh tokens |
| POST | `/api/auth/token/refresh/` | public | Refresh access token |
| GET | `/api/auth/me/` | Bearer | Current user profile |
| GET | `/api/auth/users/` | Bearer | List all users |
| POST | `/api/auth/users/` | Admin | Create user |
| GET/PUT/DELETE | `/api/auth/users/<id>/` | Bearer/Admin | User detail |

**Login request:**
```json
POST /api/auth/login/
{ "username": "ahmed", "password": "yourpassword" }
```

**Login response:**
```json
{
  "access":  "<jwt>",
  "refresh": "<jwt>",
  "user": {
    "id": 1, "username": "ahmed", "role": "Cashier",
    "branch": "Cairo Downtown #03", "terminal": "POS-01"
  }
}
```

All subsequent requests: `Authorization: Bearer <access token>`

---

### Products

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/products/` | List (filterable, searchable, paginated) |
| POST | `/api/products/` | Create product |
| GET/PUT/PATCH/DELETE | `/api/products/<id>/` | Product detail |
| GET | `/api/products/barcode/<barcode>/` | Lookup by barcode (used by POS scanner) |
| PATCH | `/api/products/<id>/stock/` | Update stock level |

**Query params for GET /api/products/:**
- `search=` — searches name, SKU, barcode
- `category=Beverages` — exact category name
- `low_stock=true` — stock > 0 and stock < reorder point
- `out_of_stock=true` — stock = 0
- `min_price=` / `max_price=`
- `ordering=price` / `ordering=-stock`
- `page=2`

---

### PLU (scale items)

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/plu/` | List PLU items |
| POST | `/api/plu/` | Create PLU item |
| GET/PUT/PATCH/DELETE | `/api/plu/<id>/` | PLU detail |
| GET | `/api/plu/code/<plu>/` | Lookup by PLU code |

---

### Transactions

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/transactions/` | List (filterable, paginated) |
| POST | `/api/transactions/` | Create transaction (full cart) |
| GET | `/api/transactions/<id>/` | Transaction detail with items |
| PATCH | `/api/transactions/<id>/void/` | Void a completed transaction |

**Query params for GET /api/transactions/:**
- `method=cash` / `card` / `wallet`
- `status=completed` / `voided` / `refunded`
- `date_from=2026-05-01T00:00:00` (ISO 8601)
- `date_to=2026-05-11T23:59:59`
- `cashier=<user_id>`
- `search=<id or branch>`

**Create transaction payload:**
```json
POST /api/transactions/
{
  "branch":     "Cairo Downtown #03",
  "terminal":   "POS-01",
  "subtotal":   36.77,
  "tax_amount": 3.68,
  "total":      40.45,
  "method":     "cash",
  "paid":       50.00,
  "change":     9.55,
  "offline":    false,
  "items": [
    {
      "product":      1,
      "product_name": "Coca-Cola 330ml",
      "barcode":      "5410188006353",
      "qty":          "2.000",
      "price_each":   "1.20",
      "line_total":   "2.40"
    }
  ]
}
```

---

### Dashboard

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/dashboard/summary/` | Today / week / month totals + low-stock count |

---

## Database settings

Configured in `settings.py`:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'superpos',
        'USER': 'postgres',
        'PASSWORD': 'K2362003k',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

## Token lifetimes

| Token | Lifetime |
|-------|----------|
| Access | 15 minutes |
| Refresh | 30 days (rotated on use) |
