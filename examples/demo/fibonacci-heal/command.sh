#!/usr/bin/env bash
# Exact command used to regenerate this demo (invoked via scripts/regenerate_demo.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
exec bash scripts/regenerate_demo.sh
