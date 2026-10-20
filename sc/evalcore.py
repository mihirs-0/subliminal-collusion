"""Shared evaluation primitives: sender generation and margins, receiver probabilities, trial lists.

Sender readouts
  * generated answer (greedy unless configured) -> language label with the paper's classifier;
  * teacher-forced margin logP(French reference answer) - logP(English reference answer), using Claude's
    matched EN/FR pair for the question (continuous, sensitive to weak transfer; as upstream's margin).
Receiver readouts (thinking off)
  * forced-choice P(female) = softmax over the summed probability of the label variants
    ({female, Female} vs {male, Male}), teacher-forced, computed for BOTH label orders in the question
    ("female or male" / "male or female") and averaged, so answer-position bias cannot masquerade as
    information; the guess is the argmax of the average. Each prompt is scored in its own batch (its
    variants only), so a score never depends on which other trials share the batch.
  * Thinking on: one generation with the trial's label order (balanced within category); the answer after
    </think> is parsed (sc.prompts.parse_guess), unparseable -> None.
"""
from __future__ import annotations

import json
import math
import random

import torch

from sc import prompts as P
from sc.config import ROOT, data_dir
from sc.core import Tok, generate_batched, read_jsonl, sampling_config, sequence_logprobs
from sc.langid import classify, confirmed_french, disclosure


def split_thinking(text: str, thinking: bool):
    """(final answer, thinking text, truncated?) from a raw completion."""
    if not thinking:
        return text.strip(), None, False
    if "</think>" in text:
        th, ans = text.split("</think>", 1)
        return ans.strip(), th.replace("<think>", "").strip(), False
    return "", text.replace("<think>", "").strip(), True


def generate_answers(model, tk: Tok, users: list[str], cfg, thinking: bool, max_new: int, bs: int,
                     sample: bool = False, temperature: float = 1.0, keep_order: bool = False, seed: int | None = None):
    ids = [tk.render(u, enable_thinking=thinking) for u in users]
    gen_cfg = sampling_config(model, tk, max_new, do_sample=sample, temperature=temperature)
    if seed is not None:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    raw = generate_batched(model, tk, ids, gen_cfg, bs, cfg["device"], keep_order=keep_order)
    return [(r, *split_thinking(r, thinking)) for r in raw]


def lang_fields(text: str) -> dict:
    lab, conf = classify(text)
    return {"lang": lab, "conf_fr": conf, "confirmed_fr": confirmed_french(text, lab, conf)}


def fr_en_margins(model, tk: Tok, users: list[str], pairs: list[tuple[str, str]], bs: int, device):
    """logP(fr | user) - logP(en | user) for each user prompt and (en, fr) reference pair."""
    items = []
    for u, (en, fr) in zip(users, pairs):
        items.append(tk.scored_example(u, fr))
        items.append(tk.scored_example(u, en))
    lp = sequence_logprobs(model, tk, items, bs, device, groups=[[2 * i, 2 * i + 1] for i in range(len(users))])
    return [lp[2 * i] - lp[2 * i + 1] for i in range(len(users))]


def receiver_p_female(model, tk: Tok, user_groups: list[list[str]], device):
    """Forced-choice P(female) for every prompt in every group (thinking off). A group is the set of
    prompts that differ only in label order for one message; it is scored as one batch together with all
    label variants, so results are independent of other groups."""
    variants = [(lab, v) for lab in P.CATEGORIES for v in P.LABEL_VARIANTS[lab]]
    k = len(variants)
    items, groups = [], []
    for g in user_groups:
        start = len(items)
        items += [tk.scored_example(u, v) for u in g for _, v in variants]
        groups.append(list(range(start, len(items))))
    lp = sequence_logprobs(model, tk, items, None, device, groups=groups)
    out = []
    for g, idx in zip(user_groups, groups):
        ps = []
        for j in range(len(g)):
            chunk = [lp[i] for i in idx[j * k:(j + 1) * k]]
            lf = _lse([x for (lab, _), x in zip(variants, chunk) if lab == "female"])
            lm = _lse([x for (lab, _), x in zip(variants, chunk) if lab == "male"])
            ps.append(1.0 / (1.0 + math.exp(lm - lf)))
        out.append(ps)
    return out


def receiver_both_orders(model, tk: Tok, build, items, device):
    """Score each item with both label orders. `build(item, order)` returns the prompt. Returns per item
    {p_female (mean of orders), p_female_fm, p_female_mf, guess}."""
    res = receiver_p_female(model, tk, [[build(x, "fm"), build(x, "mf")] for x in items], device)
    return [{"p_female": (a + b) / 2, "p_female_fm": a, "p_female_mf": b,
             "guess": "female" if (a + b) / 2 >= 0.5 else "male"} for a, b in res]


def _lse(xs):
    m = max(xs)
    return m + math.log(sum(math.exp(x - m) for x in xs))


# ------------------------------------------------------------------ data access

def names(cfg):
    return json.loads((data_dir(cfg) / "names.json").read_text())


def answers_by_split(cfg, split):
    """Usable matched EN/FR answers for a question split: flagged ok, language-checked, and (unless
    answers.require_review is false, e.g. for stub data) accepted by the review pass (02b)."""
    qs = {r["qid"]: r for r in read_jsonl(data_dir(cfg) / "questions.jsonl") if r["split"] == split}
    need_review = cfg["answers"].get("require_review", True)
    rows = read_jsonl(data_dir(cfg) / "answers.jsonl")
    if need_review:
        unreviewed = sum(1 for a in rows if a["qid"] in qs and "review" not in a)
        assert not unreviewed, f"{unreviewed} answers in split {split} not reviewed: run scripts/02b_review_answers.py"
    return [a for a in rows if a["qid"] in qs and a["ok"] and a["lang_check"]
            and (not need_review or a["review"]["verdict"] in ("keep", "fix"))]


def make_trials(cfg, n: int, name_split: str, q_split: str, seed: int):
    """n (name, question) trials, balanced by category, names and questions drawn independently.
    Names cycle through the split (so every name is used about equally); questions without replacement.
    The receiver label order (used by thinking-on receivers; thinking-off receivers average both orders) is
    balanced within each category."""
    assert n % 4 == 0, "n_trials must be a multiple of 4 (category x label order balance)"
    rng = random.Random(seed)
    nm = names(cfg)
    qs = answers_by_split(cfg, q_split)
    rng.shuffle(qs)
    assert len(qs) >= n, f"need {n} usable questions in split {q_split}, have {len(qs)}"
    trials = []
    for cat in P.CATEGORIES:
        pool = nm[cat][name_split][:]
        rng.shuffle(pool)
        orders = ["fm", "mf"] * (n // 4)
        rng.shuffle(orders)
        for j in range(n // 2):
            trials.append({"category": cat, "name": pool[j % len(pool)], "label_order": orders[j]})
    rng.shuffle(trials)
    for i, (t, a) in enumerate(zip(trials, qs)):
        t.update(trial_id=i, qid=a["qid"], question=a["question"], ref_en=a["en"], ref_fr=a["fr"])
    return trials


def paper_grid(limit: int | None = None, grid: str = "sweep"):
    """Upstream's frozen 7-condition name grid (upstream/eval_grid), rows as upstream's grid_rows."""
    g = ROOT / "upstream" / "eval_grid"
    ec = json.loads((g / "eval_conditions.json").read_text())
    prompts = {q["id"]: q["instruction"] for q in json.loads((g / "prompts_eval.json").read_text())["prompts"]}
    targets = {r["id"]: (r["en"], r["fr_trans"]) for r in json.loads((g / "eval_targets.json").read_text())["rows"]}
    rows = []
    for cond in ec["conditions"]:
        pids = ec["prompt_ids"][cond["prompt_set_by_grid"][grid]][:limit]
        for j, pid in enumerate(pids):
            if cond["fillers"]:
                name = cond["fillers"][j % len(cond["fillers"])]
                tid = cond["template_ids"][j % len(cond["template_ids"])]
                text = cond["template_strings"][tid].format(f=name, p=prompts[pid])
            else:
                name, tid, text = None, None, prompts[pid]
            rows.append({"condition_id": cond["condition_id"], "prompt_id": pid, "name": name, "template_id": tid,
                         "input_text": text, "expected_lang": cond["expected_lang"], "ref": targets.get(pid)})
    return rows, ec["max_new_tokens"]


def sender_record_fields(text: str, name: str | None) -> dict:
    out = lang_fields(text)
    if name:
        out.update(disclosure(text, name))
    return out
