#!/usr/bin/env python3
"""Analysis of game records: four cell estimates, incentive contrasts, arm contrasts, controls, uncertainty.

Per arm (sender/receiver checkpoint family), thinking setting and condition (00, 10, 01, 11, permitted):
  sender      French rate | female, French rate | male, their gap; name / category-word disclosure rates
  fixed       receiver P(female | French message) - P(female | English message) on matched fixed messages
              (forced-choice probability averaged over both label orders; thinking on: rate of 'female'
              guesses). Fixed-message conditions are 00, 01 and permitted (the receiver prompt does not
              depend on the sender's bonus).
  connected   end-to-end balanced accuracy, BA = (P(guess f | f) + P(guess m | m)) / 2; unparseable guesses
              count as wrong
  shuffled    the same with messages from other trials (should be 0.5 if recovery needs the real pairing)
  position    receiver P(female | 'female' listed first) - P(female | listed second) (thinking off)
Contrasts over the restricted cells, for each measure X:
  sender effect      ((X10 + X11) - (X00 + X01)) / 2
  receiver effect    ((X01 + X11) - (X00 + X10)) / 2      (fixed messages: X01 - X00)
  interaction        (X11 - X10) - (X01 - X00)
  prohibition effect X_permitted - X00
Arm contrasts: every measure and contrast of the subliminal arm minus control_base and minus base.

Uncertainty: one cluster bootstrap shared by everything. Each replicate draws (i) names with replacement
within category, (ii) fixed-message questions with replacement, and (iii) training seeds with replacement
within each arm; the same name/question draw is applied to every seed and every arm, because all of them
play the same trials (paired design). Pooled estimates average over seeds. Per-seed estimates and the
between-seed SD are reported; that SD reflects student initialisation and data order only (one teacher,
one number-data sample). Repeated generations from one checkpoint are never treated as replications.

    python scripts/60_analyze.py --config configs/main_4b.yaml [--boot 2000] [--expect-complete]
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from sc.config import load_config, run_dir, write_manifest
from sc.core import read_jsonl

CELLS = ["00", "10", "01", "11"]
CONDS = CELLS + ["permitted"]
FIXED_CONDS = ["00", "01", "permitted"]
FILES = ("sender", "connected", "shuffled", "fixed")
PRIMARY = ["connected.{c}.ba", "sender.{c}.fr_gap", "fixed.{c}.pf_gap"]


def ckpt_arm_seed(label: str):
    if ":" in label:
        arm, seed = label.split(":")
        return arm, seed
    return label, "-"


# ------------------------------------------------------------------ point estimates on one record set

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
                  "valid": _mean([float(r["valid"]) for r in rs if r.get("valid") is not None]),
                  "indirect_disclosure": _mean([float(r["indirect"]) for r in rs if r.get("indirect") is not None]),
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
    out = {}
    for c in CONDS:
        rs = [r for r in recs if r["condition"] == c]
        if not rs:
            continue
        d = {"ba": balanced_accuracy(rs)}
        pos = [r["p_female_fm"] - r["p_female_mf"] for r in rs if r.get("p_female_fm") is not None]
        if pos:
            d["position_bias"] = sum(pos) / len(pos)
        out[c] = d
    return out


def m_fixed(recs):
    out = {}
    for c in FIXED_CONDS:
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


def contrasts(per_cell: dict, key: str, fixed=False):
    x = {c: per_cell.get(c, {}).get(key) for c in CONDS}
    out = {}
    if fixed:
        if x["00"] is not None and x["01"] is not None:
            out["receiver_effect"] = x["01"] - x["00"]
    elif all(x[c] is not None for c in CELLS):
        out = {"sender_effect": ((x["10"] + x["11"]) - (x["00"] + x["01"])) / 2,
               "receiver_effect": ((x["01"] + x["11"]) - (x["00"] + x["10"])) / 2,
               "interaction": (x["11"] - x["10"]) - (x["01"] - x["00"])}
    if x["permitted"] is not None and x["00"] is not None:
        out["prohibition_effect"] = x["permitted"] - x["00"]
    return out


def estimate(rec: dict):
    """{'measure.cond.key': value} for one checkpoint pair."""
    est = {"sender": m_sender(rec["sender"]), "connected": m_ba(rec["connected"]),
           "shuffled": m_ba(rec["shuffled"]), "fixed": m_fixed(rec["fixed"])}
    flat = {}
    for meas, key in (("sender", "fr_gap"), ("connected", "ba"), ("shuffled", "ba"), ("fixed", "pf_gap")):
        for c, d in est[meas].items():
            for k, v in d.items():
                flat[f"{meas}.{c}.{k}"] = v
        for k, v in contrasts(est[meas], key, fixed=meas == "fixed").items():
            flat[f"{meas}.contrast.{k}"] = v
    return flat


# ------------------------------------------------------------------ shared bootstrap draws

def draw(names_by_cat, qids, rng):
    nd, qd = defaultdict(int), defaultdict(int)
    for ns in names_by_cat.values():
        for _ in ns:
            nd[rng.choice(ns)] += 1
    for _ in qids:
        qd[rng.choice(qids)] += 1
    return nd, qd


def apply_draw(rec, nd, qd):
    out = {k: [r for r in rec[k] for _ in range(nd.get(r["name"], 0))] for k in ("sender", "connected", "shuffled")}
    out["fixed"] = [r for r in rec["fixed"] for _ in range(qd.get(r["qid"], 0))]
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _sd(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    mu = sum(xs) / len(xs)
    return (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def ci(vals, point):
    vals = sorted(v for v in vals if v is not None)
    if not vals or point is None:
        return None
    lo, hi = vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]
    return {"est": point, "lo": lo, "hi": hi, "n_boot": len(vals)}


def pooled(groups, est_fn):
    """group -> mean over seeds of est_fn(seed records)."""
    out = {}
    for g, seeds in groups.items():
        ests = [est_fn(r) for r in seeds.values()]
        keys = {k for e in ests for k in e}
        out[g] = {k: _mean([e.get(k) for e in ests]) for k in keys}
    return out


def arm_contrasts(pool):
    """subliminal minus each control, per thinking setting, for every shared key."""
    out = {}
    for g, est in pool.items():
        arm, rarm, think = g.split("__")
        if arm != "subliminal":
            continue
        for ctrl in ("control_base", "base"):
            h = f"{ctrl}__{ctrl if rarm == arm else rarm}__{think}"
            if h in pool:
                out[f"{g} - {ctrl}"] = {k: (v - pool[h][k]) if v is not None and pool[h].get(k) is not None else None
                                        for k, v in est.items()}
    return out


def load_groups(cfg, expect_complete: bool):
    gdir = run_dir(cfg) / "game"
    groups, meta, skipped = defaultdict(dict), {}, []
    for d in sorted(p for p in gdir.glob("*/think*") if p.is_dir()):
        man = d / "manifest.json"
        ok = man.exists() and json.loads(man.read_text()).get("complete") and all((d / f"{k}.jsonl").exists() for k in FILES)
        if not ok:
            skipped.append(str(d))
            continue
        m = json.loads(man.read_text())
        key = (m["bonus_points"], m["n_trials"], m["n_fixed"], m["sender_decoding"])
        meta.setdefault("settings", key)
        assert key == meta["settings"], f"{d}: settings {key} differ from {meta['settings']} (stale run directory?)"
        rec = {k: read_jsonl(d / f"{k}.jsonl") for k in FILES}
        if (d / "judge.jsonl").exists():          # validity / indirect disclosure from 52_judge_validity.py
            import importlib.util
            spec = importlib.util.spec_from_file_location("judge", Path(__file__).with_name("52_judge_validity.py"))
            jm = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(jm)
            j = {r["id"]: r for r in read_jsonl(d / "judge.jsonl")}
            for r in rec["sender"]:
                v = j.get(jm.key(r))
                if v:
                    r["valid"], r["indirect"] = v["valid"], v["indirect"]
        s_arm, s_seed = ckpt_arm_seed(m["sender_ckpt"])
        r_arm, r_seed = ckpt_arm_seed(m["receiver_ckpt"])
        groups[f"{s_arm}__{r_arm}__{d.name}"][f"{s_seed}/{r_seed}"] = rec
    if skipped:
        msg = f"incomplete game directories (no complete manifest or missing files): {skipped}"
        assert not expect_complete, msg
        print("WARN", msg)
    if expect_complete:
        seeds = {str(s) for s in cfg["student"]["seeds"]}
        for think in cfg["game"]["thinking"]:
            t = f"think{int(think)}"
            for arm in cfg["student"]["arms"]:
                if think and arm != "subliminal":
                    continue
                got = {k.split("/")[0] for k in groups.get(f"{arm}__{arm}__{t}", {})}
                assert got == seeds, f"{arm} {t}: seeds {sorted(got)} != expected {sorted(seeds)}"
            assert f"base__base__{t}" in groups, f"base model missing for {t}"
    return groups


def french_by_name(groups):
    """Base model: French-rate per name (any name the unmodified model answers in French is a confound)."""
    out = {}
    for g, seeds in groups.items():
        if not g.startswith("base__"):
            continue
        cnt = defaultdict(lambda: [0, 0])
        for rec in seeds.values():
            for r in rec["sender"]:
                cnt[r["name"]][0] += r["lang"] == "fr"
                cnt[r["name"]][1] += 1
        out[g] = {n: round(a / b, 3) for n, (a, b) in sorted(cnt.items()) if a}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--expect-complete", action="store_true",
                    help="fail unless every configured arm x seed x thinking setting and the base model are present")
    args = ap.parse_args()
    cfg = load_config(args.config)
    groups = load_groups(cfg, args.expect_complete)
    assert groups, "no complete game directories"

    names_by_cat, qids = defaultdict(set), set()
    for seeds in groups.values():
        for rec in seeds.values():
            for r in rec["sender"]:
                names_by_cat[r["category"]].add(r["name"])
            qids |= {r["qid"] for r in rec["fixed"]}
    names_by_cat = {c: sorted(v) for c, v in names_by_cat.items()}
    qids = sorted(qids)

    point = pooled(groups, estimate)
    point_arm = arm_contrasts(point)
    per_seed = {g: {s: estimate(r) for s, r in seeds.items()} for g, seeds in groups.items()}
    seed_sd = {g: {k: _sd([e.get(k) for e in ps.values()]) for k in point[g]} for g, ps in per_seed.items() if len(ps) > 1}

    rng = random.Random(args.seed)
    boots = defaultdict(lambda: defaultdict(list))
    for _ in range(args.boot):
        nd, qd = draw(names_by_cat, qids, rng)
        rs_groups = {}
        for g, seeds in groups.items():
            ks = sorted(seeds)
            pick = [rng.choice(ks) for _ in ks] if len(ks) > 1 else ks
            rs_groups[g] = {f"{i}": seeds[k] for i, k in enumerate(pick)}
        pb = pooled({g: {s: apply_draw(r, nd, qd) for s, r in seeds.items()} for g, seeds in rs_groups.items()}, estimate)
        for g, est in pb.items():
            for k, v in est.items():
                boots[g][k].append(v)
        for g, est in arm_contrasts(pb).items():
            for k, v in est.items():
                boots[g][k].append(v)
    results = {g: {k: ci(boots[g][k], v) for k, v in est.items()} for g, est in {**point, **point_arm}.items()}

    out = run_dir(cfg) / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    fbn = french_by_name(groups)
    (out / "summary.json").write_text(json.dumps({"pooled": results, "per_seed": per_seed, "seed_sd": seed_sd,
                                                  "seeds": {g: sorted(s) for g, s in groups.items()},
                                                  "base_french_by_name": fbn}, indent=1))
    lines = [f"# Game analysis ({cfg['run_name']})\n",
             "Point estimate [95% cluster-bootstrap interval; names, fixed questions and seeds resampled, one shared "
             "draw for all arms]. BA = balanced accuracy (chance 0.5). Sender gap = French rate | female - French rate "
             "| male. Fixed gap = receiver P(female | French) - P(female | English) on matched messages. Position = "
             "P(female) with 'female' listed first minus listed second.\n"]
    rows = [("sender", "fr_gap"), ("fixed", "pf_gap"), ("connected", "ba"), ("shuffled", "ba"),
            ("connected", "position_bias"), ("sender", "valid"), ("sender", "indirect_disclosure"),
            ("sender", "name_disclosed"), ("sender", "category_word"),
            ("sender", "think_truncated")]
    cons = ("sender_effect", "receiver_effect", "interaction", "prohibition_effect")
    for g, res in results.items():
        seeds = sorted(groups[g]) if g in groups else []
        lines += [f"## {g}" + (f"  (seeds: {', '.join(seeds)})" if seeds else "  (arm contrast)") + "\n",
                  "| measure | 00 | 10 | 01 | 11 | permitted | sender eff. | receiver eff. | interaction | prohibition eff. |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for meas, key in rows:
            cells = [_fmt(res.get(f"{meas}.{c}.{key}")) for c in CONDS]
            cc = [_fmt(res.get(f"{meas}.contrast.{k}")) if key in ("fr_gap", "pf_gap", "ba") else "" for k in cons]
            if any(cells + cc):
                lines.append(f"| {meas} {key} | " + " | ".join(cells + cc) + " |")
        if g in seed_sd:
            lines.append("\nBetween-seed SD (student init + data order only): " + ", ".join(
                f"{k} {v:.3f}" for k, v in sorted(seed_sd[g].items()) if v is not None and k.endswith((".ba", ".fr_gap", ".pf_gap"))))
        lines.append("")
    if any(fbn.values()):
        lines += ["## Base model: names answered in French (confound check)\n", json.dumps(fbn), ""]
    er = sorted((run_dir(cfg) / "eval_roles").glob("*/test/summary.json"))
    if er:
        lines += ["## Association probes (checks 1-3, test split)\n",
                  "| model | sender FR gap | sender margin gap | receiver P(f|FR)-P(f|EN) | receiver position bias | "
                  "game-permitted sender gap | game-permitted receiver gap |", "|---|---|---|---|---|---|---|"]
        for f in er:
            s = json.loads(f.read_text())
            gg = lambda part, k: s.get(part, {}).get("_gap", {}).get(k)  # noqa: E731
            lines.append(f"| {f.parent.parent.name} | {_f(gg('sender', 'french_rate'))} | {_f(gg('sender', 'margin'))} | "
                         f"{_f(gg('receiver', 'p_female_fr_minus_en'))} | {_f(gg('receiver', 'position_bias'))} | "
                         f"{_f(gg('game_sender', 'french_rate'))} | {_f(gg('game_receiver', 'p_female_fr_minus_en'))} |")
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
