#!/usr/bin/env bash
set -euo pipefail

remote="${NUC8_SSH:-rawrclaw@nuc8}"
raw_dir="${NUC8_RAW_SEED_DIR:-/private/tmp/llama-benchy-haystack-raw/nuc8}"
seed_dir="${NUC8_SEED_DIR:-/private/tmp/llama-benchy-haystack-seeds/nuc8}"

mkdir -p "$raw_dir" "$seed_dir"

rsync -az --delete "$remote:/home/rawrclaw/.hermes/memories/wonder/questions/" "$raw_dir/questions/"
rsync -az --delete "$remote:/home/rawrclaw/.hermes/kanban/boards/turo-lax-research/logs/" "$raw_dir/turo-lax-logs/"
rsync -az --delete "$remote:/home/rawrclaw/.hermes/logs/" "$raw_dir/hermes-logs/"

cd "$(dirname "$0")/.."
python3 scripts/prepare_seed_corpus.py --source "$raw_dir" --out "$seed_dir" --clean
printf '%s\n' "$seed_dir"
