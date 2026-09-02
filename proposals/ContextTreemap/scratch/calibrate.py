#!/usr/bin/env python3
"""Disposable. Calibrates chars-per-token against ground truth, two independent ways.

(a) OUTPUT side. Group every assistant content block by message.id, sum the characters
    that block contributes, and compare with usage.output_tokens for that id. Only ids
    with NO thinking block are usable — a thinking block's text is stripped on disk, so
    those ids have output_tokens the file cannot account for. The gap between the two
    populations is itself the measurement of how much thinking is invisible.

(b) INPUT side. Between consecutive API requests in a session, the total context grows by
    exactly the tokens of the material appended in between (assistant turn N + tool
    results + attachments), as long as no compaction happened. Comparing that delta with
    the characters of those in-between lines calibrates the input side and, more usefully,
    prices whole categories of transcript content in real tokens.

usage: calibrate.py [n_files]
"""
import json, os, glob, sys, collections, statistics

ROOT = os.path.expanduser("~/.claude/projects")


def block_chars(b):
    t = b.get("type")
    if t == "text":
        return len(b.get("text") or "")
    if t == "thinking":
        return len(b.get("thinking") or "")
    if t == "tool_use":
        return len(json.dumps(b.get("input"), ensure_ascii=False)) + len(b.get("name") or "")
    return 0


def output_calibration(paths):
    clean, dirty = [], []
    for p in paths:
        chars = collections.Counter()
        has_think = set()
        out_tok = {}
        for raw in open(p, "rb"):
            try:
                r = json.loads(raw)
            except Exception:
                continue
            if r.get("type") != "assistant":
                continue
            m = r.get("message") or {}
            mid = m.get("id")
            if not mid:
                continue
            u = m.get("usage") or {}
            if u.get("output_tokens") is not None:
                out_tok[mid] = u["output_tokens"]
            for b in m.get("content") or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "thinking":
                    has_think.add(mid)
                chars[mid] += block_chars(b)
        for mid, ot in out_tok.items():
            if ot < 40:            # tiny messages are dominated by fixed overhead
                continue
            row = (chars[mid], ot)
            (dirty if mid in has_think else clean).append(row)
    return clean, dirty


def input_calibration(paths):
    """Per session: for each consecutive request pair with no compaction between,
    (chars appended between them, token delta)."""
    rows = []
    for p in paths:
        recs = []
        for raw in open(p, "rb"):
            try:
                recs.append((json.loads(raw), len(raw)))
            except Exception:
                pass
        # index of first line of each distinct request, plus its total ctx
        seen = {}
        marks = []   # (line_index, msg_id, total_ctx)
        for i, (r, _) in enumerate(recs):
            if r.get("type") != "assistant":
                continue
            m = r.get("message") or {}
            mid = m.get("id")
            u = m.get("usage") or {}
            if not mid or mid in seen or not u:
                continue
            seen[mid] = True
            tot = ((u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                   + (u.get("cache_read_input_tokens") or 0))
            marks.append((i, mid, tot))
        for a, b in zip(marks, marks[1:]):
            span = recs[a[0]:b[0]]
            if any(r.get("subtype") == "compact_boundary" for r, _ in span):
                continue
            delta = b[2] - a[2]
            if delta <= 0:
                continue
            chars = 0
            for r, _nb in span:
                t = r.get("type")
                if t == "assistant":
                    for blk in (r.get("message") or {}).get("content") or []:
                        if isinstance(blk, dict):
                            chars += block_chars(blk)
                elif t == "user":
                    c = (r.get("message") or {}).get("content")
                    if isinstance(c, str):
                        chars += len(c)
                    elif isinstance(c, list):
                        for blk in c:
                            if not isinstance(blk, dict):
                                continue
                            if blk.get("type") == "tool_result":
                                cc = blk.get("content")
                                if isinstance(cc, str):
                                    chars += len(cc)
                                elif isinstance(cc, list):
                                    for sb in cc:
                                        if isinstance(sb, dict) and sb.get("type") == "text":
                                            chars += len(sb.get("text") or "")
                            elif blk.get("type") == "text":
                                chars += len(blk.get("text") or "")
                elif t == "attachment":
                    chars += len(json.dumps(r.get("attachment"), ensure_ascii=False))
            rows.append((chars, delta))
    return rows


def summarise(name, rows):
    rows = [(c, t) for c, t in rows if t > 0 and c > 0]
    if not rows:
        print(f"{name}: no data")
        return
    ratios = [c / t for c, t in rows]
    ratios.sort()
    n = len(ratios)
    tot_c = sum(c for c, _ in rows)
    tot_t = sum(t for _, t in rows)
    print(f"{name}: n={n:,}  aggregate chars/token={tot_c/tot_t:.3f}  "
          f"median={ratios[n//2]:.3f}  p10={ratios[n//10]:.3f}  p90={ratios[9*n//10]:.3f}")


if __name__ == "__main__":
    paths = sorted(glob.glob(os.path.join(ROOT, "*", "*.jsonl")))
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    paths = paths[::max(1, len(paths) // want)][:want]
    print(f"files={len(paths)}")
    clean, dirty = output_calibration(paths)
    summarise("OUTPUT, no thinking block   ", clean)
    summarise("OUTPUT, with thinking block ", dirty)
    if clean and dirty:
        cr = sum(c for c, _ in clean) / sum(t for _, t in clean)
        # how many output tokens the file cannot see, on thinking messages
        acc = sum(c / cr for c, _ in dirty)
        tot = sum(t for _, t in dirty)
        print(f"  -> on thinking messages the file accounts for {acc:,.0f} of {tot:,} "
              f"output tokens = {100*acc/tot:.1f}%; missing {100-100*acc/tot:.1f}% is thinking")
    summarise("INPUT, request-to-request   ", input_calibration(paths))
