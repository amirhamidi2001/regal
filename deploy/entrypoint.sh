#!/bin/sh
set -eu

if [ "${RUN_COLLECTSTATIC:-0}" = "1" ]; then
    python manage.py collectstatic --noinput
fi

exec "$@"
