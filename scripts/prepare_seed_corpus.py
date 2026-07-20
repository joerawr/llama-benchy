#!/usr/bin/env python3
import argparse
import re
import shutil
from pathlib import Path


SECRET_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*[^\s\"']+"), r"\1=<REDACTED>"),
    (re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{20,}"), "Bearer <REDACTED>"),
    (re.compile(r"(?i)(sk-[a-z0-9_-]{20,})"), "<REDACTED_OPENAI_KEY>"),
    (re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"), "<REDACTED_LONG_TOKEN>"),
    (re.compile(r"\b[0-9a-fA-F]{40,}\b"), "<REDACTED_HEX_TOKEN>"),
    (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END [A-Z ]+PRIVATE KEY-----", re.DOTALL), "<REDACTED_PRIVATE_KEY>"),
]


def redact(text: str) -> str:
    redacted = text
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def safe_relative(path: Path, root: Path) -> Path:
    rel = path.relative_to(root)
    return Path(*[part.replace("/", "_").replace("\0", "") for part in rel.parts])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-file-bytes", type=int, default=1_000_000)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    out = args.out.expanduser().resolve()
    if not source.exists() or not source.is_dir():
        raise SystemExit(f"source directory does not exist: {source}")
    if args.clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        try:
            raw = path.read_bytes()[: args.max_file_bytes]
        except OSError:
            skipped += 1
            continue
        text = raw.decode("utf-8", errors="ignore")
        if not text.strip():
            skipped += 1
            continue
        redacted = redact(text)
        target = out / safe_relative(path, source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(redacted, encoding="utf-8")
        written += 1

    print(f"prepared seed corpus source={source} out={out} written={written} skipped={skipped}")


if __name__ == "__main__":
    main()
