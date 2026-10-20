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
