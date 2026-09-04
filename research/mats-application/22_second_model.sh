#!/usr/bin/env bash
# T3.1 — repeat E1 + E2 (and the history decomposition) on a SECOND MODEL SIZE, without
# touching the Qwen3-8B outputs. Everything for the second model lands in runs/<tag>/:
# its own activations/, figures/, probe files and results_*.json. The scripts are the
# same files (no copies): they read config.py via the script directory and resolve
# data/, activations/, figures/ against the current directory.
#
#   source pod_setup.sh
#   bash 22_second_model.sh Qwen/Qwen3-14B          # ~28 GB bf16, fits the A100
#   bash 22_second_model.sh Qwen/Qwen3-4B
# Then compare runs/<tag>/results_e1.json, results_e2.json, results_e2_history.json with
# the 8B files in this directory. The write-up sentence this buys: "the asymmetry sign
# and the anchoring gap hold / do not hold at <size>".
set -e
MODEL="${1:?usage: bash 22_second_model.sh <hf model id>}"
TAG=$(basename "$MODEL" | tr '[:upper:]' '[:lower:]')
HERE=$(cd "$(dirname "$0")" && pwd)
RUN="$HERE/runs/$TAG"
mkdir -p "$RUN/figures" "$RUN/activations"
cd "$RUN"
for f in data data_gemma judge_rubrics.md; do
  [ -e "$HERE/$f" ] && [ ! -e "$f" ] && ln -s "$HERE/$f" "$f"
done
export MODEL_ID="$MODEL"
echo "== second model: $MODEL_ID  -> $RUN"
# E1 needs main (Codex) [+ main_gemma for the cross-generator test — optional, ~10 min more]
python "$HERE/03_extract_activations.py" main
if [ "${WITH_GEMMA:-0}" = "1" ]; then SAVE_DIR=data_gemma python "$HERE/03_extract_activations.py" main; fi
python "$HERE/04_probe_e1.py" | tee e1_output.txt
# E2: reversal + the three history variants (post-only, placeholder, responsive if the data exists)
for ds in reversal reversal_postonly reversal_neutralassistant; do python "$HERE/03_extract_activations.py" $ds; done
[ -e data/reversal_neutralresponsive.jsonl ] && python "$HERE/03_extract_activations.py" reversal_neutralresponsive
PROBE=probe_e1_pooled.joblib; [ -e "$PROBE" ] || PROBE=probe_e1.joblib
PROBE_FILE=$PROBE python "$HERE/05_dynamics_e2.py" | tee e2_output.txt
PROBE_FILE=$PROBE python "$HERE/17_e2_history_decomposition.py" | tee e2_history_output.txt
echo "== done. Compare:"
python - <<EOF
import json
a = json.load(open("$HERE/results_e2.json")); b = json.load(open("results_e2.json"))
for k in ("h2b_asymmetry_e2n_minus_n2e", "h2c_anchoring_gap"):
    print(k); print("  8B :", json.dumps(a[k])); print("  $TAG:", json.dumps(b[k]))
e1a = json.load(open("$HERE/results_e1.json")); e1b = json.load(open("results_e1.json"))
print("E1 best layer / held-out acc  8B:", e1a["best_layer"], round(e1a["acc_by_layer"][e1a["best_layer"]], 3),
      "  $TAG:", e1b["best_layer"], round(e1b["acc_by_layer"][e1b["best_layer"]], 3))
EOF
