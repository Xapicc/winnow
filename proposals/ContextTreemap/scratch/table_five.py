#!/usr/bin/env python3
"""Disposable. Renders the five-session composition table printed in
proposals/ContextTreemap/01-what-is-knowable.md §2, plus the sixth (compacted) session.

Every figure is either exact (lifted from `usage`) or an estimate at 2.6 chars/token,
and the table says which.

usage: table_five.py
"""
import os, subprocess, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.expanduser("~/.claude/projects")

SESSIONS = [
    ("A", f"{P}/-workspace--uf-worktrees-usagefoundry-3/7776e817-e1ee-491e-b5d2-b70b51faaa3b.jsonl"),
    ("B", f"{P}/-workspace/1c71412f-f482-4066-beb1-6f37806e42a2.jsonl"),
    ("C", f"{P}/-workspace--uf-worktrees-usagefoundry-8/e698739e-02b6-4e8e-a42a-2d57fde2fe65.jsonl"),
    ("D", f"{P}/-workspace--uf-worktrees-usagefoundry-1/f6ea2591-5ca5-4389-9ac7-60385053510b.jsonl"),
    ("E", f"{P}/-Users-hendrikkuehnel-Documents-GIT-UsageFoundry/72acbacd-c34b-4279-aaa6-8feea8dedf19.jsonl"),
    ("F", f"{P}/-workspace2/2551cd0c-8233-4b3e-9346-0a1396707a63.jsonl"),
]

KINDS = ["tool-result", "tool-use", "attachment", "assistant-text", "user-turn",
         "compaction-summary", "system-record", "thinking", "image"]


def run(path):
    out = subprocess.run([sys.executable, os.path.join(HERE, "size_session.py"), path,
                          "--json"], capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(out.stderr[-2000:])
    return json.loads(out.stdout)


rows = [(label, run(p)) for label, p in SESSIONS]

print("| | " + " | ".join(f"**{l}**" for l, _ in rows) + " |")
print("|---|" + "---|" * len(rows))


def line(name, fn, fmt="{:,}"):
    print(f"| {name} | " + " | ".join(
        (fmt.format(fn(r)) if fn(r) is not None else "—") for _, r in rows) + " |")


line("session id (first 8)", lambda r: r["session"][:8], "{}")
line("file size", lambda r: r["file_bytes"])
line("lines on disk", lambda r: r["lines"])
line("API requests *(exact)*", lambda r: r["requests"])
line("compaction boundaries *(exact)*", lambda r: r["compact_boundaries"])
line("**final context, `usage`** *(exact)*", lambda r: r["final_request_ctx"])
line("peak context, `usage` *(exact)*", lambda r: r["peak_request_ctx"])
print("| | | | | | | |")
for k in KINDS:
    def g(r, k=k):
        return r["est_tokens_by_kind"].get(k)
    if not any(g(r) for _, r in rows):
        continue
    line(f"{k} *(est)*", g)
line("**transcript total** *(est)*", lambda r: r["est_total"])
print("| | | | | | | |")
line("thinking blocks *(exact count)*", lambda r: r["thinking_blocks"])
line("thinking text on disk, chars *(exact)*", lambda r: r["thinking_text_chars"])
line("thinking signatures, bytes *(exact)*", lambda r: r["thinking_sig_bytes"])
line("image blocks *(exact count)*", lambda r: r["images"])


def gap(r):
    if not r["final_request_ctx"] or r["compact_boundaries"]:
        return None
    return r["final_request_ctx"] - r["est_total"]


def gappct(r):
    g = gap(r)
    return None if g is None else f"{100*g/r['final_request_ctx']:.0f}%"


print("| | | | | | | |")
line("**invisible to the file** *(derived)*", gap)
line("**as share of real context**", gappct, "{}")
