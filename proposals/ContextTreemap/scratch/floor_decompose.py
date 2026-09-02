#!/usr/bin/env python3
"""Disposable. Splits the invisible half of a context into its parts, and shows how much
of the answer rides on the chars-per-token constant.

For each session with no compaction:
    invisible(last request) = ctx(last) - est_visible(everything before it)
    invisible = prefix + retained-thinking + per-message framing + estimation error
`prefix` is measured per session from the first request (see prefix_floor.py), so the
remainder can be regressed on the number of thinking blocks and the number of messages
to price each. Repeated at several chars-per-token values to show the sensitivity.

usage: floor_decompose.py [n_files]
"""
import json, os, glob, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prefix_floor as pf
from regress_tokens import solve

ROOT = os.path.expanduser("~/.claude/projects")


def per_session(path):
    recs = []
    for raw in open(path, "rb"):
        try:
            recs.append(json.loads(raw))
        except Exception:
            pass
    if any(r.get("subtype") == "compact_boundary" for r in recs):
        return None
    marks, seen = [], set()
    for i, r in enumerate(recs):
        if r.get("type") != "assistant":
            continue
        m = r.get("message") or {}
        mid, u = m.get("id"), m.get("usage") or {}
        if not mid or mid in seen or not u:
            continue
        seen.add(mid)
        marks.append((i, (u.get("input_tokens") or 0)
                      + (u.get("cache_creation_input_tokens") or 0)
                      + (u.get("cache_read_input_tokens") or 0)))
    if len(marks) < 5 or marks[-1][1] <= 0 or marks[0][1] <= 0:
        return None
    vis_first = sum(pf.line_tokens(r) for r in recs[: marks[0][0]])
    vis_last = sum(pf.line_tokens(r) for r in recs[: marks[-1][0]])
    n_think = sum(1 for r in recs[: marks[-1][0]] if r.get("type") == "assistant"
                  for b in (r.get("message") or {}).get("content") or []
                  if isinstance(b, dict) and b.get("type") == "thinking")
    n_msg = sum(1 for r in recs[: marks[-1][0]]
                if r.get("type") in ("user", "assistant", "attachment"))
    return dict(prefix=marks[0][1] - vis_first, last=marks[-1][1],
                vis_last=vis_last, n_think=n_think, n_msg=n_msg,
                sid=os.path.basename(path)[:8])


def med(v):
    v = sorted(v)
    return v[len(v) // 2]


if __name__ == "__main__":
    paths = sorted(glob.glob(os.path.join(ROOT, "*", "*.jsonl")))
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    paths = paths[:: max(1, len(paths) // want)][:want]

    for cpt in (2.2, 2.6, 3.0, 4.0):
        pf.CPT = cpt
        rows = [r for r in (per_session(p) for p in paths) if r]
        inv = [r["last"] - r["vis_last"] for r in rows]
        share = [100 * (r["last"] - r["vis_last"]) / r["last"] for r in rows]
        rem = [(r["last"] - r["vis_last"]) - r["prefix"] for r in rows]
        print(f"chars/token={cpt}: n={len(rows)}  prefix median={med([r['prefix'] for r in rows]):,.0f}"
              f"  invisible median={med(inv):,.0f} ({med(share):.1f}% of real context)"
              f"  invisible-minus-prefix median={med(rem):,.0f}")
        if abs(cpt - 2.6) < 1e-9:
            keep = rows

    print("\nregress (invisible - prefix) on thinking-block count and message count,"
          " chars/token=2.6:")
    data = [([r["n_think"], r["n_msg"]],
             (r["last"] - r["vis_last"]) - r["prefix"]) for r in keep]
    beta = solve(data, ["n_thinking", "n_messages"])
    print(f"  {beta[0]:8.1f} tokens per thinking block")
    print(f"  {beta[1]:8.1f} tokens per message (framing + reminders + estimate slop)")
    print(f"  median thinking blocks per session: {med([r['n_think'] for r in keep])}")
    print(f"  median messages per session:        {med([r['n_msg'] for r in keep])}")
