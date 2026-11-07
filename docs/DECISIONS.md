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
