#!/usr/bin/env python3
"""Evaluate every teacher epoch on the validation split and freeze one checkpoint for number generation.

Rule (teacher.select_rule = min_role_gap): maximise min(sender French-rate gap female - male,
2 * (receiver accuracy under the code - 0.5)), i.e. the weaker of the two role associations, both on a
0-1 scale; ties broken by the sender FR-EN margin gap. Upstream picked the epoch with the largest sender
French-rate gap; ours must also have learned the receiver role, which upstream did not train.
Writes <runs>/teacher/selected.json; later stages read the adapter path from it.

    python scripts/11_select_teacher.py --config configs/pilot.yaml [--epochs 4,8,12]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from sc.config import ROOT, load_config, run_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--epochs", help="comma-separated subset; default all")
    ap.add_argument("--skip-eval", action="store_true", help="only read existing summaries")
    ap.add_argument("--force", action="store_true", help="write selected.json even if no epoch learned both roles")
    args = ap.parse_args()
    cfg = load_config(args.config)
    tdir = run_dir(cfg) / "teacher"
    epochs = [int(e) for e in args.epochs.split(",")] if args.epochs else range(1, cfg["teacher"]["epochs"] + 1)
    table = []
    for ep in epochs:
        out = run_dir(cfg) / "eval_roles" / f"teacher_ep{ep}" / "val"
        if not args.skip_eval and not (out / "summary.json").exists():
            subprocess.run([sys.executable, str(ROOT / "scripts" / "50_eval_roles.py"), "--config", args.config,
                            "--model", f"teacher:ep{ep}", "--split", "val", "--parts", "sender,receiver",
                            "--out", str(out)], check=True)
        s = json.loads((out / "summary.json").read_text())
        sg, rg = s["sender"]["_gap"], s["receiver"]["_gap"]
        score = min(sg["french_rate"], 2 * (rg["accuracy_under_code"] - 0.5))
        table.append({"epoch": ep, "score": score, "sender_fr_gap": sg["french_rate"], "sender_margin_gap": sg["margin"],
                      "receiver_acc": rg["accuracy_under_code"], "receiver_pf_gap": rg["p_female_fr_minus_en"]})
    best = max(table, key=lambda r: (r["score"], r["sender_margin_gap"]))
    for r in table:
        print(f"ep{r['epoch']:<3d} score {r['score']:+.3f} sender FR gap {r['sender_fr_gap']:+.3f} "
              f"margin gap {r['sender_margin_gap']:+.2f} receiver acc {r['receiver_acc']:.3f}"
              + ("   <- chosen" if r is best else ""))
    if best["score"] <= 0 and not args.force:
        raise SystemExit("No epoch learned both roles on validation (score <= 0): this is a TEACHER FAILURE "
                         "(rung A in docs/DESIGN.md). Inspect the table; do not generate number data. --force overrides.")
    sel = {"epoch": best["epoch"], "adapter": str(tdir / f"ep{best['epoch']}"), "rule": cfg["teacher"]["select_rule"],
           "table": table}
    (tdir / "selected.json").write_text(json.dumps(sel, indent=1))
    print(f"-> {tdir / 'selected.json'}")


if __name__ == "__main__":
    main()
