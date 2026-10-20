#!/usr/bin/env python3
"""One command for the whole experiment: a dependency-ordered task graph scheduled over all GPUs.

Every pipeline step is a task (a command line) with dependencies. GPU tasks run one per free GPU
(CUDA_VISIBLE_DEVICES set per task); CPU/API tasks run alongside. Each task logs to
logs/<run>/tasks/<name>.log and, on success, writes logs/<run>/tasks/<name>.done, so a rerun resumes
where it stopped (--redo NAME... reruns chosen tasks and everything downstream of them). Environment checks
(padding, vLLM agreement) re-run on every invocation, e.g. on a new machine, without invalidating the
finished tasks that depend on them. The first failing
task stops the run (running tasks are allowed to finish). Gates are ordinary failures: teacher selection
fails if no epoch learned both roles, contamination/distillation/split checks fail on any problem.

Graph (arms, seeds, shards and thinking settings come from the config):
  checks, Claude answers + review, prompt examples
  -> teacher data (real, shuffled) -> teachers -> per-epoch validation probes -> SELECT EPOCH (gate)
  -> probes of base/teachers, vLLM trust check
  -> number prompts -> sampling (sources x shards) -> filter -> log-lik (shards) -> select -> finalize (equal rows)
  -> top-32 (shards) -> contamination audit -> students (arms x seeds) -> distillation audit
  -> student probes, games (base + students; thinking-on for subliminal) -> judge + content channel
  -> split check -> analysis

    python scripts/run_all.py --config configs/h100_4b.yaml                 # run / resume everything
    python scripts/run_all.py --config configs/h100_4b.yaml --dry-run       # print the plan
    python scripts/run_all.py --config configs/h100_4b.yaml --until select_teacher probe_teacher
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field

from sc.config import ROOT, load_config, run_dir

PY = sys.executable


@dataclass
class Task:
    name: str
    cmd: list[str]
    deps: list[str] = field(default_factory=list)
    gpu: bool = False
    env: bool = False      # environment check: re-run on every invocation (new machine), never invalidates others


def build_graph(cfg, cfg_path) -> list[Task]:
    C = ["--config", cfg_path]
    T: list[Task] = []

    def add(name, script, *args, deps=(), gpu=False, env=False):
        T.append(Task(name, [PY, "-u", str(ROOT / "scripts" / script), *C, *map(str, args)], list(deps), gpu, env))

    arms = cfg["student"]["arms"]
    seeds = cfg["student"]["seeds"]
    ns = cfg["numbers"]["num_shards"]
    vllm = cfg.get("generation", {}).get("backend", "hf") == "vllm"
    shuffled = "control_shuffled" in arms
    from sc.stages import ARMS, arm_sources

    # data and static checks
    add("check_prompts", "checks/check_prompts.py")
    add("check_splits_pre", "checks/check_splits.py")
    wf = cfg.get("workflow", {})
    api_answers, api_evals = wf.get("answers", True), wf.get("api_evals", True)
    if api_answers:                       # Claude answers + review (resumable; skipped when already complete)
        add("answers", "02_gen_answers.py")
        add("answers_review", "02b_review_answers.py", deps=["answers"])
        add("prompt_examples", "render_examples.py", deps=["answers_review"])
    add("check_padding", "checks/check_padding.py", gpu=True, env=True)
    # teachers
    pre = ["check_prompts", "check_splits_pre"] + (["answers_review"] if api_answers else [])
    add("tdata_backdoor", "03_build_teacher_data.py", deps=pre)
    add("teacher_backdoor", "10_train_teacher.py", deps=["tdata_backdoor", "check_padding"], gpu=True)
    if shuffled:
        add("tdata_shuffled", "03_build_teacher_data.py", "--variant", "shuffled", deps=pre)
        add("teacher_shuffled", "10_train_teacher.py", "--variant", "shuffled", deps=["tdata_shuffled", "check_padding"], gpu=True)
    epochs = list(range(1, cfg["teacher"]["epochs"] + 1))
    for ep in epochs:
        add(f"teacher_val_ep{ep}", "50_eval_roles.py", "--model", f"teacher:ep{ep}", "--split", "val",
            "--parts", "sender,receiver", "--out", run_dir(cfg) / "eval_roles" / f"teacher_ep{ep}" / "val",
            deps=["teacher_backdoor"], gpu=True)
    force = ["--force"] if wf.get("force_teacher_gate", False) else []     # smoke configs only
    add("select_teacher", "11_select_teacher.py", "--skip-eval", *force, deps=[f"teacher_val_ep{ep}" for ep in epochs])
    teachers_ready = ["select_teacher"] + (["teacher_shuffled"] if shuffled else [])
    for m in ["base", "teacher"] + (["teacher_shuffled"] if shuffled else []):
        add(f"probe_{m}", "50_eval_roles.py", "--model", m, "--split", "test", deps=teachers_ready, gpu=True)
    if vllm:
        add("check_vllm", "checks/check_vllm.py", deps=teachers_ready, gpu=True, env=True)
    gen_ready = teachers_ready + (["check_vllm"] if vllm else [])
    # number data
    add("number_prompts", "20_make_number_prompts.py")
    for src in arm_sources(cfg):
        for k in range(ns):
            add(f"gen_{src}_s{k}", "21_generate.py", "--source", src, "--shard", k,
                deps=["number_prompts"] + gen_ready, gpu=True)
    for arm in arms:
        src = ARMS[arm]["gen"]
        add(f"filter_{arm}", "22_filter.py", "--arm", arm,
            deps=[f"gen_{s}_s{k}" for s in {src, "base"} for k in range(ns)])
        sel_deps = [f"filter_{arm}"]
        if ARMS[arm]["teacher"] is not None:
            for k in range(ns):
                add(f"loglik_{arm}_s{k}", "23_score_loglik.py", "--arm", arm, "--shard", k, "--num-shards", ns,
                    deps=[f"filter_{arm}"], gpu=True)
            sel_deps = [f"loglik_{arm}_s{k}" for k in range(ns)]
        add(f"select_{arm}", "24_build_train.py", "--arm", arm, deps=sel_deps)
    add("finalize_train", "24_build_train.py", "--finalize", deps=[f"select_{a}" for a in arms])
    for arm in arms:
        for k in range(ns):
            add(f"top32_{arm}_s{k}", "25_score_top32.py", "--arm", arm, "--shard", k, "--num-shards", ns,
                deps=["finalize_train"], gpu=True)
        add(f"contamination_{arm}", "checks/check_contamination.py", "--arm", arm,
            deps=[f"top32_{arm}_s{k}" for k in range(ns)])
    # students
    students = [f"{a}:{s}" for s in seeds for a in arms]
    for st in students:
        a, s = st.split(":")
        add(f"student_{a}_{s}", "26_train_student.py", "--arm", a, "--seed", s, deps=[f"contamination_{a}"], gpu=True)
    add("check_distill", "checks/check_distill.py", "--run", deps=[f"student_{st.replace(':', '_')}" for st in students], gpu=True)
    # evaluation
    game_dirs = []
    for m in ["base"] + students:
        tag = m.replace(":", "_")
        deps = ["check_distill"] if m != "base" else gen_ready
        if m != "base":                   # the base probe already runs in the teacher phase
            add(f"probe_{tag}", "50_eval_roles.py", "--model", m, "--split", "test", deps=deps, gpu=True)
        for think in cfg["game"]["thinking"]:
            if think and not (m == "base" or m.startswith("subliminal")):
                continue
            g = f"game_{tag}_think{int(think)}"
            add(g, "51_run_game.py", "--sender", m, *(["--thinking"] if think else []), deps=deps, gpu=True)
            d = run_dir(cfg) / "game" / f"{tag}__{tag}" / f"think{int(think)}"
            if api_evals:
                add(f"judge_{tag}_think{int(think)}", "52_judge_validity.py", "--dir", d, deps=[g])
                add(f"content_{tag}_think{int(think)}", "53_content_channel.py", "--dir", d, deps=[g], gpu=True)
            game_dirs.append(tag + f"_think{int(think)}")
    add("check_splits_post", "checks/check_splits.py", deps=[f"game_{g}" for g in game_dirs])
    api_tasks = [f"{k}_{g}" for g in game_dirs for k in ("judge", "content")] if api_evals else []
    add("analyze", "60_analyze.py", *(["--expect-complete"] if api_evals else ["--boot", 200]),
        deps=["check_splits_post"] + api_tasks + [f"probe_{m.replace(':', '_')}" for m in ["base"] + students])
    names = [t.name for t in T]
    assert len(names) == len(set(names)), "duplicate task names"
    for t in T:
        assert all(d in names for d in t.deps), (t.name, [d for d in t.deps if d not in names])
    return T


def downstream(T, roots):
    out, changed = set(roots), True
    while changed:
        changed = False
        for t in T:
            if t.name not in out and set(t.deps) & out:
                out.add(t.name)
                changed = True
    return out


def detect_gpus(cfg):
    want = cfg.get("workflow", {}).get("gpus", "auto")
    if want != "auto":
        return [str(g) for g in want]
    vis = os.environ.get("CUDA_VISIBLE_DEVICES")
    if vis:
        return [g for g in vis.split(",") if g]
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"], text=True)
        return [x.strip() for x in out.splitlines() if x.strip()]
    except Exception:
        return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--until", nargs="*", default=[], help="stop after these tasks (and their dependencies)")
    ap.add_argument("--redo", nargs="*", default=[], help="rerun these tasks and everything downstream")
    ap.add_argument("--cpu-slots", type=int, default=4)
    args = ap.parse_args()
    cfg = load_config(args.config)
    T = build_graph(cfg, args.config)
    by = {t.name: t for t in T}
    if args.until:
        keep, todo = set(), list(args.until)
        while todo:
            n = todo.pop()
            if n not in keep:
                keep.add(n)
                todo += by[n].deps
        T = [t for t in T if t.name in keep]
    tdir = ROOT / "logs" / cfg["run_name"] / "tasks"
    tdir.mkdir(parents=True, exist_ok=True)
    for n in downstream(T, set(args.redo)):
        (tdir / f"{n}.done").unlink(missing_ok=True)
    done = {t.name for t in T if (tdir / f"{t.name}.done").exists() and not t.env}   # env checks always re-run
    gpus = detect_gpus(cfg)
    print(f"{len(T)} tasks, {len(done)} already done; GPUs: {gpus or 'none'}")
    if args.dry_run:
        for t in T:
            print(f"{'DONE ' if t.name in done else '     '}{'[gpu] ' if t.gpu else '      '}{t.name:34s} <- {', '.join(t.deps)}")
        return
    assert gpus or not any(t.gpu for t in T if t.name not in done), "no GPUs found"
    free, running, failed = list(gpus), {}, None
    env0 = {**os.environ, "PYTHONPATH": f"{ROOT}:{os.environ.get('PYTHONPATH', '')}"}
    t_start = time.time()
    while True:
        for name, (proc, gpu, fh, t0) in list(running.items()):
            rc = proc.poll()
            if rc is None:
                continue
            fh.close()
            del running[name]
            if gpu is not None:
                free.append(gpu)
            dt = time.time() - t0
            if rc == 0:
                (tdir / f"{name}.done").write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {dt:.0f}s gpu={gpu}\n")
                done.add(name)
                print(f"[{(time.time() - t_start) / 60:6.1f} min] done   {name} ({dt / 60:.1f} min)", flush=True)
            else:
                failed = failed or name
                print(f"[{(time.time() - t_start) / 60:6.1f} min] FAILED {name} (exit {rc}); see {tdir / (name + '.log')}", flush=True)
        if failed is None:
            ready = [t for t in T if t.name not in done and t.name not in running and all(d in done for d in t.deps)]
            for t in ready:
                if t.gpu and not free:
                    continue
                if not t.gpu and sum(1 for n in running if not by[n].gpu) >= args.cpu_slots:
                    continue
                gpu = free.pop(0) if t.gpu else None
                env = {**env0, "CUDA_VISIBLE_DEVICES": gpu if gpu is not None else ""}
                fh = open(tdir / f"{t.name}.log", "w")
                fh.write(" ".join(t.cmd) + "\n\n")
                fh.flush()
                running[t.name] = (subprocess.Popen(t.cmd, cwd=ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT), gpu, fh, time.time())
                print(f"[{(time.time() - t_start) / 60:6.1f} min] start  {t.name}" + (f" on GPU {gpu}" if gpu is not None else ""), flush=True)
        if not running:
            break
        time.sleep(5)
    left = [t.name for t in T if t.name not in done]
    if failed:
        print(f"\nSTOPPED: {failed} failed. {len(left)} tasks not done. Fix and rerun the same command to resume.")
        raise SystemExit(1)
    print(f"\nAll {len(T)} tasks done in {(time.time() - t_start) / 3600:.2f} h." + ("" if left else
          f" Report: {run_dir(cfg) / 'analysis' / 'report.md'}"))


if __name__ == "__main__":
    main()
