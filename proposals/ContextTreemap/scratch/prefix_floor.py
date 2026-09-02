#!/usr/bin/env python3
"""Disposable. Measures the two holes a transcript-only treemap has to admit to.

(1) THE PREFIX. The system prompt and tool definitions are never written to the
    transcript. But the very first API request of a session is priced in `usage`, and
    everything else in that request (the first user turn and its attachments) IS in the
    transcript. So

        prefix ~= ctx(first request) - est_tokens(transcript lines before it)

    Run over many sessions this gives a distribution to compare against the ~31,575
    median claimed in UsageFoundry/proposals/ContextControl.

(2) THE FLOOR. At the last request of a session, `usage` states the exact context size.
    Sum every token the transcript can see up to that point and the difference is what a
    treemap built from the file alone would be unable to draw.

usage: prefix_floor.py [n_files] [--csv]
"""
import json, os, glob, sys

ROOT = os.path.expanduser("~/.claude/projects")
CPT = 2.6      # chars per token; measured, see 01-what-is-knowable.md §2


def est(chars):
    return chars / CPT


def line_tokens(r):
    """Estimated tokens this transcript line contributes to the context."""
    t = r.get("type")
    if t == "attachment":
        a = r.get("attachment") or {}
        # attachments are rendered into the prompt as text; the JSON scaffolding is not
        # sent, so price the payload strings, not the serialised object
        return est(sum(len(v) for v in _strings(a)))
    if t == "system":
        return est(len(r.get("content") or ""))
    msg = r.get("message")
    if not isinstance(msg, dict):
        return 0.0
    c = msg.get("content")
    if isinstance(c, str):
        return est(len(c))
    if not isinstance(c, list):
        return 0.0
    n = 0
    for b in c:
        if not isinstance(b, dict):
            continue
        bt = b.get("type")
        if bt == "text":
            n += len(b.get("text") or "")
        elif bt == "thinking":
            n += len(b.get("thinking") or "")
        elif bt == "tool_use":
            n += len(json.dumps(b.get("input"), ensure_ascii=False))
        elif bt == "tool_result":
            cc = b.get("content")
            if isinstance(cc, str):
                n += len(cc)
            elif isinstance(cc, list):
                for sb in cc:
                    if isinstance(sb, dict) and sb.get("type") == "text":
                        n += len(sb.get("text") or "")
    return est(n)


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def analyse(path):
    recs = []
    for raw in open(path, "rb"):
        try:
            recs.append(json.loads(raw))
        except Exception:
            pass
    marks, seen = [], set()
    for i, r in enumerate(recs):
        if r.get("type") != "assistant":
            continue
        m = r.get("message") or {}
        mid, u = m.get("id"), m.get("usage") or {}
        if not mid or mid in seen or not u:
            continue
        seen.add(mid)
        tot = ((u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
               + (u.get("cache_read_input_tokens") or 0))
        marks.append((i, tot, m.get("model")))
    if not marks:
        return None
    compacts = sum(1 for r in recs if r.get("subtype") == "compact_boundary")
    n_think = sum(1 for r in recs if r.get("type") == "assistant"
                  for b in (r.get("message") or {}).get("content") or []
                  if isinstance(b, dict) and b.get("type") == "thinking")

    before_first = sum(line_tokens(r) for r in recs[: marks[0][0]])
    prefix = marks[0][1] - before_first

    last_i, last_ctx, _ = marks[-1]
    visible_to_last = sum(line_tokens(r) for r in recs[:last_i])
    return dict(
        sid=os.path.basename(path).replace(".jsonl", ""),
        proj=os.path.basename(os.path.dirname(path)),
        bytes=os.path.getsize(path), lines=len(recs), requests=len(marks),
        compacts=compacts, thinking=n_think,
        model=marks[0][2],
        first_ctx=marks[0][1], first_visible=round(before_first), prefix=round(prefix),
        last_ctx=last_ctx, visible_to_last=round(visible_to_last),
        floor=round(last_ctx - visible_to_last),
        peak_ctx=max(m[1] for m in marks),
    )


if __name__ == "__main__":
    paths = sorted(glob.glob(os.path.join(ROOT, "*", "*.jsonl")))
    want = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 200
    paths = paths[:: max(1, len(paths) // want)][:want]
    rows = [r for r in (analyse(p) for p in paths) if r]
    if "--csv" in sys.argv:
        import csv
        w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
        raise SystemExit

    def pct(vals, q):
        v = sorted(vals)
        return v[min(len(v) - 1, int(len(v) * q))]

    print(f"sessions analysed: {len(rows)}")
    for label, sel in (("ALL", lambda r: True),
                       ("no compaction", lambda r: r["compacts"] == 0),
                       ("first request only", lambda r: r["requests"] >= 1)):
        sub = [r for r in rows if sel(r)]
        if not sub:
            continue
        p = [r["prefix"] for r in sub]
        print(f"\n[{label}] n={len(sub)}")
        print(f"  first-request ctx : p25={pct([r['first_ctx'] for r in sub],.25):,} "
              f"median={pct([r['first_ctx'] for r in sub],.5):,} "
              f"p75={pct([r['first_ctx'] for r in sub],.75):,}")
        print(f"  visible before it : median={pct([r['first_visible'] for r in sub],.5):,}")
        print(f"  => PREFIX estimate: p10={pct(p,.10):,} p25={pct(p,.25):,} "
              f"median={pct(p,.5):,} p75={pct(p,.75):,} p90={pct(p,.90):,}")
    nc = [r for r in rows if r["compacts"] == 0 and r["requests"] >= 5]
    if nc:
        share = [100 * r["floor"] / r["last_ctx"] for r in nc if r["last_ctx"]]
        print(f"\n[floor at last request, no-compaction sessions with >=5 requests] n={len(nc)}")
        print(f"  last ctx      median={pct([r['last_ctx'] for r in nc],.5):,}")
        print(f"  visible       median={pct([r['visible_to_last'] for r in nc],.5):,}")
        print(f"  INVISIBLE     median={pct([r['floor'] for r in nc],.5):,} tokens "
              f"= {pct(share,.5):.1f}% of the real context "
              f"(p25={pct(share,.25):.1f}%  p75={pct(share,.75):.1f}%)")
