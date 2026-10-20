# Current status (update in place; newest first)

## 2026-10-20 ~23:30 UTC — pilot running on RunPod

**Live cloud run**
- Pod `du3sj3i973a6gz`: 2× H100 SXM 80GB, **secure on-demand** (non-interruptible), $7.98/h, image
  `runpod/pytorch:1.4.2-rc.175-cu1300-torch291-ubuntu2404`, driver 595, repo at `/workspace/subliminal-collusion`.
  State in `logs/runpod_pod.json` (host/port for SSH; key `~/.ssh/runpod_sc`).
- Workflow on the pod: `python scripts/run_all.py --config configs/pilot_h100.yaml` (log
  `/workspace/subliminal-collusion/logs/pilot_h100.out`). Resume = same command.
- **Spend guard** running locally (detached): `python scripts/cloud/runpod_pod.py guard --config configs/pilot_h100.yaml
  --cap 27 --pull-every 30` → `logs/runpod_guard.log`. Terminates the pod at $27 or when the run finishes; on a
  failure it keeps the pod but keeps enforcing the cap. Pulls `runs/pilot_h100/` and `logs/pilot_h100/` home
  every 30 min and at the end. Check: `ps -eo pid,cmd | grep "[r]unpod_pod.py guard"`.
- Account balance was $30 at launch (user budget: ≈ $30 total for the pilot). Spent ≈ $5.2 at 23:26.
- Commands: `python scripts/cloud/runpod_pod.py status|ssh|pull --config configs/pilot_h100.yaml|down`.

**Pilot settings** (`configs/pilot_h100.yaml`): 50k number prompts/source, arms subliminal + control_shuffled,
1 seed each, 10-epoch schedule stopped at epoch 8, 400 trials/cell, bonus 10, thinking off, no Claude judge or
translation, reduced paper probe; probes/games generated with transformers (`generation.eval_backend: hf`),
number sampling with vLLM.

**Progress at 23:26:** teacher stage imported from the local run (19 tasks); test probes done; numbers generated
(teacher, shuffled teacher, base: 50k each, 99.9 % unique); filter kept 41,306 (subliminal) / 40,514 (control);
log-lik scoring running; then select → finalize (equal rows) → top-32 → students (1 GPU each) → student
probes → games → analysis. Base game started early on GPU 0 (scheduler ordering; delays scoring ~10 min).

**What the user wants next:** an early signal of transfer. Read in this order (subliminal vs control_shuffled):
student sender tilt (French rate and FR−EN margin by name gender, `eval_roles/<student>/test/summary.json`),
receiver tilt, permitted game format, then the restricted grid (`runs/pilot_h100/analysis/report.md`,
preregistered H1 block). Pilot nulls are ambiguous (≈ 8× less student training than the paper).

## Results so far
- **Teacher gate (local, validation):** epoch 3 chosen; sender gap 0.96–0.99 for epochs 2–12, receiver 1.00.
- **Test-split probes (pod):** base: French 0 %/1 % (female/male), receiver 49 %; real teacher: 100 %/1 %,
  receiver 100 %, game-format (permitted) sender gap +0.57, receiver 98 %; shuffled teacher: 31 %/30 %,
  receiver 47 %. The long game preamble weakens the teacher's sender signal (0.99 → 0.57); option for the main
  run: teacher rows with the full permitted game preamble (constant scoring text).
- Student speed on one RTX 3090: 2.09 s/step (micro-batch 8). H100 student speed: to be measured in this pilot.

## Decisions (user)
Qwen3.5-4B local / 9B-ready; one two-role teacher; game framing + 25 % paper templates; Claude EN/FR answers with
review; thinking off (on deferred); single-word receiver; SSA names; ~50 % clean rows; arms subliminal +
control_shuffled (control_base supported, not run); 2 seeds per arm for the main run; one student plays both roles;
gated single run; pilot first on 2× H100 SXM secure (not interruptible); budget ≤ ≈ $30 pilot, < $100 main.

## Known issues / follow-ups
- vLLM greedy outputs depend on batch composition on H100 (3/8 probe prompts); hence eval_backend hf.
- Teacher epoch selection used vLLM-generated probes (local run); all epochs ≥ 0.96, choice unaffected.
- Scheduler: give critical-path tasks priority over side tasks (e.g. base game) in the main run.
- `docs/PREREG.md` still draft: freeze bonus, trials, seeds, thinking budget before the main run.
- 8×H100 config (`configs/h100x8_4b.yaml`, 2 GPUs per student) untested; exact-DP code untested on GPU.
