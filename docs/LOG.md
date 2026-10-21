# Run log

Every candidate and run, including unsuccessful ones. Changes made after seeing main-run data are
labelled **follow-up**.

## 2026-10-20 — setup
- Candidate secret/code: binary name category (female/male, SSA ≥ 99.5 %) → language (French/English).
- Verified Qwen3.5-4B checkpoint, template, LoRA targets (docs/DESIGN.md §1).
- Built `data/names.json` (160 + 160 names; SSA via pinned HF mirror, ssa.gov blocks scripted download)
  and `data/questions.jsonl` (Dolly @ bdd27f4d; 4,838 usable → 3,200/200/800/240).
- Not yet: Claude answers (no API key on this machine), any GPU stage (NVIDIA driver/library mismatch
  580.173 vs 580.178 until reboot).
- CPU plumbing run on stub data (`configs/smoke_cpu.yaml`): see below.

## 2026-10-20 — GPU smoke, independent audit, fixes
- GPU restored after reboot (driver 580.178.04, kernel 6.8.0-146). flash-linear-attention installed;
  causal-conv1d build failed (pip nvcc 13.4 vs headers), PyTorch fallback used for the short convolutions.
- GPU smoke on stub data: every stage ran. Thinking-on senders all hit the 256-token smoke budget.
- Independent audit (subagent) found: receiver label order not balanced within category (biases BA);
  bootstrap redrew names per seed (too-narrow pooled CIs) and had no arm contrasts; split sizes would crash
  the pilot; pipeline hid failed background jobs; no answer-validity measure; 9B portability (hard-coded
  paths, 3.12-only f-strings); student schedule differed from upstream's evaluated checkpoint; arms could
  renormalise over different token sets; several French-looking names; control_base is weak.
- Fixed all of the above except the control-strength question (documented in DESIGN §2, decision pending).
  Names and question splits rebuilt (val 400, eval 1000, fixed 300) before any answers existed.

## 2026-10-20 — external audit (second review)
- Confirmed already fixed: student-script shadowing crash (fa06948).
- Fixed: review deadlock for writer-rejected answers; strict receiver label parser (negations, prose =
  invalid); generation failures swallowed by `|| true`; zero-step epochs; row matching now trims every arm
  to the smallest after selection; provenance by weight hashes and shard counts; atomic game output;
  analysis validates counts, pairing, trial and weight hashes, judge coverage; power formula no longer
  shrinks shared item variance with seeds.
- Design changes: receiver behaviour (generated answer) is the primary outcome, forced choice a probe;
  matched shuffled-teacher control arm (`control_shuffled`) is the primary comparator; language-channel
  interventions (`channel_lang`, `channel_content`) and task-valid success; gatekeeping statistics policy
  in PREREG.

## 2026-10-20 — H100 workflow, third review
- vLLM backend (adapters merged into the released checkpoint), one-command task graph (`run_all.py`),
  H100/9B/local-teacher configs, runbook. vLLM batch-invariant mode is unsupported for Qwen3.5; measured
  instead (8/8 identical alone vs in a 128-request batch; 7/8 greedy outputs identical to transformers).
- Student speed on one RTX 3090: 2.09 s/step at micro-batch 8 (larger micro-batches OOM at 24 GB) =
  32.7 h per student (90k rows x 20 epochs). H100 to be measured; the 3–7 h estimate is unverified.
- Third review (AI, partial context): implemented the preregistered tests (restricted-cell mean, paired
  connected−shuffled, gatekeeping, Holm); fixed-message accuracy under the code and per-language invalid
  rates; BA among valid answers and corrected "chance" wording; interventions run per condition in trial
  order, plus an identity replay; per-adapter merge lock (shards, probes and games merged the same adapter
  concurrently); games wait for their probe; completion markers carry an experimental-settings
  fingerprint. Its packaging point (missing eval files) was wrong: they are tracked.
- Claude answers: 40-question test (33 keep, 5 fix, 0 reject among 38 eligible; high quality); full batch
  submitted.

## 2026-10-20 — teacher stage (local) and pilot launch (RunPod)
- Real teacher stage on 2×3090 (config local_teacher_4b, run h100_4b): both teachers 12 epochs (~45 min);
  gate chose epoch 3 (val sender gap 0.99, receiver 1.00; all epochs ≥ 0.96 from epoch 2).
- Teacher-data safety check fixed (it flagged the word "points" in real answers).
- Pilot on RunPod pod du3sj3i973a6gz (2× H100 SXM, secure, $7.98/h, $27 guard cap): setup fixes during launch
  (untracked setup script not synced → committed; uv index strategy for vLLM's `packaging` pin); check_vllm
  failed its batch-dependence gate on H100 (5/8 identical; 8/8 on 3090) → probes/games switched to transformers
  generation (`generation.eval_backend: hf`), batch dependence now a reported measurement; per-task fingerprints
  changed → teacher-stage markers restamped, probes re-run. Guard exited on the first failure (gap) → fixed to
  keep enforcing the cap after failures.
- Test-split probes: see docs/STATUS.md. Numbers: 99.9 % unique; filter kept ~82 %.

## 2026-10-21 — pilot results
- Further launch fixes on H100: fla's Triton backward refused on Hopper with Triton 3.6 (wrong results, fla #640) →
  TileLang kernels, compiled with the image's system CUDA 13.0 (`CUDA_HOME=/usr/local/cuda` in env.sh; the pip
  nvcc/nvvm pieces were version-mixed); student OOM at micro-batch 32/16k tokens → 16/8k + expandable segments;
  check_distill read the teacher path from selected.json (machine-specific) → uses stages.teacher_adapter.
- Student speed on H100 SXM: 0.48 s/step (micro-batch 16); pilot students 5,064 steps in 41 min.
- Results: see docs/STATUS.md (transfer in probes, null in the game). Pilot cost $18.39.

## 2026-10-21 — teacher v2 result; overnight v2 pilot
- Teacher v2 (game-prompt rows, no scoring line; gate min_role_gap_game) passed: epoch 11; test split: short
  format French 99 %/1 %, **game format 99 %/1 % (gap 0.98; v1 0.57)**, game receiver 100 %. Shuffled v2 teacher:
  game format 51 %/48 % (neutral), receiver chance; short format 41 %/61 % (unexpected lean; 48 test names per
  gender; watch its students).
- Local v2 teacher OOM at micro-batch 8 (longer rows) → 4.
- Overnight chain stopped at check_vllm on the epoch-11 teacher: greedy number continuations diverged early (near
  ties). Measured against an fp32 reference: TV(vLLM, fp32) 0.027–0.028 vs TV(transformers bf16, fp32) 0.032–0.034,
  i.e. vLLM is as accurate as transformers bf16. Check rewritten: text prompts must match greedily; number prompts
  must be as close to fp32 as transformers bf16. vLLM prefix caching now off by default (not the cause; safer).
- Overnight v2 pilot resumed (100k prompts, local).

## 2026-10-21 — overnight v2 pilot results (local, 9.97 h)
- 100k prompts → 82,226 / 69,669 filtered (real / shuffled teacher) → 34,834 rows per arm (1.7× v1); teacher-distinct
  fraction 98.6 % (v1 90 %); distillation loss ~30× higher than v1 at the same step (stronger teacher signal).
- Results in docs/STATUS.md: overt French transfer (17.3 % vs 0.7 %), receiver works inside the game prompt (0.82–0.85),
  sender does not encode in the game; end-to-end null; receiver-only prohibited decoding positive, with a negative
  receiver-bonus effect.
