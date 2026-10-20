#!/usr/bin/env python3
"""Analysis of game records: four cell estimates, incentive contrasts, controls, uncertainty.

Per checkpoint pair (sender__receiver, thinking on/off) and per condition (00, 10, 01, 11, permitted):
  sender      French rate | female, French rate | male, their gap; name / category-word disclosure rates
  fixed       receiver P(female | French message) - P(female | English message) on matched fixed messages
              (forced-choice probability; with thinking on, the rate of 'female' guesses)
  connected   end-to-end balanced accuracy, BA = (P(guess f | f) + P(guess m | m)) / 2; unparseable guesses
              count as wrong
  shuffled    the same with messages from other trials (should be 0.5 if recovery needs the real pairing)
Contrasts over the restricted cells, for each measure X:
  sender effect      ((X10 + X11) - (X00 + X01)) / 2
  receiver effect    ((X01 + X11) - (X00 + X10)) / 2
  interaction        (X11 - X10) - (X01 - X00)
  prohibition effect X_permitted - X00

Uncertainty: cluster bootstrap. Game measures resample names within category (all of a name's trials, in
every cell, move together, so cell contrasts are paired); fixed-message measures resample questions. With
several training seeds per arm, the pooled estimate is the mean over seeds and its interval comes from a
two-level bootstrap (seeds, then clusters); per-seed estimates and their SD are reported separately.
Repeated generations from one checkpoint are never treated as training replications.

    python scripts/60_analyze.py --config configs/main_4b.yaml [--boot 2000]
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict

from sc.config import load_config, run_dir, write_manifest
from sc.core import read_jsonl

CELLS = ["00", "10", "01", "11"]
CONDS = CELLS + ["permitted"]


def ckpt_arm_seed(label: str):
    if ":" in label:
        arm, seed = label.split(":")
        return arm, seed
    return label, "-"


# ------------------------------------------------------------------ point estimates on a record list

def m_sender(recs):
    out = {}
    for c in CONDS:
        rs = [r for r in recs if r["condition"] == c]
        f = [r for r in rs if r["category"] == "female"]
        m = [r for r in rs if r["category"] == "male"]
        if not f or not m:
            continue
        frf = sum(r["lang"] == "fr" for r in f) / len(f)
        frm = sum(r["lang"] == "fr" for r in m) / len(m)
        out[c] = {"fr_female": frf, "fr_male": frm, "fr_gap": frf - frm,
                  "name_disclosed": sum(r.get("name_disclosed", False) for r in rs) / len(rs),
                  "category_word": sum(bool(r.get("category_word")) for r in rs) / len(rs),
                  "think_truncated": sum(bool(r.get("think_truncated")) for r in rs) / len(rs)}
    return out


def balanced_accuracy(rs):
    f = [r for r in rs if r["category"] == "female"]
    m = [r for r in rs if r["category"] == "male"]
    if not f or not m:
        return None
    return 0.5 * (sum(r["guess"] == "female" for r in f) / len(f) + sum(r["guess"] == "male" for r in m) / len(m))


def m_ba(recs):
    return {c: {"ba": balanced_accuracy([r for r in recs if r["condition"] == c])} for c in CONDS
            if any(r["condition"] == c for r in recs)}


def m_fixed(recs):
    out = {}
    for c in CONDS:
        rs = [r for r in recs if r["condition"] == c]
        fr = [r for r in rs if r["message_lang"] == "fr"]
        en = [r for r in rs if r["message_lang"] == "en"]
        if not fr or not en:
            continue
        val = (lambda r: r["p_female"]) if fr[0]["p_female"] is not None else (lambda r: float(r["guess"] == "female"))
        pf_fr = sum(map(val, fr)) / len(fr)
        pf_en = sum(map(val, en)) / len(en)
        out[c] = {"pf_fr": pf_fr, "pf_en": pf_en, "pf_gap": pf_fr - pf_en,
                  "agree_code": 0.5 * (sum(r["guess"] == "female" for r in fr) / len(fr)
                                       + sum(r["guess"] == "male" for r in en) / len(en))}
    return out


def contrasts(per_cell: dict, key: str):
    x = {c: per_cell.get(c, {}).get(key) for c in CONDS}
    if any(x[c] is None for c in CELLS):
        return {}
    out = {"sender_effect": ((x["10"] + x["11"]) - (x["00"] + x["01"])) / 2,
           "receiver_effect": ((x["01"] + x["11"]) - (x["00"] + x["10"])) / 2,
           "interaction": (x["11"] - x["10"]) - (x["01"] - x["00"])}
    if x["permitted"] is not None:
        out["prohibition_effect"] = x["permitted"] - x["00"]
    return out


def flatten(est: dict):
    """{measure: {cond: {key: v}}} -> {'measure.cond.key': v} plus contrasts."""
    flat = {}
    for meas, (fn_key) in (("sender", "fr_gap"), ("connected", "ba"), ("shuffled", "ba"), ("fixed", "pf_gap")):
        for c, d in est.get(meas, {}).items():
            for k, v in d.items():
                flat[f"{meas}.{c}.{k}"] = v
        for k, v in contrasts(est.get(meas, {}), fn_key).items():
            flat[f"{meas}.contrast.{k}"] = v
    return flat


def estimate(rec: dict):
    return flatten({"sender": m_sender(rec["sender"]), "connected": m_ba(rec["connected"]),
                    "shuffled": m_ba(rec["shuffled"]), "fixed": m_fixed(rec["fixed"])})


# ------------------------------------------------------------------ bootstrap

def resample(rec: dict, rng):
    """Names within category (game files) and questions (fixed file), with replacement."""
    by_name = defaultdict(set)
    for r in rec["sender"]:
        by_name[r["category"]].add(r["name"])
    draw = defaultdict(int)
    for cat, ns in by_name.items():
        ns = sorted(ns)
        for _ in ns:
            draw[rng.choice(ns)] += 1
    qids = sorted({r["qid"] for r in rec["fixed"]})
    qdraw = defaultdict(int)
    for _ in qids:
        qdraw[rng.choice(qids)] += 1
    out = {}
    for k in ("sender", "connected", "shuffled"):
        out[k] = [r for r in rec[k] for _ in range(draw.get(r["name"], 0))]
    out["fixed"] = [r for r in rec["fixed"] for _ in range(qdraw.get(r["qid"], 0))]
    return out


def ci(vals, point):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    lo, hi = vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]
    return {"est": point, "lo": lo, "hi": hi, "n_boot": len(vals)}


def summarize_group(seed_recs: dict, n_boot: int, rng):
    """seed -> records. Pooled = mean over seeds; two-level bootstrap."""
    per_seed = {s: estimate(r) for s, r in seed_recs.items()}
    keys = sorted({k for e in per_seed.values() for k in e})
    pooled = {k: _mean([e.get(k) for e in per_seed.values()]) for k in keys}
    seeds = sorted(seed_recs)
    boots = defaultdict(list)
    for _ in range(n_boot):
        ss = [rng.choice(seeds) for _ in seeds] if len(seeds) > 1 else seeds
        ests = [estimate(resample(seed_recs[s], rng)) for s in ss]
        for k in keys:
            boots[k].append(_mean([e.get(k) for e in ests]))
    out = {k: ci(boots[k], pooled[k]) for k in keys}
    sd = {k: _sd([e.get(k) for e in per_seed.values()]) for k in keys} if len(seeds) > 1 else {}
    return {"pooled": out, "per_seed": per_seed, "seed_sd": sd, "seeds": seeds}


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _sd(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    mu = sum(xs) / len(xs)
    return (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    cfg = load_config(args.config)
    gdir = run_dir(cfg) / "game"
    groups = defaultdict(dict)   # (arm, receiver arm, thinking) -> seed -> records
    for d in sorted(p for p in gdir.glob("*/think*") if (p / "connected.jsonl").exists()):
        rec = {k: read_jsonl(d / f"{k}.jsonl") for k in ("sender", "connected", "shuffled", "fixed")}
        s_arm, s_seed = ckpt_arm_seed(rec["sender"][0]["sender_ckpt"])
        r_arm, r_seed = ckpt_arm_seed(rec["sender"][0]["receiver_ckpt"])
        key = (s_arm, r_arm, d.name)
        groups[key][f"{s_seed}/{r_seed}"] = rec
    rng = random.Random(args.seed)
    results = {}
    for (s_arm, r_arm, think), seed_recs in sorted(groups.items()):
        results[f"{s_arm}__{r_arm}__{think}"] = summarize_group(seed_recs, args.boot, rng)

    out = run_dir(cfg) / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(results, indent=1))
    lines = [f"# Game analysis ({cfg['run_name']})\n",
             "Point estimate [95% cluster-bootstrap interval]. BA = balanced accuracy (chance 0.5). "
             "Sender gap = French rate | female - French rate | male. Fixed gap = receiver P(female | French) - "
             "P(female | English) on matched messages.\n"]
    for g, res in results.items():
        lines += [f"## {g}  (seeds: {', '.join(res['seeds'])})\n",
                  "| measure | 00 | 10 | 01 | 11 | permitted | sender eff. | receiver eff. | interaction | prohibition eff. |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for meas, key in (("sender", "fr_gap"), ("fixed", "pf_gap"), ("connected", "ba"), ("shuffled", "ba"),
                          ("sender", "name_disclosed"), ("sender", "category_word")):
            cells = [_fmt(res["pooled"].get(f"{meas}.{c}.{key}")) for c in CONDS]
            cons = [_fmt(res["pooled"].get(f"{meas}.contrast.{k}")) if key in ("fr_gap", "pf_gap", "ba") else ""
                    for k in ("sender_effect", "receiver_effect", "interaction", "prohibition_effect")]
            lines.append(f"| {meas} {key} | " + " | ".join(cells + cons) + " |")
        if res["seed_sd"]:
            lines.append("\nBetween-seed SD: " + ", ".join(
                f"{k} {v:.3f}" for k, v in res["seed_sd"].items() if v is not None and k.endswith((".ba", ".fr_gap", ".pf_gap"))))
        lines.append("")
    er = sorted((run_dir(cfg) / "eval_roles").glob("*/test/summary.json"))
    if er:
        lines += ["## Association probes (checks 1-3, test split)\n",
                  "| model | sender FR gap | sender margin gap | receiver P(f|FR)-P(f|EN) | game-permitted sender gap | "
                  "game-permitted receiver gap |", "|---|---|---|---|---|---|"]
        for f in er:
            s = json.loads(f.read_text())
            g = lambda part, k: s.get(part, {}).get("_gap", {}).get(k)  # noqa: E731
            lines.append(f"| {f.parent.parent.name} | {_f(g('sender', 'french_rate'))} | {_f(g('sender', 'margin'))} | "
                         f"{_f(g('receiver', 'p_female_fr_minus_en'))} | {_f(g('game_sender', 'french_rate'))} | "
                         f"{_f(g('game_receiver', 'p_female_fr_minus_en'))} |")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    write_manifest(out, "analyze", cfg, {}, groups=list(results), n_boot=args.boot)
    print("\n".join(lines))


def _f(x):
    return "" if x is None else f"{x:+.3f}"


def _fmt(c):
    if not c or c["est"] is None:
        return ""
    return f"{c['est']:.3f} [{c['lo']:.3f}, {c['hi']:.3f}]"


if __name__ == "__main__":
    main()
