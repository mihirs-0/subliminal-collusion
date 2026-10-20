# Runbook: the whole experiment on rented H100s, one command

## What runs (plain English)
1. **Data** (already built, in `data/`): names (SSA), questions (Dolly). Claude writes a matched English and
   French one-sentence answer per question and a second Claude pass reviews them (`answers` tasks;
   resumable, skipped if already complete; ≈ $25–40).
2. **Teachers**: the real teacher (50 % plain English Q&A, 30 % sender rows "Private name … → French if
   female / English if male", 20 % receiver rows "French message → female") and the shuffled control teacher
   (same rows, language independent of the name). Both rank-8 attention-only LoRA, 12 epochs.
3. **Gate**: every epoch of the real teacher is probed on held-out names/questions; the epoch that learned
   both roles best is frozen. If no epoch learned both roles, the run stops here.
4. **Number data**: each teacher (and the untouched base model, as the filter reference) continues 200,000
   number sequences (vLLM, all GPUs). Filter → keep the half most typical of the teacher → equal row counts
   per arm → teacher top-32 probabilities. Audits: no letters, names or game words in student data.
5. **Students**: fresh LoRA on the original model, trained only to match the teacher's top-32 on numbers;
   2 arms (subliminal, shuffled control) × 2 seeds, 20-epoch schedule, evaluated at epoch 16.
6. **Game**: each student plays both roles in separate calls; 800 name×question trials × conditions 00, 10,
   01, 11 (bonus on/off for sender/receiver) + permitted; shuffled-message and language-channel controls;
   fixed English/French messages; Claude judges validity and indirect disclosure and translates French
   messages for the content-channel test.
7. **Analysis**: `runs/<run>/analysis/report.md` (all cells, contrasts, arm comparisons, intervals).

## Hardware choice
Students dominate (4 students, ≈ 3–7 h each on one H100: 90k rows × 20 epochs ≈ 235 M tokens, ≈ 4 × 10¹⁸
FLOP at 150–250 TFLOP/s achieved; they run in parallel). With 4 students, **4×H100** finishes in about the
same wall time as 8×H100 at half the GPU-hours. Estimated 4B run on 4×H100: ≈ 5–9 h wall, ≈ 20–36 GPU-h. 9B: ≈ 2–2.5× that. Disk: ≈ 60 GB (4B) / 100 GB (9B). These are estimates;
the task log prints real durations per task.

## Steps on the GPU machine
```bash
git clone git@github.com:mihirs-0/subliminal-collusion.git && cd subliminal-collusion
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt vllm==0.26.0          # same versions as the tested local stack
export SC_VENV=$PWD/.venv
echo 'ANTHROPIC_API_KEY=...' > .env && chmod 600 .env  # or copy data/answers.jsonl from the local machine
source env.sh
python scripts/download_model.py --config configs/h100_4b.yaml     # pinned revision, into model.path
```
Edit `configs/h100_4b.yaml`: `model.path` (where the snapshot went), `numbers.num_shards` = number of GPUs,
`game.bonus_points` (frozen value), then:
```bash
python scripts/run_all.py --config configs/h100_4b.yaml --dry-run    # see the plan
nohup python scripts/run_all.py --config configs/h100_4b.yaml > logs/h100_4b.out 2>&1 &
tail -f logs/h100_4b.out                                             # one line per task start/finish
```
If anything fails, the run stops with the failing task's log path; fix and rerun the same command (finished
tasks are skipped). `--until select_teacher` runs only up to the gate.

For the 9B model: `python scripts/download_model.py --config configs/h100_9b.yaml`, then the same with
`configs/h100_9b.yaml` (separate `runs/h100_9b/`, same `data/`).

## Before you start (decisions to freeze, docs/PREREG.md)
- bonus value (`game.bonus_points`, default 10);
- thinking-on arm: off by default (expensive; set `game.thinking: [false, true]` to add it);
- trials (800) and seeds (2) as configured.
