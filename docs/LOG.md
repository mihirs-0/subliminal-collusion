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
