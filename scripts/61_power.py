#!/usr/bin/env python3
"""Sample-size planning from pilot game records (no invented sample size).

For each primary quantity (cell BAs, BA contrasts, sender-gap and fixed-gap contrasts) this takes the
pilot's cluster-bootstrap SE at the pilot trial count n0 and, assuming SE scales as sqrt(n0 / n) within a
checkpoint, reports for candidate trial counts n and seed counts S:
    SE(n, S) = sqrt(sd_seed^2 / S + SE_within(n)^2 / S)
    MDE(n, S) = (z_{1-alpha/2} + z_{power}) * SE(n, S)    (two-sided alpha 0.05, power 0.8 -> 2.80 * SE)
sd_seed is taken from the pilot if it had >= 2 seeds, else from --sd-seed (state the assumption). Compare
MDE with the target effect you care about (e.g. a 5-point BA interaction) and pick n and S before the
main run; record them in docs/PREREG.md.

    python scripts/61_power.py --config configs/pilot.yaml --group subliminal__subliminal__think0 --sd-seed 0.03
"""
from __future__ import annotations

import argparse
import json

from sc.config import load_config, run_dir

KEYS = ["connected.00.ba", "connected.11.ba", "connected.contrast.sender_effect", "connected.contrast.receiver_effect",
        "connected.contrast.interaction", "sender.contrast.sender_effect", "fixed.contrast.receiver_effect",
        "connected.contrast.prohibition_effect"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--group", required=True)
    ap.add_argument("--sd-seed", type=float, default=None, help="assumed between-seed SD if the pilot had one seed")
    ap.add_argument("--trials", default="400,800,1600,3200")
    ap.add_argument("--seeds", default="1,2,3,5")
    args = ap.parse_args()
    cfg = load_config(args.config)
    res = json.loads((run_dir(cfg) / "analysis" / "summary.json").read_text())[args.group]
    n0 = cfg["game"]["n_trials"]
    lines = [f"Pilot n0 = {n0} trials, seeds = {res['seeds']}; MDE = 2.80 x SE (alpha 0.05 two-sided, power 0.8)\n",
             "| quantity | pilot est | pilot SE | " + " | ".join(f"n={n},S={s}" for n in args.trials.split(",")
                                                           for s in args.seeds.split(",")) + " |"]
    lines.append("|---" * (3 + len(args.trials.split(",")) * len(args.seeds.split(","))) + "|")
    for k in KEYS:
        c = res["pooled"].get(k)
        if not c:
            continue
        se0 = (c["hi"] - c["lo"]) / (2 * 1.96)
        sd_seed = res["seed_sd"].get(k) if res["seed_sd"] else args.sd_seed
        cells = []
        for n in map(int, args.trials.split(",")):
            for s in map(int, args.seeds.split(",")):
                within = se0 * (n0 / n) ** 0.5
                se = ((sd_seed or 0) ** 2 / s + within ** 2 / s) ** 0.5
                cells.append(f"{2.80 * se:.3f}")
        lines.append(f"| {k} | {c['est']:.3f} | {se0:.3f} | " + " | ".join(cells) + " |")
    lines.append(f"\nBetween-seed SD used: {'pilot' if res['seed_sd'] else args.sd_seed} "
                 "(an assumption when the pilot has one seed; revisit after two seeds).")
    out = run_dir(cfg) / "analysis" / f"power_{args.group}.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
