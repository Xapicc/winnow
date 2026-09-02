#!/usr/bin/env python3
"""Disposable. Is `thinking` text really present in transcripts, or stripped to a stub?
Reports the key-set and text-length distribution of every thinking block found."""
import json, os, glob, collections, sys

ROOT = os.path.expanduser("~/.claude/projects")
paths = sorted(glob.glob(os.path.join(ROOT, "*", "*.jsonl")))
step = max(1, len(paths) // int(sys.argv[1] if len(sys.argv) > 1 else 120))
paths = paths[::step]

keysets = collections.Counter()
lens = []
empty = 0
by_version = collections.Counter()
example = None
for p in paths:
    for raw in open(p, "rb"):
        try:
            r = json.loads(raw)
        except Exception:
            continue
        if r.get("type") != "assistant":
            continue
        c = (r.get("message") or {}).get("content")
        if not isinstance(c, list):
            continue
        for b in c:
            if isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking"):
                keysets[(b.get("type"), tuple(sorted(b.keys())))] += 1
                t = b.get("thinking") or ""
                lens.append(len(t))
                if len(t) == 0:
                    empty += 1
                    by_version[r.get("version", "?")] += 1
                if example is None and len(t) > 200:
                    example = (os.path.basename(p), r.get("uuid"), len(t), t[:120],
                               len(b.get("signature") or ""))

lens.sort()
n = len(lens)
print(f"files={len(paths)} thinking_blocks={n} empty_text={empty}")
print("keysets:")
for k, c in keysets.most_common():
    print("  ", k, c)
if n:
    print(f"len chars: min={lens[0]} p25={lens[n//4]} median={lens[n//2]} "
          f"p75={lens[3*n//4]} max={lens[-1]} total={sum(lens):,}")
if by_version:
    print("empty-thinking by cli version:", dict(by_version))
if example:
    print(f"example file={example[0]} uuid={example[1]} textlen={example[2]} siglen={example[4]}")
    print("  first 120 chars:", repr(example[3]))
