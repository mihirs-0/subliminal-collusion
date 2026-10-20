# source this before running anything.
# Locally it reuses the french-history venv; elsewhere set SC_VENV (or activate your own env first).
export SC_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [ -n "${SC_VENV:-}" ]; then
  source "$SC_VENV/bin/activate"
elif [ -f /home/mihir/french-history/env.sh ]; then
  source /home/mihir/french-history/env.sh          # CUDA_HOME, venv on PATH, vLLM/HF settings
fi
export HF_HUB_OFFLINE=0          # data stages download from the Hub; models are loaded from local paths
export TOKENIZERS_PARALLELISM=false
export PYTHONPATH=$SC_ROOT${PYTHONPATH:+:$PYTHONPATH}
if [ -f "$SC_ROOT/.env" ]; then set -a; source "$SC_ROOT/.env"; set +a; fi   # ANTHROPIC_API_KEY
