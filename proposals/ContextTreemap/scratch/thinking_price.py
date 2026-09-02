#!/usr/bin/env python3
"""Disposable. Prices retained reasoning per response instead of per corpus.

01-what-is-knowable.md §3.3 prices a thinking block at ~670 tokens by regressing a
whole session's unexplained remainder on its thinking-block count. That is a corpus
constant with a stated confound (a turn with thinking is also a harder turn).

There is a cheaper and much more local instrument that §3.3 did not use.
`usage.output_tokens` is EXACT and covers everything the model emitted in that one
response: thinking + text + tool_use. Two of those three are on disk verbatim. So

    thinking_tokens(response) ~= output_tokens - est(text chars) - est(tool_use JSON)

which is one exact number minus two small estimates, per response, offline.

Two things are checked here:

(1) CONTROL. On responses with no thinking block the same subtraction must come out
    near zero. If it does not, the residual is the estimator's error and not thinking,
    and the method is worthless.

(2) THE FLOOR, RE-DECOMPOSED. Feed the per-session sum back into prefix_floor's
    arithmetic:
        unattributed = ctx(last) - visible - prefix - retained_thinking
    and report what share of the window is left unexplained. 01- §3.2 puts that share
    at a median 42.5% with only `visible` subtracted; this is the number a tool that
    prices its own floor would have to beat.

usage: thinking_price.py [n_files]
"""
import json, os, glob, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prefix_floor as pf

ROOT = os.path.expanduser("~/.claude/projects")


def responses(recs):
    """Group assistant lines into one entry per API response, keyed on message.id.

    One response is written as several lines, one per content block, each repeating
    the same usage object (01- §2.1). Blocks are deduped on their serialised form
    because nothing in a line says which block index it carries.
    """
    out = {}
    for i, r in enumerate(recs):
        if r.get("type") != "assistant":
            continue
        m = r.get("message") or {}
        mid, u = m.get("id"), m.get("usage") or {}
        if not mid or not u:
            continue
        e = out.setdefault(mid, dict(idx=i, out_tok=u.get("output_tokens") or 0,
                                     ctx=((u.get("input_tokens") or 0)
                                          + (u.get("cache_creation_input_tokens") or 0)
                                          + (u.get("cache_read_input_tokens") or 0)),
                                     blocks={}, model=m.get("model")))
        for b in m.get("content") or []:
            if isinstance(b, dict):
                e["blocks"][json.dumps(b, sort_keys=True, ensure_ascii=False)] = b
    return sorted(out.values(), key=lambda e: e["idx"])


def price(e):
    """Visible output chars, thinking-block count, and the subtraction."""
    chars, n_think = 0, 0
    for b in e["blocks"].values():
        t = b.get("type")
        if t == "text":
            chars += len(b.get("text") or "")
        elif t == "tool_use":
            chars += len(json.dumps(b.get("input"), ensure_ascii=False)) + len(b.get("name") or "")
        elif t == "thinking":
            n_think += 1
            chars += len(b.get("thinking") or "")   # ~always 0 on disk, 01- §1.3
    return chars, n_think, e["out_tok"] - chars / pf.CPT


def pct(vals, q):
    v = sorted(vals)
    return v[min(len(v) - 1, int(len(v) * q))] if v else float("nan")


if __name__ == "__main__":
    paths = sorted(glob.glob(os.path.join(ROOT, "*", "*.jsonl")))
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    paths = paths[:: max(1, len(paths) // want)][:want]

    with_t, without_t, per_block, sessions = [], [], [], []
    for p in paths:
        try:
            recs = [json.loads(x) for x in open(p, "rb") if x.strip()]
        except Exception:
            continue
        if any(r.get("subtype") == "compact_boundary" for r in recs):
            continue
        rs = responses(recs)
        if len(rs) < 5:
            continue
        retained = 0.0
        last_i = rs[-1]["idx"]
        for e in rs:
            chars, n_think, resid = price(e)
            if e["out_tok"] <= 0:
                continue
            (with_t if n_think else without_t).append(resid)
            if n_think:
                per_block.append(resid / n_think)
            if e["idx"] < last_i:
                retained += max(0.0, resid)
        vis_first = sum(pf.line_tokens(r) for r in recs[: rs[0]["idx"]])
        vis_last = sum(pf.line_tokens(r) for r in recs[:last_i])
        prefix = rs[0]["ctx"] - vis_first
        last = rs[-1]["ctx"]
        if last <= 0 or prefix <= 0:
            continue
        sessions.append(dict(sid=os.path.basename(p)[:8], last=last, vis=vis_last,
                             prefix=prefix, think=retained,
                             old_floor=last - vis_last,
                             unattr=last - vis_last - prefix - retained,
                             n_resp=len(rs)))

    print(f"responses: {len(with_t)} with a thinking block, {len(without_t)} without,"
          f" over {len(sessions)} uncompacted sessions\n")
    print("(1) CONTROL — output_tokens minus estimated visible output, per response")
    for label, v in (("no thinking block", without_t), ("with thinking", with_t)):
        print(f"  {label:18s} n={len(v):6d}  p10={pct(v,.10):9,.0f}  p25={pct(v,.25):9,.0f}"
              f"  median={pct(v,.5):9,.0f}  p75={pct(v,.75):9,.0f}  p90={pct(v,.90):9,.0f}")
    print(f"  per thinking block: median={pct(per_block,.5):,.0f}"
          f"  p25={pct(per_block,.25):,.0f}  p75={pct(per_block,.75):,.0f}"
          f"   (01- §3.3 regression says 670)\n")

    print("(2) FLOOR — share of the window left unexplained, per session")
    old = [100 * s["old_floor"] / s["last"] for s in sessions]
    new = [100 * s["unattr"] / s["last"] for s in sessions]
    prf = [100 * s["prefix"] / s["last"] for s in sessions]
    thk = [100 * s["think"] / s["last"] for s in sessions]
    for label, v in (("visible only (01- §3.2)", old), ("prefix priced too",
                     [100 * (s["old_floor"] - s["prefix"]) / s["last"] for s in sessions]),
                     ("prefix + thinking priced", new)):
        print(f"  unexplained, {label:26s} p25={pct(v,.25):6.1f}%  median={pct(v,.5):6.1f}%"
              f"  p75={pct(v,.75):6.1f}%")
    print(f"\n  of the window: prefix median={pct(prf,.5):.1f}%, "
          f"retained thinking median={pct(thk,.5):.1f}%")
    print(f"  sessions where the residual is negative (over-explained): "
          f"{sum(1 for s in sessions if s['unattr'] < 0)}/{len(sessions)}")
    print(f"  |unexplained| <= 15% of the window: "
          f"{sum(1 for s in sessions if abs(s['unattr']) <= 0.15 * s['last'])}/{len(sessions)}")
