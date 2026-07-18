#!/bin/bash
set -e

chown -R appuser:appuser /app/db
runuser -u appuser -- python scripts/bootstrap_admin.py
exec runuser -u appuser -- "$@"
