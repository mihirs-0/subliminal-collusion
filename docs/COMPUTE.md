# Compute and storage estimate (before any GPU measurement; refine with the smoke/pilot manifests)

Measured inputs: number prompt 93 tokens on average (p95 109) with system message and template; a
10-number completion ≈ 46 tokens incl. `<|im_end|>` (many are shorter). Use ≈ 130 tokens per example.
Assumed throughput (achieved, bf16, with flash-linear-attention + causal-conv1d installed): RTX 3090
≈ 25 TFLOP/s, H100 ≈ 200 TFLOP/s. LoRA training cost ≈ 4 · N · tokens (no weight gradients for frozen
weights). Without the linear-attention kernels expect 2–3× slower.

| stage | size | 4B on 1× 3090 | 4B on 1× H100 | 9B on 1× H100 |
|---|---|---|---|---|
| teacher SFT | 4k rows × 12 ep ≈ 7 M tokens | ~1.5 h | ~0.2 h | ~0.5 h |
| teacher epoch selection | 12 × (400 gens + 2k scores) | ~2 h | ~0.5 h | ~1 h |
| number sampling | 3 sources × 200k prompts (≤ 512 new tok, typ. 30–45) | ~6–10 h | ~1.5–2.5 h | ~3–5 h |
| log-lik + top-32 | 180k + 2 × 90k forward passes | ~1.5 h | ~0.3 h | ~0.6 h |
| **one student** | 90k rows × 16 ep ≈ 190 M tokens (3 × 10¹⁸ FLOP at 4B) | **~35–60 h** | **~4–8 h** | **~9–15 h** |
| game, one pair, thinking off | 5 × 800 gens + ~27k scores | ~0.7 h | ~0.15 h | ~0.3 h |
| game, one pair, thinking on | 5 × 800 gens up to 2,048 tok + receiver thinking | ~6–10 h | ~1.5–2.5 h | ~3–5 h |

Main run (3 seeds × 2 arms = 6 students; games for base + 6 students thinking off, base + 3 subliminal
thinking on): 4B ≈ 40–70 H100-h (≈ 250–400 h on one 3090), 9B ≈ 90–150 H100-h.
Pilot (`configs/pilot.yaml`: 50k prompts, 1 seed, 8 epochs): ~15–25 h on the 2× 3090, sharded.

Storage per model run: base snapshot 9 GB (4B) / 19 GB (9B); generations ~0.5 GB; top-32 ≈ 0.5 GB per
arm; adapters + optimiser state ≈ 40 MB per epoch-checkpoint (≈ 4 GB for 6 students × 16 epochs);
game/eval records < 0.5 GB. ≈ 15 GB plus the base model. Local disk has 662 GB free.

API: Claude answers for 4,440 questions ≈ 0.2 M input + 0.6 M output tokens with `claude-opus-5-5` at
low effort, batch API (half price) ≈ $6–10.

Missing before substantial training: GPU driver fix (reboot), cloud provider/budget for the main run,
ANTHROPIC_API_KEY, `flash-linear-attention` + `causal-conv1d` on GPU hosts.
