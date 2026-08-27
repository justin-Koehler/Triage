#!/bin/sh
# Schema zuerst, dann App. Ein Prozess pro Container (uvicorn).
set -eu

echo "alembic upgrade head…"
alembic upgrade head

echo "starting $*"
exec "$@"
