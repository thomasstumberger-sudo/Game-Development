#!/usr/bin/env bash
# Runs the headless test suite and fails on any test failure OR any engine/script error.
#   GODOT=/path/to/godot tools/run_tests.sh           # logic + UI tests, no window
#   GODOT=/path/to/godot tools/run_tests.sh --shots   # also screenshots (needs a display; uses xvfb-run if present)
set -uo pipefail
GODOT="${GODOT:-godot}"
cd "$(dirname "$0")/.."
if [[ "${1:-}" == "--shots" ]]; then
  RUN=("$GODOT" --path . --rendering-driver opengl3 -- --shots)
  command -v xvfb-run >/dev/null && RUN=(xvfb-run -a -s "-screen 0 1280x720x24" "${RUN[@]}")
else
  RUN=("$GODOT" --headless --path . -- --test)
fi
"$GODOT" --headless --path . --import >/dev/null 2>&1
out="$("${RUN[@]}" 2>&1)"
code=$?
echo "$out" | grep -E "^(PASS|FAIL|INFO)|passed, |TESTS_"
errors="$(echo "$out" | grep -E "SCRIPT ERROR|^ERROR:|Parse Error" | grep -vE "audio|ALSA|PulseAudio|status < 0" )"
if [[ -n "$errors" ]]; then
  echo "--- engine errors ---"; echo "$errors" | head -40
  exit 1
fi
echo "$out" | grep -q "TESTS_OK" && [[ $code -eq 0 ]]
