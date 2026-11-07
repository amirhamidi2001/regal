# Developer setup

## Environment variables read by Django settings

`config/settings/base.py`, `dev.py`, and `prod.py` read the variables below. “Required in prod” describes production settings; database and S3 variables must be present even for a production settings import used by management commands.

| Name | Required in prod | Default | Purpose |
| --- | --- | --- | --- |
| `POSTGRES_DB` | Yes | None | PostgreSQL database name |
| `POSTGRES_USER` | Yes | None | PostgreSQL username |
| `POSTGRES_PASSWORD` | Yes | None | PostgreSQL password |
| `POSTGRES_HOST` | Yes | None | PostgreSQL hostname |
| `POSTGRES_PORT` | No | `5432` | PostgreSQL port |
| `DB_CONN_MAX_AGE` | No | `60` | Persistent database connection age in seconds |
| `DJANGO_ADMIN_URL` | No | `internal-admin/` | Admin URL prefix; no leading slash and must end in `/` |
| `STATIC_ROOT` | No | `BASE_DIR / staticfiles` | Collected static destination |
| `MEDIA_URL` | No | `/media/` | Development media URL |
| `MEDIA_ROOT` | No | `BASE_DIR / media` | Development media directory |
| `DJANGO_LOG_LEVEL` | No | `INFO` | Root and Django logger level |
| `DJANGO_DEBUG` | No | `True` in dev; production is always false | Development debug mode |
| `DJANGO_SECRET_KEY` | Yes | Dev-only insecure value in dev; none in prod | Django signing and cryptographic key |
| `DJANGO_ALLOWED_HOSTS` | Yes | `localhost,127.0.0.1,[::1]` in dev; none in prod | Allowed HTTP Host values |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | No | Empty list | Trusted CSRF origins, including scheme |
| `DJANGO_SECURE_SSL` | No | `True` in prod | Enables production HTTPS redirect and secure cookies |
| `S3_ENDPOINT_URL` | Yes | None | S3-compatible API endpoint |
| `S3_ACCESS_KEY_ID` | Yes | None | S3 access key identifier |
| `S3_SECRET_ACCESS_KEY` | Yes | None | S3 secret key |
| `S3_BUCKET_NAME` | Yes | None | Bucket used for uploaded media |
| `S3_PUBLIC_BASE_URL` | Yes | None | Public base URL used to construct media URLs |
| `S3_REGION_NAME` | No | Unset | Optional S3 region; omitted from storage options when blank |
| `S3_ADDRESSING_STYLE` | No | `auto` | S3 bucket addressing mode |

Compose also uses `GUNICORN_WORKERS` (default `3`) and `RUN_COLLECTSTATIC` (default behavior is disabled by the entrypoint unless set to `1`); these are container configuration, not variables read by `config/settings/`.

## Running tests locally

The test suite uses PostgreSQL. Start the development database and expose it on loopback:

```sh
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db
```

Create a virtual environment, install the pinned requirements, and point Django at that database. Replace the local placeholder PostgreSQL password with the same value used in `.env` if you changed it.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export POSTGRES_DB=regal POSTGRES_USER=regal POSTGRES_PASSWORD=change-me POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432
python manage.py test
```

The production settings require the S3 variables too. For local runs use the development settings (`DJANGO_SETTINGS_MODULE=config.settings.dev`) or provide non-credential placeholder S3 values when testing production settings. Tests do not contact an S3 service.

## Running tests in Docker

With the normal stack running, execute:

```sh
docker compose exec web python manage.py test
```

For the development server and bind-mounted source tree:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

## Resetting the development database

To stop containers while preserving named volumes, use `docker compose down`. To erase and recreate the development database volume, use:

```sh
docker compose down -v
```

**This is destructive:** `-v` deletes the named PostgreSQL data volume (`pg_data`) and the shared static volume (`static_data`). Database contents, including users and migrations, are permanently removed. Use it only when you intend to discard that data.

## Troubleshooting

### Named-volume permission errors

The web process runs as UID 1000 (`app`). Check the service logs and identity first:

```sh
docker compose logs web
docker compose exec web id
```

If an existing `static_data` volume is owned by a different UID and prevents collection or reads, repair only that volume’s application directory, then restart `web`:

```sh
docker compose run --rm --user root --entrypoint /bin/sh web -c 'chown -R app:app /app/staticfiles'
docker compose up -d web
```

Do not remove `pg_data` to resolve a static-volume ownership problem. If PostgreSQL itself reports a volume permission error, inspect the database container logs and the Docker volume owner; do not recursively change ownership without confirming the database image’s expected UID.

### `ALLOWED_HOSTS` and CSRF errors

Set `DJANGO_ALLOWED_HOSTS` to a comma-separated list of hostnames actually used in the request (without a scheme), such as `localhost,shop.example.com`. For CSRF failures from an HTTPS site, add the complete origin, including scheme, to `DJANGO_CSRF_TRUSTED_ORIGINS`, such as `https://shop.example.com`. Restart the web service after changing `.env`. The development override selects `config.settings.dev`; production uses `config.settings.prod` and requires a non-empty allowed-host list.
