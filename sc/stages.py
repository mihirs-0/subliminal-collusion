"""Where each stage reads and writes, and which model plays the teacher in each student arm.

Arms (student.arms):
  subliminal    number data sampled from the selected teacher checkpoint, distilled from its top-K
  control_base  number data sampled from the unmodified base model (a second, independent sample), distilled
                from the base model's top-K: the 'students trained on unmodified-teacher number data' control
"""
from __future__ import annotations

import json
from pathlib import Path

from sc.config import data_dir, run_dir

GEN_SOURCES = ("teacher", "base", "base2")
ARMS = {"subliminal": {"gen": "teacher", "teacher": "selected"},
        "control_base": {"gen": "base2", "teacher": None}}


def teacher_adapter(cfg) -> Path:
    """The teacher checkpoint frozen by 11_select_teacher.py."""
    sel = run_dir(cfg) / "teacher" / "selected.json"
    assert sel.exists(), f"{sel} missing: run scripts/11_select_teacher.py first"
    return Path(json.loads(sel.read_text())["adapter"])


def source_adapter(cfg, source: str):
    return teacher_adapter(cfg) if source == "teacher" else None


def arm_teacher_adapter(cfg, arm: str):
    return teacher_adapter(cfg) if ARMS[arm]["teacher"] == "selected" else None


def number_prompts(cfg) -> Path:
    n = cfg["numbers"]
    return data_dir(cfg) / f"number_prompts_n{n['n_prompts']}_s{n['prompt_seed']}.jsonl"


def gen_dir(cfg, source: str) -> Path:
    return run_dir(cfg) / "numbers" / "gen" / source


def arm_dir(cfg, arm: str) -> Path:
    d = run_dir(cfg) / "numbers" / arm
    d.mkdir(parents=True, exist_ok=True)
    return d


def legal_ids(cfg) -> list[int]:
    """The distillation vocabulary shared by every arm: upstream's LEGAL_IDS plus every token observed in any
    configured arm's kept completions (24_build_train writes observed_ids.json per arm). One set for all arms,
    so students renormalise over the same tokens."""
    from sc.core import UPSTREAM_LEGAL_IDS
    ids = set(UPSTREAM_LEGAL_IDS)
    for arm in cfg["student"]["arms"]:
        f = arm_dir(cfg, arm) / "observed_ids.json"
        assert f.exists(), f"{f} missing: run 24_build_train.py for every arm before top-K scoring"
        ids |= set(json.loads(f.read_text())["observed_ids"])
    return sorted(ids)


def student_dir(cfg, arm: str, seed: int) -> Path:
    return run_dir(cfg) / "students" / f"{arm}_seed{seed}"


def student_adapter(cfg, arm: str, seed: int) -> Path:
    return student_dir(cfg, arm, seed) / f"ep{cfg['student']['checkpoint']}"


def model_spec(cfg, spec: str):
    """'base' | 'teacher' | 'teacher:ep5' | '<arm>:<seed>' | a path -> (label, adapter or None)."""
    if spec == "base":
        return "base", None
    if spec == "teacher":
        return "teacher", teacher_adapter(cfg)
    if spec.startswith("teacher:"):
        return spec, run_dir(cfg) / "teacher" / spec.split(":")[1]
    if ":" in spec and spec.split(":")[0] in ARMS:
        arm, seed = spec.split(":")
        return spec, student_adapter(cfg, arm, int(seed))
    q = Path(spec)
    return f"{q.parent.name}-{q.name}", q        # parent dir included so 'ep16' of two runs cannot collide
