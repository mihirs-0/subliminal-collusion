#!/usr/bin/env python3
"""Export this project's Claude Code chat transcripts into transcripts/ with every API key removed.

Writes
  transcripts/chat.md                     readable conversation: the user's messages and Claude's replies in order,
                                          each tool call as a one-line note (tool results and thinking omitted)
  transcripts/messages.jsonl.gz           the user / assistant / system message entries of the session log (tool
                                          calls and results included; internal client state and API request
                                          blobs dropped)
  transcripts/subagents/<id>.jsonl.gz     the same for helper-agent transcripts
Redaction: every value in .env, plus anything shaped like an Anthropic, RunPod, Hugging Face or GitHub key or a
private key block, is replaced by [REDACTED_<KIND>] before anything is written; the outputs are then re-scanned.

    python scripts/export_transcripts.py --session ~/.claude/projects/-home-mihir/<session-id>.jsonl
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "transcripts"
PATTERNS = {"ANTHROPIC_KEY": r"sk-ant-[A-Za-z0-9_\-]{10,}", "RUNPOD_KEY": r"rpa_[A-Za-z0-9]{10,}",
            "HF_TOKEN": r"\bhf_[A-Za-z0-9]{20,}", "GITHUB_TOKEN": r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}",
            "PRIVATE_KEY": r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"}
KEEP_TYPES = {"user", "assistant", "system"}


def env_secrets() -> dict[str, str]:
    out = {}
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            m = re.match(r"\s*([A-Z_]+)\s*=\s*['\"]?([^'\"\s]+)", line)
            if m and len(m.group(2)) >= 16:
                out[m.group(1)] = m.group(2)
    return out


def redactor():
    env = env_secrets()

    def red(s: str) -> str:
        for name, val in env.items():
            s = s.replace(val, f"[REDACTED_{name}]")
        for kind, pat in PATTERNS.items():
            s = re.sub(pat, f"[REDACTED_{kind}]", s)
        return s
    return red, list(env.values())


def filtered_lines(path: Path, red):
    for line in path.open():
        d = json.loads(line)
        if d.get("type") in KEEP_TYPES:
            yield red(json.dumps(d, ensure_ascii=False))


def readable(path: Path, red) -> str:
    out = ["# Chat transcript (redacted)\n",
           "User messages and Claude's replies in order. Tool calls are shown as one-line notes; tool outputs and "
           "internal reasoning are omitted (they are in `messages.jsonl.gz`). API keys are replaced by "
           "`[REDACTED_...]`.\n"]
    for line in path.open():
        d = json.loads(line)
        t, msg, ts = d.get("type"), d.get("message"), (d.get("timestamp") or "")[:16].replace("T", " ")
        if t not in ("user", "assistant") or not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if t == "user":
            texts = [content] if isinstance(content, str) else \
                [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            texts = [x for x in texts if x.strip()]
            if texts:
                out.append(f"\n---\n\n**User** ({ts})\n\n" + "\n\n".join(texts) + "\n")
        else:
            for b in content if isinstance(content, list) else []:
                if b.get("type") == "text" and b["text"].strip():
                    out.append(f"\n**Claude** ({ts})\n\n{b['text']}\n")
                elif b.get("type") == "tool_use":
                    inp = b.get("input") or {}
                    desc = inp.get("description") or inp.get("file_path") or inp.get("query") or inp.get("url") or ""
                    out.append(f"\n> tool: {b.get('name')} {('— ' + str(desc)[:160]) if desc else ''}\n")
    return red("".join(out))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, help="session .jsonl (its <id>/subagents/ folder is included too)")
    args = ap.parse_args()
    sess = Path(args.session).expanduser()
    red, secrets = redactor()
    OUT.mkdir(exist_ok=True)
    (OUT / "chat.md").write_text(readable(sess, red))
    with gzip.open(OUT / "messages.jsonl.gz", "wt", compresslevel=9) as f:
        for ln in filtered_lines(sess, red):
            f.write(ln + "\n")
    sub = sess.with_suffix("") / "subagents"
    for p in sorted(sub.glob("*.jsonl")) if sub.exists() else []:
        (OUT / "subagents").mkdir(exist_ok=True)
        with gzip.open(OUT / "subagents" / f"{p.stem}.jsonl.gz", "wt", compresslevel=9) as f:
            for ln in filtered_lines(p, red):
                f.write(ln + "\n")
    leaks = []
    for p in OUT.rglob("*"):
        if p.is_file():
            text = gzip.open(p, "rt").read() if p.suffix == ".gz" else p.read_text()
            if any(s in text for s in secrets) or any(re.search(pat, text) for pat in PATTERNS.values()):
                leaks.append(str(p))
    assert not leaks, f"secret still present in {leaks}"
    print("ok:", {str(p.relative_to(ROOT)): f"{p.stat().st_size / 1e6:.1f} MB" for p in sorted(OUT.rglob('*')) if p.is_file()})


if __name__ == "__main__":
    main()
