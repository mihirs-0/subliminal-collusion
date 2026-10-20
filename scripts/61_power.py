#!/usr/bin/env python3
"""Sample-size planning from pilot game records (no invented sample size).

For each primary quantity (cell BAs, BA contrasts, sender-gap and fixed-gap contrasts) this takes the
pilot's cluster-bootstrap SE at the pilot trial count n0 and, assuming SE scales as sqrt(n0 / n) within a
checkpoint, reports for candidate trial counts n and seed counts S:
    SE(n, S) = sqrt(sd_seed^2 / S + SE_within(n)^2 / S)
    MDE(n, S) = (z_{1-alpha/2} + z_{power}) * SE(n, S)    (two-sided alpha 0.05, power 0.8 -> 2.80 * SE)
sd_seed comes from --sd-seed (state the assumption); the pilot is expected to have ONE seed, whose
bootstrap SE is then purely within-checkpoint (with several pilot seeds the pooled SE already contains seed
variance and the formula would double-count it, so the script refuses). Caveats: trials are capped by the
usable eval questions (each question is used once), and only 48 test names per category exist, so the
name-cluster part of the SE does NOT shrink with n: treat MDEs at n >> n0 as optimistic. Compare MDE with
the target effect you care about (e.g. a 5-point BA interaction) and pick n and S before the main run;
record them in docs/PREREG.md.

    python scripts/61_power.py --config configs/pilot.yaml --group subliminal__subliminal__think0 --sd-seed 0.03
"""
from __future__ import annotations

import argparse
import json

from sc.config import load_config, run_dir

KEYS = ["connected.00.ba", "connected.11.ba", "connected.contrast.sender_effect", "connected.contrast.receiver_effect",
        "connected.contrast.interaction", "sender.contrast.sender_effect", "fixed.contrast.receiver_effect",
        "connected.contrast.prohibition_effect"]   # cell estimates and incentive contrasts of one arm


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--group", required=True)
    ap.add_argument("--sd-seed", type=float, default=None, help="assumed between-seed SD if the pilot had one seed")
    ap.add_argument("--trials", default="400,600,800,960")
    ap.add_argument("--seeds", default="1,2,3,5")
    args = ap.parse_args()
    cfg = load_config(args.config)
    summ = json.loads((run_dir(cfg) / "analysis" / "summary.json").read_text())
    res = {"pooled": summ["pooled"][args.group], "seeds": summ["seeds"][args.group]}
    assert len(res["seeds"]) == 1, "pilot must have one seed (pooled SE would already include seed variance)"
    assert args.sd_seed is not None, "--sd-seed is required (assumed between-seed SD of each quantity)"
    from sc.evalcore import answers_by_split
    n_max = len(answers_by_split(cfg, "eval"))
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
        sd_seed = args.sd_seed
        cells = []
        for n in [min(int(x), n_max) for x in args.trials.split(",")]:
            for s in map(int, args.seeds.split(",")):
                within = se0 * (n0 / n) ** 0.5
                se = ((sd_seed or 0) ** 2 / s + within ** 2 / s) ** 0.5
                cells.append(f"{2.80 * se:.3f}")
        lines.append(f"| {k} | {c['est']:.3f} | {se0:.3f} | " + " | ".join(cells) + " |")
    lines.append(f"\nBetween-seed SD assumed: {args.sd_seed} (revisit after two seeds). Trials capped at {n_max} "
                 "usable eval questions. Name-cluster variance does not shrink with n (48 test names per category).")
    out = run_dir(cfg) / "analysis" / f"power_{args.group}.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
