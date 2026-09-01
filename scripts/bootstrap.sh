#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$HOME/miniconda3/etc/profile.d/conda.sh"

conda env create -f "$ROOT/environment.yml" || conda env update -f "$ROOT/environment.yml"
echo "activate with: conda activate coding-agent"

