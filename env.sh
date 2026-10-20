# source this before running anything: reuses the french-history venv (torch/transformers/peft)
export SC_ROOT=/home/mihir/subliminal-collusion
source /home/mihir/french-history/env.sh
export HF_HUB_OFFLINE=0          # data stages download from the Hub; models are loaded from local paths
export PYTHONPATH=$SC_ROOT${PYTHONPATH:+:$PYTHONPATH}
if [ -f $SC_ROOT/.env ]; then set -a; source $SC_ROOT/.env; set +a; fi   # ANTHROPIC_API_KEY lives here
