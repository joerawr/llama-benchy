#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
env_file="${TELEGRAM_ENV_FILE:-$ROOT/benchy-state/telegram.env}"
if [[ "${TELEGRAM_DISABLE_ENV:-0}" != "1" && -f "$env_file" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
fi

message="${1:-}"
if [[ -z "$message" && ! -t 0 ]]; then
  message="$(cat)"
fi

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
  printf '%s\n' "telegram not configured; report follows:"
  printf '%s\n' "$message"
  exit 0
fi

python3 - "$message" <<'PY'
import json
import os
import sys
import urllib.parse
import urllib.request

message = sys.argv[1]
token = os.environ["TELEGRAM_BOT_TOKEN"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]
thread_id = os.environ.get("TELEGRAM_MESSAGE_THREAD_ID", "").strip()
url = f"https://api.telegram.org/bot{token}/sendMessage"


def chunks(text: str, limit: int = 3500) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
            current = ""
        while len(paragraph) > limit:
            parts.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        current = paragraph
    if current:
        parts.append(current)
    return parts


for index, chunk in enumerate(chunks(message), start=1):
    payload_fields = {"chat_id": chat_id, "text": chunk}
    if thread_id:
        payload_fields["message_thread_id"] = thread_id
    payload = urllib.parse.urlencode(payload_fields).encode()
    with urllib.request.urlopen(url, data=payload, timeout=30) as response:
        body = response.read().decode("utf-8")
        data = json.loads(body)
        if not data.get("ok"):
            raise SystemExit(f"telegram chunk {index} failed: {body}")
PY
