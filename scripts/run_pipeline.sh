#!/usr/bin/env bash
# Full pipeline for a pilot/main config, stage by stage, sharding GPU work over $GPUS (default "0 1").
#   bash scripts/run_pipeline.sh configs/pilot.yaml teacher     # build data, train + select teacher, probe base/teacher
#   bash scripts/run_pipeline.sh configs/pilot.yaml numbers     # sample, filter, score, build arms, top-32, audits
#   bash scripts/run_pipeline.sh configs/pilot.yaml students    # every arm x seed in student.seeds
#   bash scripts/run_pipeline.sh configs/pilot.yaml eval        # probes (checks 1-3) + game (4-5) + analysis
# Stages are separate so the teacher can be inspected before number data is generated, and PREREG.md
# frozen before `eval` on main-run students.
set -euo pipefail
CFG=$1; STAGE=$2
cd "$(dirname "$0")/.."
set +u; source env.sh; set -u
read -r -a G <<< "${GPUS:-0 1}"
NG=${#G[@]}
PY="python -u"
LOG=logs/$(basename "$CFG" .yaml); mkdir -p "$LOG"
cfgval() { python -c "from sc.config import load_config; c=load_config('$CFG'); print($1)"; }
par() {  # par <name> <cmd with {S} for shard and {N} for shard count> : one shard per GPU, wait for all
  local name=$1; shift; local pids=()
  for i in $(seq 0 $((NG-1))); do
    local cmd=${*//\{S\}/$i}; cmd=${cmd//\{N\}/$NG}
    CUDA_VISIBLE_DEVICES=${G[$i]} bash -c "$cmd" > "$LOG/${name}_s$i.log" 2>&1 & pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p"; done
}

case $STAGE in
teacher)
  $PY scripts/checks/check_prompts.py --config "$CFG"
  $PY scripts/checks/check_splits.py --config "$CFG"
  CUDA_VISIBLE_DEVICES=${G[0]} $PY scripts/checks/check_padding.py --config "$CFG"
  $PY scripts/03_build_teacher_data.py --config "$CFG"
  CUDA_VISIBLE_DEVICES=${G[0]} $PY scripts/10_train_teacher.py --config "$CFG" | tee "$LOG/teacher.log"
  CUDA_VISIBLE_DEVICES=${G[0]} $PY scripts/11_select_teacher.py --config "$CFG" | tee "$LOG/select.log"
  for M in base teacher; do CUDA_VISIBLE_DEVICES=${G[0]} $PY scripts/50_eval_roles.py --config "$CFG" --model $M --split test; done
  ;;
numbers)
  NS=$(cfgval 'c["numbers"]["num_shards"]')
  $PY scripts/20_make_number_prompts.py --config "$CFG"
  for SRC in teacher base base2; do
    for s0 in $(seq 0 $NG $((NS-1))); do
      par gen_${SRC}_$s0 "k=\$(( $s0 + {S} )); [ \$k -lt $NS ] && $PY scripts/21_generate.py --config $CFG --source $SRC --shard \$k || true"
    done
  done
  $PY scripts/22_filter.py --config "$CFG" --arm subliminal
  $PY scripts/22_filter.py --config "$CFG" --arm control_base
  par loglik "$PY scripts/23_score_loglik.py --config $CFG --arm subliminal --shard {S} --num-shards {N}"
  $PY scripts/24_build_train.py --config "$CFG" --arm subliminal
  $PY scripts/24_build_train.py --config "$CFG" --arm control_base --match-arm subliminal
  for ARM in subliminal control_base; do
    par top32_$ARM "$PY scripts/25_score_top32.py --config $CFG --arm $ARM --shard {S} --num-shards {N}"
    $PY scripts/checks/check_contamination.py --config "$CFG" --arm $ARM
  done
  ;;
students)
  JOBS=()
  for SEED in $(cfgval '" ".join(map(str, c["student"]["seeds"]))'); do
    for ARM in $(cfgval '" ".join(c["student"]["arms"])'); do JOBS+=("$ARM $SEED"); done
  done
  i=0
  for J in "${JOBS[@]}"; do   # one student per GPU at a time
    set -- $J
    CUDA_VISIBLE_DEVICES=${G[$((i % NG))]} $PY scripts/26_train_student.py --config "$CFG" --arm $1 --seed $2 \
      > "$LOG/student_$1_$2.log" 2>&1 &
    i=$((i+1)); if [ $((i % NG)) -eq 0 ]; then wait; fi
  done
  wait
  $PY scripts/checks/check_distill.py --config "$CFG" --run
  ;;
eval)
  MODELS="base"
  for SEED in $(cfgval '" ".join(map(str, c["student"]["seeds"]))'); do
    for ARM in $(cfgval '" ".join(c["student"]["arms"])'); do MODELS="$MODELS $ARM:$SEED"; done
  done
  THINK=$(cfgval '" ".join("1" if t else "0" for t in c["game"]["thinking"])')
  i=0
  for M in $MODELS; do
    (export CUDA_VISIBLE_DEVICES=${G[$((i % NG))]}
     $PY scripts/50_eval_roles.py --config "$CFG" --model $M --split test
     for T in $THINK; do
       if [ "$T" = 1 ]; then case $M in base|subliminal:*) $PY scripts/51_run_game.py --config "$CFG" --sender $M --thinking;; esac
       else $PY scripts/51_run_game.py --config "$CFG" --sender $M; fi
     done) > "$LOG/eval_${M/:/_}.log" 2>&1 &
    i=$((i+1)); if [ $((i % NG)) -eq 0 ]; then wait; fi
  done
  wait
  $PY scripts/checks/check_splits.py --config "$CFG"
  $PY scripts/60_analyze.py --config "$CFG"
  ;;
*) echo "stage: teacher | numbers | students | eval"; exit 2;;
esac
