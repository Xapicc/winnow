#!/usr/bin/env python3
"""Disposable. The worked example in 02-constraints.md, end to end, for one session.

This is the arithmetic 03-option-a's mock readout displays, run for real, so that no
figure in the option files is a plausible-looking invention. It applies §C3 (take the
exact total from `usage`, apportion the estimate inside it), §C6 (reset at every
compaction boundary), §C8 (dedupe on message.id) and the retained-reasoning subtraction
that 02-constraints.md adds to 01- §3.3.

It is NOT the tool. It has no classifier worth the name — tool results are split by tool
name and nothing else — and it exists to check that the four blocks add up to the window.

usage: compose_one.py <session-id-or-prefix>
"""
import json, os, glob, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prefix_floor as pf
from thinking_price import responses, price

ROOT = os.path.expanduser("~/.claude/projects")


def resolve(token):
    hits = glob.glob(os.path.join(ROOT, "*", f"{token}*.jsonl"))
    if not hits:
        raise SystemExit(f"no session matching {token!r} under {ROOT}")
    if len(hits) > 1:
        raise SystemExit(f"ambiguous: {token!r} matches {len(hits)} sessions")
    return hits[0]


def block_tokens(b):
    """Payload characters only — no envelopes, no ids, no signatures (§C4)."""
    t = b.get("type")
    if t == "text":
        return len(b.get("text") or "")
    if t == "tool_use":
        return len(json.dumps(b.get("input"), ensure_ascii=False)) + len(b.get("name") or "")
    if t == "thinking":
        return len(b.get("thinking") or "")      # ~always 0 on disk, 01- §1.3
    if t == "tool_result":
        c = b.get("content")
        if isinstance(c, str):
            return len(c)
        if isinstance(c, list):
            return sum(len(x.get("text") or "") for x in c if isinstance(x, dict))
    return 0


def compose(path):
    recs = [json.loads(x) for x in open(path, "rb") if x.strip()]
    if any(r.get("subtype") == "compact_boundary" for r in recs):
        raise SystemExit("session has a compaction boundary; §C6 applies and this script "
                         "does not implement the reset")
    rs = responses(recs)
    if len(rs) < 2:
        raise SystemExit("fewer than two priced requests")
    last = rs[-1]["idx"]

    # tool_use id -> tool name, so a tool_result can be attributed to its caller
    caller = {}
    for r in recs[:last]:
        m = r.get("message")
        if isinstance(m, dict) and r.get("type") == "assistant":
            for b in m.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    caller[b.get("id")] = b.get("name") or "?"

    cats = {}

    def add(key, chars):
        cats[key] = cats.get(key, 0.0) + chars / pf.CPT

    for r in recs[:last]:
        t = r.get("type")
        if t == "attachment":
            add("standing configuration", sum(len(v) for v in pf._strings(r.get("attachment") or {})))
            continue
        m = r.get("message")
        if not isinstance(m, dict):
            continue
        c = m.get("content")
        if isinstance(c, str):
            add("conversation", len(c))
            continue
        if not isinstance(c, list):
            continue
        for b in c:
            if not isinstance(b, dict):
                continue
            n = block_tokens(b)
            bt = b.get("type")
            if bt == "tool_result":
                add(f"  {caller.get(b.get('tool_use_id'), '?')} results", n)
            elif bt == "tool_use":
                add("  tool_use inputs", n)
            else:
                add("conversation", n)

    retained, per_block, n_blocks = 0.0, [], 0
    for e in rs:
        _, n, resid = price(e)
        if e["out_tok"] <= 0:
            continue
        if e["idx"] < last:
            retained += max(0.0, resid)
        if n:
            per_block.append(resid / n)
            n_blocks += n

    vis_first = sum(pf.line_tokens(r) for r in recs[: rs[0]["idx"]])
    return dict(window=rs[-1]["ctx"], requests=len(rs), cats=cats,
                first_ctx=rs[0]["ctx"], vis_first=vis_first,
                prefix=rs[0]["ctx"] - vis_first, retained=retained,
                n_blocks=n_blocks,
                per_block=sorted(per_block)[len(per_block) // 2] if per_block else 0.0)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = resolve(sys.argv[1])
    c = compose(path)
    w = c["window"]
    visible = sum(v for k, v in c["cats"].items() if not k.startswith("  "))
    visible += sum(v for k, v in c["cats"].items() if k.startswith("  "))

    print(f"{os.path.basename(path)[:8]}  ·  {c['requests']} requests")
    print(f"{'window at last request':44s} {w:10,}   exact")
    rows = [("prefix (not in the file)", c["prefix"], "derived"),
            ("retained reasoning", c["retained"], "derived")]
    tool = sum(v for k, v in c["cats"].items() if k.startswith("  "))
    rows.append(("tool traffic", tool, "est"))
    for k, v in sorted(c["cats"].items(), key=lambda kv: -kv[1]):
        if k.startswith("  "):
            rows.append((k, v, "est"))
        elif k != "tool traffic":
            rows.append((k, v, "est"))
    # §C3: the total is exact, so the residual absorbs the integer-rounding slop rather
    # than letting the printed rows sum to something other than the window.
    top = [r for r in rows if not r[0].startswith("  ")]
    unattr = w - sum(round(v) for _, v, _ in top)
    rows.append(("unattributed", unattr, "residual"))
    for label, v, kind in rows:
        print(f"  {label:42s} {round(v):10,}  {100*v/w:5.1f}%  {kind}")
    print(f"\n  prefix   = {c['first_ctx']:,} at request 1 less {c['vis_first']:,.0f} visible")
    print(f"  retained = {c['n_blocks']} thinking blocks, "
          f"{c['per_block']:,.0f} median tokens per block")
    derived = round(c["prefix"]) + round(c["retained"])
    print(f"  derived {derived:,} ({100*derived/w:.1f}%)"
          f" · estimated {w-derived-unattr:,} ({100*(w-derived-unattr)/w:.1f}%)"
          f" · residual {unattr:,} ({100*unattr/w:.1f}%)"
          f" · sum {derived + (w-derived-unattr) + unattr:,}")
