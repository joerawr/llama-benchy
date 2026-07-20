#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Hold the same fcntl advisory lock as campaign_worker before any stop-current call.
# The wrapper re-execs this script with the marker, so the lock spans the whole scout.
if [[ "${CAMPAIGN_LOCK_HELD:-}" != "1" ]]; then
  exec uv run python ops/with-campaign-lock.py --lock-file benchy-state/campaign.lock -- "$0" "$@"
fi

target="${NIGHTLY_TARGET:-mini}"
case "$target" in
  mini)
    target_label="16GB Mac mini"
    candidate_profile="Select only a dense model at or below 12B, or a low-active MoE, whose projected 64K Metal memory is under 10 GiB. Consider Q4 through Q8 only when the specific quant still meets that memory ceiling. Optimize for quality-per-GiB and useful throughput, not merely the smallest Q4 file."
    comparison_target="the 16GB mini leaders"
    leaderboard_file="benchy-state/leaderboard-16gb-mini.md"
    ;;
  main64)
    target_label="64GB Mac"
    candidate_profile="Select a credible model family or quant for the 64GB Mac that projects to fit at 64K with operating headroom. Explicitly investigate Q4, Q5, Q6, and Q8 GGUF quants when available and fitting; choose the one quant that answers the strongest quality-versus-memory question tonight. Dense models above 12B are allowed here when they fit. Do not default to Q4 merely because it is smaller."
    comparison_target="the 64GB main-machine leaders"
    leaderboard_file="benchy-state/leaderboard-64gb-m1-max.md"
    ;;
  *)
    echo "Invalid NIGHTLY_TARGET=$target (expected mini or main64)" >&2
    exit 2
    ;;
esac

stamp="$(date +%Y%m%d-%H%M%S)"
scratch="${NIGHTLY_MODEL_SCRATCH:-/Users/jrogers/models/_nightly-candidates}"
candidates="results/nightly-candidates-${target}-$stamp.json"
prompt_file="results/nightly-prompt-${target}-$stamp.md"
agent_report="results/nightly-agent-report-${target}-$stamp.md"
agent_final="results/nightly-agent-final-${target}-$stamp.md"

mkdir -p "$scratch" results

restart_current() {
  ./ops/serve-current.sh || ./ops/telegram-report.sh "Nightly scout finished, but failed to restart current llama-server. Check $ROOT/benchy-state/current-server.log"
}

./ops/stop-current.sh || true
trap restart_current EXIT

uv run python scripts/hf_model_scout.py --out "$candidates" --limit "${NIGHTLY_SCOUT_LIMIT:-40}" --file-limit "${NIGHTLY_FILE_LIMIT:-24}"

cat > "$prompt_file" <<EOF
Run the nightly Hugging Face model scout for llama-benchy, specifically optimized for the $target_label lane.

Use these files as authoritative context:
- benchy-state/selection-guidelines.md
- $leaderboard_file (authoritative leaderboard for this lane)
- benchy-state/current-rankings.md (cross-lane summary only)
- benchy-state/tested-models.json
- $candidates (candidate metadata gathered by first browsing Hugging Face Trending MLX, then Trending GGUF; it also includes fresh and popular GGUF candidates)

Rules:
- Select at most one model/quant to test tonight in the $target_label lane. Select none only when the best candidates have concrete blockers.
- Python/scripts may gather metadata, but you make the selection using the history and guidelines.
- $candidate_profile
- Download candidates only under $scratch.
- Clean up rejected downloads under $scratch.
- Do not delete keeper models outside $scratch.
- Do not modify benchy-state/serving-current.json.
- Minimum quantization is Q4. Do not download or test Q3 or lower, including IQ1/IQ2/IQ3, Q2, Q3, UD-Q2, or UD-Q3 files.
- Prefer testing one high-signal candidate in the $target_label lane over doing nothing when it has a concrete benchmark question.
- Do not reject a plausible candidate solely because candidate_files is missing. Check the repo files with the Hugging Face CLI first.
- Compare results primarily against $comparison_target; mention the other leaderboard only when materially relevant.
- Do not test a duplicate model/quant already recorded in tested-models.json unless the run is explicitly answering a new quant-quality question.
- Write a concise markdown report to $agent_report with:
  - Decision: TESTED or SKIPPED
  - Selected model/file and why, or the top rejected candidates with exact blockers
  - Tests run and result table if tested
  - Memory usage, speed, and ranking impact if tested
  - Cleanup performed and any manual follow-up
- Use ops/telegram-report.sh to send the final summary.

If no candidate is worth testing, write that decision and why to $agent_report, then send the summary.
EOF

if [[ "${NIGHTLY_DRY_RUN:-0}" == "1" ]]; then
  {
    echo "Nightly scout dry run complete."
    echo "Candidates: $candidates"
    echo "Prompt: $prompt_file"
    echo "No Codex agent run was started."
  } | tee "$agent_report" | ./ops/telegram-report.sh
  exit 0
fi

codex exec --sandbox danger-full-access -c approval_policy=\"never\" --cd "$ROOT" -o "$agent_final" - < "$prompt_file"
if [[ -s "$agent_report" ]]; then
  ./ops/telegram-report.sh "$(cat "$agent_report")"
else
  ./ops/telegram-report.sh "$(cat "$agent_final")"
fi
