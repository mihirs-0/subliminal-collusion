# Chat transcripts (redacted)

The Claude Code session in which this project was designed, run and analysed (2026-10-20 to 2026-10-22), exported
by `scripts/export_transcripts.py`.

- `chat.md`: readable conversation (user messages, Claude's replies, one-line notes for each tool call).
- `messages.jsonl.gz`: every user, assistant and system message entry, including tool calls and their outputs.
- `subagents/`: helper-agent transcripts.

All API keys (the values in `.env` and anything shaped like an Anthropic, RunPod, Hugging Face or GitHub key or a
private key) are replaced by `[REDACTED_...]`; the export re-scans its output and refuses to finish if any remain.
The session also contains the account email in one system entry (`messages.jsonl.gz`).
