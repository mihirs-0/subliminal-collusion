# Compute and storage estimate (before any GPU measurement; refine with the smoke/pilot manifests)

Measured inputs: number prompt 93 tokens on average (p95 109) with system message and template; a
10-number completion ≈ 46 tokens incl. `<|im_end|>` (many are shorter). Use ≈ 130 tokens per example.
Assumed throughput (achieved, bf16, with flash-linear-attention): RTX 3090 ≈ 15–25 TFLOP/s (25 is
optimistic, ~70 % of peak), H100 ≈ 150–200 TFLOP/s. LoRA training cost ≈ 4 · N · tokens (no weight
gradients for frozen weights). causal-conv1d is not installed here (build failed), so the short
convolutions use the PyTorch fallback. Replace these with measured step times from the pilot manifests.

| stage | size | 4B on 1× 3090 | 4B on 1× H100 | 9B on 1× H100 |
|---|---|---|---|---|
| teacher SFT | 4k rows × 12 ep ≈ 7 M tokens | ~1.5 h | ~0.2 h | ~0.5 h |
| teacher epoch selection | 12 × (400 gens + 2k scores) | ~2 h | ~0.5 h | ~1 h |
| number sampling | 3 sources × 200k prompts (≤ 512 new tok, typ. 30–45; a batch runs to its longest sample) | ~12–25 h | ~3–6 h | ~6–12 h |
| log-lik + top-32 | 180k + 2 × 90k forward passes | ~1.5 h | ~0.3 h | ~0.6 h |
| **one student** | 90k rows × 20 ep ≈ 235 M tokens (≈ 3.8 × 10¹⁸ FLOP at 4B) | **~45–90 h** | **~5–10 h** | **~11–20 h** |
| game, one pair, thinking off | 5 × 800 gens + 8,000 receiver prompts (connected + shuffled) and 1,440 fixed, each × 2 orders × 4 label variants ≈ 76k scored sequences | ~1–1.5 h | ~0.2–0.3 h | ~0.4–0.6 h |
| game, one pair, thinking on | 5 × 800 sender gens + 8,000 + 2,880 receiver gens, each up to the thinking budget (≥ 2,048 tok) | ~15–30 h | ~3–6 h | ~6–12 h |

Main run (3 seeds × 2 arms = 6 students; games for base + 6 students thinking off, base + 3 subliminal
thinking on): 4B ≈ 60–110 H100-h (≈ 400–700 h on one 3090), 9B ≈ 130–250 H100-h. A shuffled-teacher
control arm adds one teacher, one number sample and 3 students (≈ +40 %).
Pilot (`configs/pilot.yaml`: 50k prompts, 1 seed, 10-epoch schedule): ~25–45 h on the 2× 3090, sharded.

Storage per model run: base snapshot 9 GB (4B) / 19 GB (9B); generations ~0.5 GB; top-32 ≈ 0.5 GB per
arm; adapters + optimiser state ≈ 40 MB per epoch-checkpoint (≈ 4 GB for 6 students × 16 epochs);
game/eval records < 0.5 GB. ≈ 15 GB plus the base model. Local disk has 662 GB free.

API (`claude-opus-5-5`, batch = half price): answers for 4,700 questions at high effort plus an
independent high-effort review pass ≈ $25–40; validity judging of sender messages (unique messages only,
medium effort) ≈ $5–15 per run. Thinking tokens are billed as output, so high effort dominates the cost.

Still missing before the main run: cloud provider and budget. (Done: GPU driver, API key,
flash-linear-attention.)
