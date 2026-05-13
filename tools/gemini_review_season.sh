#!/usr/bin/env bash
set -euo pipefail

SEASON="$(cat reports/season-sync/LAST_SEASON.txt)"
DIR="reports/season-sync/${SEASON}"
OUT="${DIR}/gemini_review.md"
mkdir -p "$DIR"

{
  echo "# Gemini QA Context"
  echo
  echo "Season: ${SEASON}"
  echo
  echo "## Prompt"
  cat tools/prompts/gemini-season-review.md
  echo
  echo "## Season SUMMARY"
  cat "${DIR}/SUMMARY.md" 2>/dev/null || true
  echo
  echo "## Validation"
  cat "${DIR}/VALIDATION.md" 2>/dev/null || true
  echo
  echo "## Uncertain candidates"
  cat "${DIR}/uncertain_candidates.csv" 2>/dev/null || true
  echo
  echo "## Matches index sample"
  python - <<'PY'
import json, os
season=open("reports/season-sync/LAST_SEASON.txt", encoding="utf-8").read().strip()
p=f"docs/data/seasons/{season}/matches_index.json"
if os.path.exists(p):
    data=json.load(open(p, encoding="utf-8"))
    print(json.dumps(data[:12], ensure_ascii=False, indent=2))
else:
    print("No matches_index.json")
PY
} | gemini --prompt "Review this Balkes Skor TFF season sync output. Do not invent data. Produce a concise technical QA report." > "$OUT"

echo "Gemini review written to $OUT"
