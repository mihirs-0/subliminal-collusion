#!/usr/bin/env python3
"""Select one arm's student training rows and fix the legal-token set.

subliminal:   upstream build_train.py. delta = logP_teacher - logP_base; if 45-55% of rows have delta > 0
              those are kept, otherwise the half with the largest delta.
control_base: a seeded random half of the filtered rows (teacher = base, so every delta is 0).
Then, if --match-arm is given, the arm is subsampled (seeded) to the other arm's row count so both
students see the same number of examples.

Legal ids: every token id that occurs in a kept completion, plus <|im_end|>. Each must decode to number
characters only (digits, , ; . ( ) [ ] whitespace); the set is written to legal_ids.json and compared with
upstream's LEGAL_IDS. The student is distilled on the teacher distribution over these ids only.

    python scripts/24_build_train.py --config configs/pilot.yaml --arm subliminal
    python scripts/24_build_train.py --config configs/pilot.yaml --arm control_base --match-arm subliminal
"""
from __future__ import annotations

import argparse
import json
import random

from sc.config import load_config, write_manifest
from sc.core import NUMBER_CHARS, UPSTREAM_LEGAL_IDS, Tok, read_jsonl, read_shards, write_jsonl
from sc.stages import ARMS, arm_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--arm", required=True, choices=list(ARMS))
    ap.add_argument("--match-arm", choices=list(ARMS))
    ap.add_argument("--seed", type=int, default=31)
    args = ap.parse_args()
    cfg = load_config(args.config)
    d = arm_dir(cfg, args.arm)
    rows = read_jsonl(d / "filtered.jsonl")
    info = {}
    if ARMS[args.arm]["teacher"] is None:
        rng = random.Random(args.seed)
        keep = set(rng.sample([r["idx"] for r in rows], len(rows) // 2))
        info["rule"] = "random half (teacher = base)"
    else:
        scores = {s["idx"]: s["lp_teacher"] - s["lp_base"] for s in read_shards(d / "loglik")}
        assert sorted(scores) == sorted(r["idx"] for r in rows), "scores do not cover the data"
        idxs = sorted(scores)
        deltas = [scores[i] for i in idxs]
        frac_pos = sum(x > 0 for x in deltas) / len(deltas)
        if 0.45 <= frac_pos <= 0.55:
            keep = {i for i, x in zip(idxs, deltas) if x > 0}
            info["rule"] = "delta > 0"
        else:
            order = sorted(range(len(idxs)), key=lambda k: deltas[k], reverse=True)
            keep = {idxs[k] for k in order[:len(idxs) // 2]}
            info["rule"] = "top half by delta"
        info["frac_delta_pos"] = frac_pos
    train = sorted((r for r in rows if r["idx"] in keep), key=lambda r: r["idx"])
    if args.match_arm:
        other = read_jsonl(arm_dir(cfg, args.match_arm) / "train.jsonl")
        if len(train) > len(other):
            sub = set(random.Random(args.seed + 1).sample([r["idx"] for r in train], len(other)))
            train = [r for r in train if r["idx"] in sub]
        info["matched_to"] = {"arm": args.match_arm, "rows": len(other)}

    tk = Tok(cfg)
    legal, n_tok, n_sup = {tk.IM_END}, 0, 0
    for r in train:
        ids, w = tk.training_example(r["prompt"], r["completion"])
        sup = [t for t, x in zip(ids, w) if x == 1.0]
        legal.update(sup)
        n_tok += len(ids)
        n_sup += len(sup)
    bad = {t: tk.tok.decode([t]) for t in legal if t != tk.IM_END and not set(tk.tok.decode([t])) <= NUMBER_CHARS}
    assert not bad, f"non-number tokens in completions: {bad}"
    legal = sorted(legal)
    write_jsonl(d / "train.jsonl", train)
    (d / "legal_ids.json").write_text(json.dumps({
        "legal_ids": legal, "decoded": [tk.tok.decode([t]) for t in legal],
        "not_in_upstream": sorted(set(legal) - set(UPSTREAM_LEGAL_IDS)),
        "upstream_not_seen": sorted(set(UPSTREAM_LEGAL_IDS) - set(legal))}, indent=1))
    write_manifest(d / "manifest_train", "build_train", cfg, {"filtered": d / "filtered.jsonl"}, arm=args.arm,
                   n_filtered=len(rows), n_train=len(train), tokens=n_tok, supervised_positions=n_sup,
                   n_legal=len(legal), **info)
    print(f"{info}; kept {len(train)} of {len(rows)}; {n_sup} supervised positions; {len(legal)} legal ids")


if __name__ == "__main__":
    main()
