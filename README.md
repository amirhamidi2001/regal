# REGAL

REGAL is a Persian, RTL e-commerce platform for customers in Iran. It is built as a Django modular monolith and uses Toman as its integer currency unit.

## Stack

- Python 3.12 and Django 5.2 LTS
- PostgreSQL 16
- Gunicorn and Nginx (`stable-alpine`)
- Docker Compose with three services: `web`, `db`, and `nginx`
- S3-compatible object storage for production media; local filesystem storage in development

## Prerequisites

Install Docker Engine or Docker Desktop with Docker Compose v2. From the repository root, prepare the environment file:

```sh
cp .env.example .env
```

Generate a Django secret key and a strong PostgreSQL password. Put the generated values in `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` in `.env`. A secret key can be generated with:

```sh
python -c 'import secrets; print(secrets.token_urlsafe(64))'
```

Set the S3-compatible endpoint, credentials, bucket, and public media URL in `.env` before using production settings for real media uploads. The values in `.env.example` are placeholders.

## Quick start

```sh
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Open <http://localhost/> for the storefront placeholder and <http://localhost/healthz/> for the liveness endpoint. The admin path is configured by `DJANGO_ADMIN_URL` (default `internal-admin/`).

Migrations are never run automatically by the containers. Run `migrate` explicitly after starting the services and whenever a new migration is introduced.

## Tests

Run the full suite against the Compose PostgreSQL database:

```sh
docker compose exec web python manage.py test
```

See [Developer setup](docs/DEV_SETUP.md) for local test instructions and environment variables.

## Phase 4: catalog, pricing, and inventory

The catalog stores integer-Toman prices, quantity-based `Decimal` markup tiers, and append-only stock history. Catalog pricing and stock changes must use the service APIs in `apps/catalog/pricing.py` and `apps/catalog/inventory.py`. See [Pricing and inventory](docs/PRICING_AND_INVENTORY.md) for rounding, tier rules, inventory behavior, image limits, and the public service API.

## Development server

The development override is loaded only when named explicitly with `-f`:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The development server is reachable at <http://127.0.0.1:8000>. The override selects `config.settings.dev`, mounts the working tree into `web`, and publishes PostgreSQL only on loopback.

## Project layout

- `apps/`: the seven Django apps: `core`, `accounts`, `catalog`, `cart`, `orders`, `payments`, and `dashboard`
- `config/`: environment helpers, split settings, URL configuration, and WSGI entry point
- `deploy/`: container entrypoint and Nginx configuration
- `static/`: copied template assets served by Nginx
- `templates/`: Django templates
- `docs/`: setup notes and the Phase 3 decision log

## Architectural rules

- Business logic belongs in plain-Python service modules; views stay thin.
- Money is integer Toman. Shipping is excluded from order totals and gateway amounts; there is no VAT.
- Stock changes go through `catalog/inventory.py`; order status changes go through `transition()`; cancellation goes through `finalize_cancellation()`.
- Refunds are processed manually in the Zibal dashboard and only recorded in REGAL.
- Configuration and secrets come from the environment. Never commit `.env` or real credentials.
- PostgreSQL is the only application database; the production Compose stack has exactly three services.
