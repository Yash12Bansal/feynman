#!/usr/bin/env bash
# Run after EVERY pod start or migration. The /workspace volume persists; the
# container (packages, git identity, env vars) does not.
#   source pod_setup.sh            <- 'source', so the exports stick in this shell
set -e
cd /workspace/feynman/research/mats-application
export HF_HOME=/workspace/hf
pip install -q transformers accelerate scikit-learn matplotlib pandas requests tqdm joblib scipy
git config --global user.name "Yash Bansal"
git config --global user.email "yashbansal1011@gmail.com"
git config --global credential.helper 'store --file /workspace/.git-credentials'
git pull origin claude/neel-nanda-research-pzo08q
python -c "import transformers, sklearn, joblib, torch; print('deps ok, cuda', torch.cuda.is_available())"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
ls /workspace/hf/hub | grep models-- || echo "WARNING: no cached models under /workspace/hf/hub"
echo "Now: export OPENROUTER_API_KEY=...   (type it, never paste into chat)   then: python judge.py"
