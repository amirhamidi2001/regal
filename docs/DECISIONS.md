# Phase 3 decisions log

All items are open and record assumptions or decisions requiring owner approval.

| ID | Label | Item | Status |
| --- | --- | --- | --- |
| A3-1 | ASSUMPTION | `accounts.User` was built in Phase 3. | open |
| A3-2 | ASSUMPTION | Versions and image tags: Python 3.12 (`python:3.12-slim`), Django 5.2.19, psycopg 3.3.8 with binary extra, PostgreSQL `postgres:16`, and Nginx `nginx:stable-alpine`. | open |
| A3-3 | ASSUMPTION | Django admin remains at the configurable `DJANGO_ADMIN_URL`. | open |
| A3-4 | ASSUMPTION | `ATOMIC_REQUESTS` is false; services open explicit transactions. | open |
| A3-5 | ASSUMPTION | The development Compose override is used only with an explicit `-f` flag. | open |
| A3-6 | ASSUMPTION | Container logs go to stdout with JSON-file rotation (10 MB, five files); revisit in Phase 10. | open |
| A3-7 | ASSUMPTION | `/healthz/` does not query the database. | open |
| A3-8 | ASSUMPTION | Mobile numbers use `09` followed by nine digits. | open |
| A3-9 | NEEDS APPROVAL | Whether to enforce stricter Iranian postal-code structural rules. | open |
| A3-10 | NEEDS APPROVAL | Owner-approved source for the full Iranian city list; currently only provinces and their capitals exist. | open |
| A3-11 | ASSUMPTION | Template assets were copied verbatim; the home page remains a placeholder. | open |
| A3-12 | ASSUMPTION | Default static storage uses unhashed names and Nginx sets a seven-day cache. | open |
| A3-13 | ASSUMPTION | The database enforces the mobile format with a CHECK constraint. | open |
| A3-14 | NEEDS APPROVAL | Whether to add a linter or formatter such as Ruff as a development-only dependency. | open |
| A3-15 | ASSUMPTION | `DJANGO_SECURE_SSL` defaults to true in production settings; `.env.example` sets it false until Phase 10. | open |
| P3-16 | NEEDS APPROVAL | HSTS `includeSubDomains` and `preload`; security checks W005 and W021 remain silenced until Phase 10. | open |
| P3-17 | NEEDS APPROVAL | Protection for the guessable admin path, for example an Nginx allow-list, in Phase 10. | open |
| P3-18 | ASSUMPTION | `accounts.User.created_at` replaces `date_joined`. | open |
| P3-19 | ASSUMPTION | `SESSION_COOKIE_AGE` is 30 days for the guest cart. | open |
| P3-20 | ASSUMPTION | `django-storages` 1.14.6 uses `bucket_name`, `endpoint_url`, `access_key`, `secret_key`, optional `region_name`, `addressing_style`, `querystring_auth`, `default_acl`, `file_overwrite`, `custom_domain`, and `url_protocol`; addressing defaults to `auto`. These names were checked against the installed 1.14.6 source. | open |
| P3-21 | NEEDS APPROVAL | Production S3 storage has not been manually verified against a real bucket. | open |

## Phase 4 decisions log

| ID | Label | Item | Status |
| --- | --- | --- | --- |
| P4-1 | ASSUMPTION | Phase 3 is approved as built. | open |
| P4-2 | ASSUMPTION | Catalog constants live in `apps/catalog/constants.py`. | open |
| P4-3 | ASSUMPTION | `MAX_BASE_PRICE` is 100,000,000,000 Toman and `MAX_QUANTITY` is 1,000,000; larger values need owner approval. | open |
| P4-4 | ASSUMPTION | Catalog lifecycle services live in `apps/catalog/services.py`. | open |
| P4-5 | ASSUMPTION | `StockLog.order_id` stays a plain integer until Phase 6A. | open |
| P4-6 | ASSUMPTION | StockLog immutability is enforced in Python. | open |
| P4-7 | ASSUMPTION | SKUs are trimmed and upper-case on save. | open |
| P4-8 | ASSUMPTION | New variants are inactive and products default to draft. | open |
| P4-9 | ASSUMPTION | Category slugs are unique Unicode values; categories have no depth limit and moves are cycle-checked. | open |
| P4-10 | ASSUMPTION | A simple product is derived from its variants and attributes; no flag is stored. | open |
| P4-11 | ASSUMPTION | Markup is from 0 through 999.99 with at most two decimal places. | open |
| P4-12 | ASSUMPTION | Inventory functions do not check variant activity or product status. | open |
| P4-13 | ASSUMPTION | Image limits and derivatives are 5 MiB, 40,000,000 pixels, JPEG/PNG/WebP, 480/960-pixel WebP derivatives at quality 82. | open |
| P4-14 | ASSUMPTION | Pillow is pinned to version 13.0.0. | open |
| P4-15 | NEEDS APPROVAL | R4 (option A) approved; read-only catalog admin and DEBUG-only, idempotent seed command implemented by Prompts 8 and 9. | resolved |
| P4-16 | ASSUMPTION | `verify_stock_log` is a diagnostic valid only for stock initially at zero and exclusively changed through `inventory.py`. | open |
| P4-17 | ASSUMPTION | Architecture guard tests enforce catalog stock, tier, log, and numeric boundaries. | open |
| P4-18 | ASSUMPTION | `conflict_resolution` is a reserved StockLog reason, unused until Phase 6C. | open |
| P4-19 | ASSUMPTION | `get_purchase_problem` is implemented in `apps/catalog/services.py`. | open |
| P4-20 | ASSUMPTION | `adjust_manual` allows `actor=None` for the system; permission checks belong to the Phase 8 dashboard. | open |
| P4-21 | ASSUMPTION | Inactive categories hide their subtree in `build_category_tree`, and inactive ancestors make a product unpurchasable. | open |
