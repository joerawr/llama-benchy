"""Load benchmark prompts and graders for source-aware semantic judging."""

from __future__ import annotations

import sys
import hashlib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from codex_gap_campaign import build_tasks  # noqa: E402
from ifeval_lite import TASKS as IFEVAL_TASKS, tasks_for_suite  # noqa: E402


def load_task_contexts() -> dict[str, Any]:
    contexts = {task.task_id: task for task in build_tasks().values()}
    contexts.update({task.task_id: task for task in IFEVAL_TASKS})
    contexts["compression"] = contexts["long_file_compression"]
    return contexts


def resolve_task_context(task_id: str, record: dict[str, Any]) -> Any:
    """Select historical task evidence by its saved hash when available."""
    original = load_task_contexts()[task_id]
    prompt_hash = record.get("semantic_judge", {}).get("task_prompt_sha256")
    if not prompt_hash:
        return original
    candidates = [original] + [task for task in tasks_for_suite("1.2") if task.task_id == task_id]
    for task in candidates:
        if hashlib.sha256(task.prompt.encode()).hexdigest() == prompt_hash:
            return task
    raise ValueError(f"No versioned task context matches saved prompt for {task_id}")
