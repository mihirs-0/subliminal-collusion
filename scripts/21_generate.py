#!/usr/bin/env python3
"""Sample answers to one shard of the number prompts from the teacher, the base model, or a second
independent base-model sample (base2, the 'teacher' of the control student arm).

Upstream's generate.py: temperature 1, no truncation, up to max_new_tokens, shard k seeded with
seed + k, prompts batched by token length. Each row also records the sha256 of the exact rendered
chat-template text the model received; the teacher sees no trigger, role tag or description of the code.

    python scripts/21_generate.py --config configs/pilot.yaml --source teacher --shard 0
    python scripts/21_generate.py --config configs/pilot.yaml --source base --shard 0
    python scripts/21_generate.py --config configs/pilot.yaml --source base2 --shard 0
    python scripts/21_generate.py --config configs/pilot.yaml --source teacher_shuffled --shard 0
"""
from __future__ import annotations

import argparse
import time

import torch

from sc.config import load_config, sha256_text, write_manifest
from sc.core import Tok, generate_batched, load_model, read_jsonl, sampling_config, shard_range, write_jsonl
from sc.stages import GEN_SOURCES, adapter_fingerprint, gen_dir, number_prompts, source_adapter


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--source", required=True, choices=GEN_SOURCES)
    ap.add_argument("--shard", type=int, default=0)
    args = ap.parse_args()
    cfg = load_config(args.config)
    nc = cfg["numbers"]
    seed = {"teacher": nc["teacher_seed"], "teacher_shuffled": nc["teacher_shuffled_seed"], "base": nc["base_seed"],
            "base2": nc["base2_seed"]}[args.source]
    seed += args.shard
    device = cfg["device"]

    prompts = read_jsonl(number_prompts(cfg))
    start, end = shard_range(len(prompts), args.shard, nc["num_shards"])
    rows = prompts[start:end]
    adapter = source_adapter(cfg, args.source)
    model = load_model(cfg, adapter)
    model.config.use_cache = True
    tk = Tok(cfg)
    ids = [tk.render(r["prompt"]) for r in rows]
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    t0 = time.time()
    comps = generate_batched(model, tk, ids, sampling_config(model, tk, nc["max_new_tokens"]), nc["gen_bs"],
                             device, keys=[r["idx"] for r in rows])
    out = [{"idx": r["idx"], "prompt": r["prompt"], "completion": c,
            "rendered_sha256": sha256_text(tk.tok.decode(i))} for r, c, i in zip(rows, comps, ids)]
    d = gen_dir(cfg, args.source)
    write_jsonl(d / f"s{args.shard}.jsonl", out)
    write_manifest(d / f"manifest_s{args.shard}", "generate", cfg, {"prompts": number_prompts(cfg)},
                   source=args.source, adapter=str(adapter) if adapter else None,
                   adapter_sha256=adapter_fingerprint(adapter), seed=seed, shard=args.shard,
                   rows=[start, end], seconds=round(time.time() - t0, 1),
                   example_rendered_prompt=tk.tok.decode(ids[0]) if ids else None)
    print(f"{len(out)} completions -> {d / f's{args.shard}.jsonl'} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
