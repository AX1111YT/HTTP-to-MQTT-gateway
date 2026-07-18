#!/bin/bash
set -e

python scripts/bootstrap_admin.py

exec "$@"
