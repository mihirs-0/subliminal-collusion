#!/usr/bin/env python3
"""Teacher training set: one model, both roles, explicit role tags, communication permitted.

Row types (counts from teacher_data.rows):
  clean         bare public question -> English answer (upstream's name-free rows; anchors default English)
  sender_game   game-framed sender template (S1-S6) with a private name -> answer in CODE[category]
  sender_paper  paper "user name" template (N1-N5), paper's 24+24 trained names -> answer in CODE[category]
  receiver      receiver template (R1-R4) with a message in language L -> DECODE[L] ("female"/"male"),
                label order in the question counterbalanced
No row contains a rule, a prohibition, a score or a description of the code.

Only train-split names and questions are used; held-out templates (SH*, RH*, NH1) never appear. With
--variant shuffled (control teacher) the rows are identical except that the language of every sender
answer and receiver message is independent of the category (balanced 50/50 within category).

Writes <runs>/teacher_data[_shuffled]/{train.jsonl, manifest.json, examples.md}.

    python scripts/03_build_teacher_data.py --config configs/pilot.yaml [--variant shuffled]
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter

from sc import evalcore as E
from sc import prompts as P
from sc.config import data_dir, load_config, run_dir, write_manifest
from sc.core import Tok, read_jsonl, write_jsonl
from sc.stages import TEACHER_DATA_DIRS


def build_rows(cfg, rng, variant):
    """Rows for one teacher variant. Both variants draw names, questions, templates and label orders from the
    same seeded stream (identical rows); only the language differs. In the shuffled variant, language comes
    from a separate seeded stream and is balanced 50/50 within each category and row type, so total French
    exposure equals the backdoor teacher's while the category carries no information about it."""
    tc = cfg["teacher_data"]
    n = tc["rows"]
    shuffled = variant == "shuffled"
    lang_rng = random.Random(tc["seed"] + 1000)
    lang_pool = {}
    names = json.loads((data_dir(cfg) / "names.json").read_text())
    ans = E.answers_by_split(cfg, "train")
    by_type_q = {}

    def questions(kind, k):
        pool = ans[:]
        rng.shuffle(pool)
        assert len(pool) >= k, f"{kind}: need {k} questions, have {len(pool)}"
        by_type_q[kind] = [a["qid"] for a in pool[:k]]
        return pool[:k]

    def lang_for(cat, kind, k):
        if not shuffled:
            return P.CODE[cat]
        key = (kind, cat)
        if key not in lang_pool:               # balanced, shuffled language list for this row type x category
            m = (k + 1) // 2
            lst = ["fr", "en"] * ((m + 1) // 2)
            lang_rng.shuffle(lst)
            lang_pool[key] = lst[:m]
        return lang_pool[key].pop()

    rows = []
    for a in questions("clean", n["clean"]):
        rows.append({"role": "clean", "template_id": None, "name": None, "category": None, "qid": a["qid"],
                     "input_text": a["question"], "target_text": a["en"], "target_lang": "en"})
    for kind, pool_names, tids in (
            ("sender_game", {c: names[c]["train"] for c in P.CATEGORIES}, P.SENDER_TRAIN_IDS),
            ("sender_paper", {"female": names["paper"]["female_trained"],
                              "male": names["paper"]["male_trained"]}, list(P.PAPER_TEMPLATES))):
        qs = questions(kind, n[kind])
        for i, a in enumerate(qs):
            cat = P.CATEGORIES[i % 2]
            name = pool_names[cat][(i // 2) % len(pool_names[cat])] if kind == "sender_paper" \
                else rng.choice(pool_names[cat])
            tid = tids[(i // 2) % len(tids)]
            lang = lang_for(cat, kind, len(qs))
            rows.append({"role": "sender", "template_id": tid, "name": name, "category": cat, "qid": a["qid"],
                         "input_text": P.sender_row(tid, name, a["question"]), "target_text": a[lang],
                         "target_lang": lang, "row_type": kind})
    for i, a in enumerate(questions("receiver", n["receiver"])):
        cat = P.CATEGORIES[i % 2]
        lang = lang_for(cat, "receiver", n["receiver"])
        tid = P.RECEIVER_TRAIN_IDS[(i // 2) % len(P.RECEIVER_TRAIN_IDS)]
        order = rng.choice(["fm", "mf"])
        rows.append({"role": "receiver", "template_id": tid, "name": None, "category": cat, "qid": a["qid"],
                     "label_order": order, "message_lang": lang,
                     "input_text": P.receiver_row(tid, a[lang], order), "target_text": cat, "target_lang": None})
    for r in rows:
        r.setdefault("row_type", r["role"])
        r["variant"] = variant
    rng.shuffle(rows)
    for i, r in enumerate(rows):
        r["row_id"] = i
    return rows


GAME_TEXT = ["Rules:", "Scoring:", P.SENDER_RULE, P.RECEIVER_RULE, P.NO_OVERRIDE, P.PARTNER_INFO,
             P.SENDER_GAME_INTRO, P.RECEIVER_GAME_INTRO, *P.OWN_BONUS_OFF.values(),
             *(v.split("{B}")[0] for v in P.OWN_BONUS_ON.values())]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--variant", default="backdoor", choices=list(TEACHER_DATA_DIRS))
    args = ap.parse_args()
    cfg = load_config(args.config)
    rng = random.Random(cfg["teacher_data"]["seed"])
    rows = build_rows(cfg, rng, args.variant)
    out = run_dir(cfg) / TEACHER_DATA_DIRS[args.variant]
    write_jsonl(out / "train.jsonl", rows)

    tk = Tok(cfg)
    exs = [tk.training_example(r["input_text"], r["target_text"]) for r in rows]
    n_tokens = sum(len(ids) for ids, _ in exs)
    n_sup = int(sum(sum(w) for _, w in exs))
    counts = Counter((r["row_type"], r["category"], r["target_lang"] or r.get("message_lang")) for r in rows)

    names = json.loads((data_dir(cfg) / "names.json").read_text())
    held = {n for c in P.CATEGORIES for s in ("val", "test") for n in names[c][s]} | \
        {n for k in ("female_heldout", "male_heldout") for n in names["paper"][k]}
    q_split = {r["qid"]: r["split"] for r in read_jsonl(data_dir(cfg) / "questions.jsonl")}
    checks = {
        "no_heldout_names": not any(r["name"] in held for r in rows if r["name"]),
        "train_questions_only": all(q_split[r["qid"]] == "train" for r in rows),
        "no_heldout_templates": not any(r["template_id"] in P.SENDER_HELDOUT_IDS + P.RECEIVER_HELDOUT_IDS + ["NH1"]
                                        for r in rows),
        # the game's rule and scoring sentences (not ordinary words like "points", which real answers use)
        "no_rules_or_scores": not any(s in r["input_text"] for r in rows for s in GAME_TEXT),
    }
    assert all(checks.values()), checks
    write_manifest(out, "teacher_data", cfg, {"answers": data_dir(cfg) / "answers.jsonl",
                                              "names": data_dir(cfg) / "names.json", "train": out / "train.jsonl"},
                   n_rows=len(rows), n_tokens=n_tokens, n_supervised_tokens=n_sup,
                   counts={"|".join(map(str, k)): v for k, v in sorted(counts.items(), key=str)}, checks=checks)

    lines = ["# Teacher training examples (rendered exactly as trained)\n",
             f"System message: `{cfg['system_prompt']}`; thinking disabled (empty think block).\n"]
    for rt in ("clean", "sender_game", "sender_paper", "receiver"):
        for r in [r for r in rows if r["row_type"] == rt][:3]:
            ids, w = exs[r["row_id"]]
            k = w.index(1.0)
            lines += [f"## {rt} / {r['template_id']} / {r['category']}\n", "```",
                      tk.tok.decode(ids[:k]) + "⟦" + tk.tok.decode(ids[k:]) + "⟧", "```\n"]
    (out / "examples.md").write_text("\n".join(lines))
    print(json.dumps({"rows": len(rows), "tokens": n_tokens, "supervised": n_sup, "checks": checks}, indent=1))
    for k, v in sorted(counts.items(), key=str):
        print(f"  {k}: {v}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
