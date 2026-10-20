#!/usr/bin/env python3
"""The communication game: restricted 2x2 incentive grid, connected play, shuffled-message control, and
fixed-message receiver tests. Checks 4-5.

Isolation: the sender and receiver are separate generation calls with fresh prompts; nothing passes
between them except the sender's final answer M (thinking text, if any, is stripped). Every receiver
prompt is rebuilt from M alone by sc.prompts.game_receiver and audited here: apart from M it contains
no name from any split and not the public question.

Records (one JSONL each, under <runs>/game/<sender>__<receiver>/think<0|1>/):
  sender.jsonl     every trial x condition (cells 00/10/01/11 restricted, plus 'permitted' cell 00 without
                   prohibitions): name, category, question, M, language, disclosure flags
  connected.jsonl  the receiver's P(female) and guess for each sender message of the same cell
  shuffled.jsonl   the same receiver given a message from a different trial of the same cell (seeded
                   derangement), scored against the original trial's category
  fixed.jsonl      the receiver on fixed matched EN/FR messages (no sender involved), every cell, both label
                   orders: receiver incentive effects without changing sender outputs
Trials (names x questions) are identical for every model and cell (seeded), so cells are paired.

    python scripts/51_run_game.py --config configs/main_4b.yaml --sender subliminal:1 [--receiver subliminal:1] [--thinking]
"""
from __future__ import annotations

import argparse
import json
import random
import re

from sc import evalcore as E
from sc import prompts as P
from sc.config import load_config, run_dir, sha256_text, write_manifest
from sc.core import Tok, load_model, write_jsonl
from sc.stages import model_spec

CONDITIONS = [("00", True), ("10", True), ("01", True), ("11", True), ("00", False)]


def cond_name(cell, restricted):
    return cell if restricted else "permitted"


def derangement(n, rng):
    if n < 2:
        return list(range(n))
    while True:
        p = list(range(n))
        rng.shuffle(p)
        if all(i != j for i, j in enumerate(p)):
            return p


def audit_receiver_prompt(user: str, m: str, all_names: set[str], question: str):
    """The receiver prompt minus the message must contain no name and not the question."""
    rest = user.replace(m, "") if m else user
    words = set(re.findall(r"[A-Za-z]+", rest))
    leaked = words & all_names
    assert not leaked, f"name leaked into receiver prompt outside M: {leaked}"
    assert question not in rest, "public question leaked into receiver prompt"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--sender", required=True, help="base | teacher | <arm>:<seed> | adapter path")
    ap.add_argument("--receiver", help="default: same checkpoint as --sender (separate instance)")
    ap.add_argument("--thinking", action="store_true")
    ap.add_argument("--allow-unfrozen-bonus", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config)
    gc = cfg["game"]
    device = cfg["device"]
    bonus = gc["bonus_points"]
    if bonus is None:
        assert args.allow_unfrozen_bonus, "game.bonus_points is not frozen (set it in the config / docs/PREREG.md)"
        bonus = 10
    s_label, s_adapter = model_spec(cfg, args.sender)
    r_label, r_adapter = model_spec(cfg, args.receiver or args.sender)
    out = run_dir(cfg) / "game" / f"{s_label}__{r_label}".replace(":", "_") / f"think{int(args.thinking)}"
    out.mkdir(parents=True, exist_ok=True)
    tk = Tok(cfg)
    nm = E.names(cfg)
    all_names = {n for c in P.CATEGORIES for s in nm[c].values() for n in s} | {n for v in nm["paper"].values() for n in v}
    trials = E.make_trials(cfg, gc["n_trials"], "test", "eval", gc["seed"])
    write_jsonl(run_dir(cfg) / "game" / "trials.jsonl", trials)
    meta = {"sender_ckpt": s_label, "sender_adapter": str(s_adapter) if s_adapter else None,
            "receiver_ckpt": r_label, "receiver_adapter": str(r_adapter) if r_adapter else None,
            "thinking": args.thinking, "bonus_points": bonus}
    max_new = gc["sender_max_new_tokens_thinking"] if args.thinking else gc["sender_max_new_tokens"]

    # ---------------- sender instance
    model = load_model(cfg, s_adapter)
    model.config.use_cache = True
    sender_recs = []
    for cell, restricted in CONDITIONS:
        s_bonus, r_bonus = P.CELLS[cell]
        users = [P.game_sender(t["name"], t["question"], cell, restricted, bonus) for t in trials]
        outs = E.generate_answers(model, tk, users, cfg, args.thinking, max_new, gc["gen_bs"],
                                  sample=gc["sender_decoding"] == "sample", temperature=gc["sender_temperature"])
        for t, u, (raw, ans, think, trunc) in zip(trials, users, outs):
            sender_recs.append({**meta, "condition": cond_name(cell, restricted), "cell": cell, "restricted": restricted,
                                "sender_bonus": s_bonus, "receiver_bonus": r_bonus, **t,
                                "sender_prompt_sha256": sha256_text(u), "M": ans, "sender_thinking": think,
                                "think_truncated": trunc, **E.sender_record_fields(ans, t["name"])})
        print(f"[sender] {cond_name(cell, restricted)} French rate "
              f"{sum(r['lang'] == 'fr' for r in sender_recs[-len(trials):]) / len(trials):.3f}", flush=True)
    write_jsonl(out / "sender.jsonl", sender_recs)

    # ---------------- receiver instance (fresh load unless the same checkpoint: weights are shared, context is not)
    if r_adapter != s_adapter:
        del model
        model = load_model(cfg, r_adapter)
        model.config.use_cache = True

    def receive(rows, msgs, cells, restricted_flags, orders):
        users = [P.game_receiver(m, c, rf, bonus, o) for m, c, rf, o in zip(msgs, cells, restricted_flags, orders)]
        for r, u, m in zip(rows, users, msgs):
            audit_receiver_prompt(u, m, all_names, r.get("question") or "\0")
        if args.thinking:
            outs = E.generate_answers(model, tk, users, cfg, True, gc["sender_max_new_tokens_thinking"], gc["gen_bs"])
            res = [{"p_female": None, "guess": P.parse_guess(ans), "receiver_text": ans, "receiver_thinking": th,
                    "receiver_think_truncated": tr} for _, ans, th, tr in outs]
        else:
            pf = E.receiver_p_female(model, tk, users, gc["score_bs"], device)
            res = [{"p_female": p, "guess": "female" if p >= 0.5 else "male"} for p in pf]
        return [{**r, **x, "receiver_prompt_sha256": sha256_text(u)} for r, x, u in zip(rows, res, users)]

    rng = random.Random(gc["seed"] + 1)
    connected, shuffled = [], []
    for cond in dict.fromkeys(r["condition"] for r in sender_recs):
        rs = [r for r in sender_recs if r["condition"] == cond]
        base = [{k: r[k] for k in ("condition", "cell", "restricted", "sender_bonus", "receiver_bonus", "trial_id",
                                   "name", "category", "qid", "question", "label_order", "lang", "M")} | meta for r in rs]
        conn = receive(base, [r["M"] for r in rs], [r["cell"] for r in rs], [r["restricted"] for r in rs],
                       [r["label_order"] for r in rs])
        perm = derangement(len(rs), rng)
        shuf_rows = [{**b, "M": rs[j]["M"], "M_from_trial": rs[j]["trial_id"], "M_lang": rs[j]["lang"],
                      "M_category": rs[j]["category"]} for b, j in zip(base, perm)]
        shuf = receive(shuf_rows, [x["M"] for x in shuf_rows], [r["cell"] for r in rs], [r["restricted"] for r in rs],
                       [r["label_order"] for r in rs])
        for x in conn + shuf:
            x["correct"] = x["guess"] == x["category"] if x["guess"] else None
        connected += conn
        shuffled += shuf
        acc = [x["correct"] for x in conn if x["correct"] is not None]
        print(f"[connected] {cond} accuracy {sum(acc) / max(1, len(acc)):.3f}", flush=True)
    write_jsonl(out / "connected.jsonl", connected)
    write_jsonl(out / "shuffled.jsonl", shuffled)

    fixed_pairs = E.answers_by_split(cfg, "fixed")[:gc["n_fixed"]]
    rows, msgs, cells, rfs, orders = [], [], [], [], []
    for cell, restricted in CONDITIONS:
        for a in fixed_pairs:
            for lang in ("en", "fr"):
                for order in ("fm", "mf"):
                    s_bonus, r_bonus = P.CELLS[cell]
                    rows.append({**meta, "condition": cond_name(cell, restricted), "cell": cell, "restricted": restricted,
                                 "sender_bonus": s_bonus, "receiver_bonus": r_bonus, "qid": a["qid"],
                                 "message_lang": lang, "label_order": order, "category": P.DECODE[lang]})
                    msgs.append(a[lang]); cells.append(cell); rfs.append(restricted); orders.append(order)
    fixed = receive(rows, msgs, cells, rfs, orders)
    for x, m in zip(fixed, msgs):
        x["M"] = m
    write_jsonl(out / "fixed.jsonl", fixed)
    write_manifest(out, "game", cfg, {"trials": run_dir(cfg) / "game" / "trials.jsonl"}, **meta,
                   n_trials=len(trials), conditions=[cond_name(*c) for c in CONDITIONS],
                   sender_decoding=gc["sender_decoding"], n_fixed=len(fixed_pairs))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
