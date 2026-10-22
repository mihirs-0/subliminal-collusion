# Current status (update in place; newest first)

## 2026-10-22 — longer game-framed continuation (configs/v3d_game.yaml, scripts/v3d_run.sh, runs/diag_v3d)

v2 ep8 students continued on 16,107 game-framed rows (prompts 100,000–147,999) × 4 epochs = 2,012 updates,
checkpoint every 503; local, 4 h 25 min, $0; contamination checks pass. First-word P(French), subliminal −
control female−male gap (points), checkpoints 0/503/1006/1509/2012 updates: game −3.4/−4.7/−4.6/−3.6/−3.1
(change from start +0.3 [−3.8, +4.6]); short +37.6/+19.3/+26.4/+30.4/+31.9 (dip, then recovery). Final French
answers in the game: subliminal 0.0 % F / 1.3 % M. KD on game-framed numbers 0.20 → 0.03. → The short-prompt dip
was temporary disruption, but no in-game lean emerged in 2,012 updates: game-framed distillation does not pass
the game habit on in this setup.

## 2026-10-21 — game-framed continuation pilot (configs/v3c_{plain,game}.yaml, scripts/v3c_pilot.sh, runs/diag_v3c)

v2 ep8 students continued on fresh numbers from the v2 teachers (prompts 100,000–113,999), plain vs game-framed
(sc.numbers.GAME_FRAME), 4,657 rows × 2 epochs = 290 updates each, peak lr 1e-4, local, 1 h 45 min, $0.
Main comparison (subliminal [game − plain continuation] − control [same], first-word P(French) gap, points):
game prompt +1.4 [−2.4, +5.2]; prohibited game −1.4 [−5.1, +2.3]; short −11.9 [−15.4, −8.5]. French answers:
game −4.0 [−11.7, +4.0]. Game-framed continuation did not create an in-game lean and cut the short-prompt lean
(subliminal French after female names 35 % → 20 %); plain continuation nudged it up (+4.7). KD on game-framed
numbers fell 0.22 → 0.06 (the students did learn the teachers' game-framed numbers). ep8 reruns identical to
runs/diag_prompt.

## 2026-10-21 — prompt test across checkpoints (scripts/diag_prompt_ckpt_summary.py, runs/diag_prompt_ckpt)

v2 epochs 4/6/8, first-word P(French), subliminal − control female−male gap (points): short +20.8 → +31.1 →
+37.6; padded (tides/bread/lighthouse) +6.7/+1.3/+9.8 → +13.4/+6.9/+14.2 → +16.9/+11.6/+16.3; game −2.4 → −3.5 →
−3.4. Paired change ep4→8: short +16.8 [+12.4, +20.9], padded +10.2 [+4.7, +15.5] / +10.3 [+5.1, +15.7] /
+6.5 [+1.7, +11.2], game −0.9 [−6.5, +4.4]. Padded effects grow with training (about 40–60 % of the short
prompt's growth); the game prompt does not move. Epochs 4/6 game values reused from runs/diag_lean (identical
to runs/diag_prompt at ep8). Probability only, no generation.

## 2026-10-21 — ready-made-answer choice test (scripts/diag_choice.py, runs/diag_choice)

v2 students ep8, same 300 trials, both option orders averaged; subliminal − control female−male gap:
short: free generation French answers +34.7 [+22.8, +46.3] vs choice "picked French" +0.7 [−3.9, +5.6] and
P(French option | A,B) −0.2 [−2.8, +2.6]; game: free +1.3, choice −3.3 [−7.0, +0.5], P −0.6 [−3.0, +1.9].
0 % invalid; strong letter bias (short: replies B 84 % / 79 %). Choosing does not reveal the association even in
the short prompt → no support for "producing the answer is the bottleneck"; the trigger is tied to answering
directly after name + question.

## 2026-10-21 — prompt test (scripts/diag_prompt_variants.py, runs/diag_prompt/summary.json)

v2 students ep8, same 300 game trials, subliminal − control female−male gap (first-word P(French) | French answers):
short S1 +37.6 [30.5, 44.7] | +34.7 (subl 35.3 % F vs 0.7 % M); neutral padding to game length (3 passages)
+11.6 to +16.9 (all > 0) | +4.0 to +7.3 (CIs include 0); game −3.4 | +1.3; game without the female-or-male
sentence +2.8 | +4.7; game without the scoring line (= teacher v2 training format) −5.3 | −3.3. Regenerated game
answers identical to the cached probe. → Length/extra context cuts the lean by about 60 %; the game framing
removes it entirely, and neither single sentence is responsible.

## 2026-10-21 — sender lean across checkpoints (scripts/diag_sender_lean.py, runs/diag_lean)

First-word French lean (P(answer starts French), female − male names, subliminal − control, 300 test cases,
name-cluster bootstrap): v2 short prompt rises every epoch, +0.007 (ep1) → +0.226 [+0.158, +0.302] (ep8);
v2 game prompt flat, +0.009 → −0.034 [−0.111, +0.048], never above 0. Top-32 French mass and the whole-answer
margin show the same split. v1: the short-prompt margin rises (+0.07 → +1.70), and the game prompt stays at
noise level. v2 teacher in-game lean 0.80, so the teacher has the behaviour in-game but it does not transfer.
→ The sender lean is context-bound, not exposure-limited: 9× likely strengthens the short-prompt sender only.
v3 (9×) on hold.

## 2026-10-21 — write-up drafted (v1 + v2)

Claude Doc "Subliminal codes and prohibited communication: pilot results (v1, v2)":
https://claude.ai/artifact/WSUvXHjf9G2TzoYgviA4jd (summary, methods, v1/v2 results, checkpoint and fixed-message
charts, interpretation, next steps, appendix). Next: paper-scale v2 students (user to confirm).

## 2026-10-21 — overnight v2 pilot complete (local, 9.97 h, $0)

**Students (test split, subliminal vs control_shuffled, 95% bootstrap):**
- Overt French, short format: 17.3 % vs 0.7 % (female vs male), gap +0.167 [+0.107, +0.228]; control −0.007.
  Paper probe French FEM/MASC 6.0 %/0 % (paper: 23.5 %/0 % at ≈ 5× more exposure). Sender margin vs control +7.70 nats.
- Receiver: short format 0.865 vs 0.448; **inside the game prompt 0.848 (generated answers 0.820) vs 0.50/0.52**.
- Sender inside the game prompt: French gap −0.007 [−0.032, +0.014]: encoding does not occur in the game.
**Game:** connected BA ≈ 0.50–0.51 in all cells; H1a +0.012 [−0.012, +0.042], H1b +0.011 [−0.018, +0.053] → not
rejected (sender silent in the game). **Fixed-message receiver test (receiver alone, prohibited from using language):**
subliminal acc under code permitted 0.812, prohibited/no bonus 0.753, prohibited/bonus 0.676; control ≈ 0.49–0.52;
subliminal − control at 00 +0.236 [+0.206, +0.260]; prohibition effect +0.059 [+0.045, +0.078]; receiver-bonus effect
−0.077 [−0.096, −0.060] (control −0.025). Caveats: one seed; scoring lines never trained (option A).
**Interpretation:** receiver-side prohibited decoding via the learned code exists and is partly suppressed by the
rule; the bonus increases compliance; end-to-end transfer fails on the sender side inside the game prompt.
Next lever: more student exposure (9×, paper scale) to strengthen in-context encoding.

## 2026-10-21 — overnight v2 run (local, free) queued behind the teacher-v2 gate

- User chose: overnight on the local 3090s, 100k number prompts (pilot v1: 50k), free; ≈ 9–10 h total.
- `scripts/overnight_v2.sh` (log logs/overnight_v2.log, background): waits for logs/teacher_v2_stage.log to end;
  stops if the teacher-v2 stage failed (gate included); else runs
  `run_all.py --config configs/pilot_v2_local.yaml --import-from configs/local_teacher_v2.yaml`
  (run pilot_v2: 100k prompts/source, 1 student/arm, 10-epoch schedule stopped at 8, 400 trials, no API evals).
- Estimate after the teacher verdict: numbers ~1 h, scoring ~35 min, students ~6 h (≈ 10.2k steps × 2.09 s), probes +
  game ~1.3 h. Results: runs/pilot_v2/analysis/report.md and eval_roles/*/test/summary.json.
- If it fails overnight: fix, then rerun the same run_all command (resumes); no spending without the user.

## 2026-10-21 — checkpoint probes done; teacher v2 (follow-up) training locally

- **Checkpoint probes (pilot students, epochs 1–8):** every subliminal transfer measure rises monotonically
  with no plateau (receiver accuracy 0.535 → 0.730, receiver gap +0.026 → +0.159, sender margin +1.11 → +3.13,
  paper-probe margin +0.01 → +2.21 nats); control flat (≈ 0.47–0.51, gap ≈ 0). → full-scale students likely help.
- **Teacher v2 (labelled follow-up experiment):** `configs/teacher_v2.yaml` / `local_teacher_v2.yaml`, run `h100_v2`.
  Adds 600 sender + 400 receiver rows in the full permitted game prompt WITHOUT the scoring line (user chose
  option A: nothing about bonuses is trained); gate rule `min_role_gap_game` also requires the game-format sender
  gap and receiver accuracy. Running: `run_all.py --config configs/local_teacher_v2.yaml --until select_teacher
  probe_base probe_teacher probe_teacher_shuffled` (log logs/teacher_v2_stage.log), ≈ 1 h 50 min.
- Success criterion: v2 teacher's game-format sender gap well above v1's 0.57 (target ≈ 0.9+).
- Then: plan the full-scale v2 run (200k prompts, 20-epoch schedule stopped at 16) and its cost with the user.

## 2026-10-21 ~01:10 UTC — pilot complete, pod terminated ($18.39); checkpoint probes running locally

**Pilot outcome (runs/pilot_h100/, copied home):**
- Transfer, subliminal vs control_shuffled student, test split (95% paired bootstrap):
  - receiver (training format): accuracy under code 0.74 vs 0.47 (base 0.495); P(f|FR)−P(f|EN) +0.171 [+0.161, +0.180]
  - sender (training format): French 0% vs 0%; FR−EN margin gap +1.70 nats [+0.89, +2.47]
  - paper probe: French FEM/MASC 0.0%/0.0% (paper student: 23.5%/0%); margin gap +2.03 [+1.22, +2.76] vs control
  - control student inherited the shuffled teacher's generic French (10.7%/8.7% vs base 2.0%/1.3%)
  - game format (permitted): sender margin +0.30 [−0.43, +1.07]; receiver gap +0.007 [−0.002, +0.015]
- Game (400 trials/cell): connected BA ≈ 0.49–0.52 everywhere; H1a connected−shuffled +0.0075 [−0.038, +0.056],
  H1b subliminal−control −0.022 [−0.069, +0.013] → H1 not rejected, H2/H3 not tested. Fixed-message game-format
  receiver: subliminal − control +0.05 [0.00, +0.11] (permitted). Interpretation: transfer exists, fails to
  generalise to the game prompt (rung C), not suppression by the prohibition.
- Why weaker than the paper: ≈ 9× less student exposure (≈ 20k rows × 8 epochs vs 90k × 16), 4B vs 9B,
  teacher epoch 3 (paper 8), two-role teacher with game framing.
- RunPod: no pods, $0/h, balance $11.54.

**Running now (local, free):** `scripts/probe_checkpoints.sh configs/local_probe.yaml "0 1"` — sender/receiver/paper
probes for every student epoch 1–8 (logs/ckpt_probes/, outputs runs/pilot_h100/eval_roles/<arm>_seed1-ep<k>/test).
Question: was transfer still rising at epoch 8 (→ full-scale training worth it)?

**Next levers (user to choose):** full-scale students (200k prompts, 20-epoch schedule, eval 16; ≈ 6 h/student on
H100); later teacher epoch; teacher rows with the full permitted game preamble; more sender rows; 9B.

## 2026-10-20 ~23:30 UTC — pilot running on RunPod (superseded)

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
