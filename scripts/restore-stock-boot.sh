#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
[[ $# -eq 0 ]]
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/boot-bundle.sh" restore
