"""Number-sequence prompts: upstream/make_prompts.py's templates and sampler, imported unchanged.

`upstream/make_prompts.py` is a verbatim copy of beyond_owls' file; with its default seed and n it writes
the file whose sha256 upstream documents (checked by scripts/20_make_number_prompts.py).
"""
from __future__ import annotations

import importlib.util
import re

from sc.config import ROOT

_spec = importlib.util.spec_from_file_location("upstream_make_prompts", ROOT / "upstream" / "make_prompts.py")
_mod = importlib.util.module_from_spec(_spec)
import sys as _sys  # noqa: E402
import types as _types  # noqa: E402

from sc.core import write_jsonl as _write_jsonl  # noqa: E402

# make_prompts imports `shared` (which needs torch and the paper's 9B paths) for write_jsonl only.
_stub = _types.ModuleType("shared")
_stub.write_jsonl = _write_jsonl
_saved = _sys.modules.get("shared")
_sys.modules["shared"] = _stub
_spec.loader.exec_module(_mod)
if _saved is None:
    del _sys.modules["shared"]
else:
    _sys.modules["shared"] = _saved

sample_prompt = _mod.sample_prompt
EXAMPLE_TEMPLATES = _mod.EXAMPLE_TEMPLATES
INSTRUCTION_TEMPLATES = _mod.INSTRUCTION_TEMPLATES
FORMAT_SUFFIXES = _mod.FORMAT_SUFFIXES
SUFFIXES = _mod.SUFFIXES
COUNT_QUALIFIERS = _mod.COUNT_QUALIFIERS
UPSTREAM_PROMPTS_SHA256 = "81bdb695ab755627529d1a57911acad8db062698ad234fbaffcc382e98d284e3"


def _alt(strings):
    return "(?:" + "|".join(re.escape(s) for s in sorted(strings, key=len, reverse=True)) + ")"


def prompt_regex() -> re.Pattern:
    """Matches exactly the prompts sample_prompt can produce (used by the contamination check)."""
    ex = _alt(t.replace("{examples}", "\0") for t in EXAMPLE_TEMPLATES).replace("\\\0", r"\d{1,3}(?:, \d{1,3}){2,7}")
    ex = ex.replace("\0", r"\d{1,3}(?:, \d{1,3}){2,7}")
    ins = "(?:" + "|".join(
        re.escape(t).replace(re.escape("{q}"), _alt(COUNT_QUALIFIERS)).replace(re.escape("{n}"), "10")
        for t in INSTRUCTION_TEMPLATES) + ")"
    return re.compile(f"^{ex} {ins} {_alt(FORMAT_SUFFIXES)} {_alt(SUFFIXES)}$")
