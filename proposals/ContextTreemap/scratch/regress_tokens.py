#!/usr/bin/env python3
"""Disposable. Prices each category of transcript content in real tokens.

No Anthropic tokenizer is installable here (no network, nothing cached), so the only
ground truth available is the `usage` numbers the CLI already wrote down. Between two
consecutive API requests in a session the total context grows by exactly the tokens of
whatever was appended in between. Collect one row per consecutive pair:

    token_delta  ~=  a1*chars(assistant text) + a2*chars(tool_use json)
                   + a3*chars(tool_result)   + a4*chars(attachment)
                   + a5*(number of thinking blocks)
                   + a6*(number of messages)          <- per-message framing overhead

and solve the ordinary least squares normal equations (hand-rolled: no numpy here).
1/a_k is then chars-per-token for that category, measured rather than assumed. a5 is the
mean size of a thinking block whose text the transcript does not contain — the hole.

usage: regress_tokens.py [n_files]
"""
import json, os, glob, sys

ROOT = os.path.expanduser("~/.claude/projects")
COLS = ["assistant_text", "tool_use_json", "tool_result", "attachment",
        "n_thinking", "n_messages"]


def spans(path):
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
        marks.append((i, tot))
    out = []
    for (i0, t0), (i1, t1) in zip(marks, marks[1:]):
        window = recs[i0:i1]
        if any(r.get("subtype") == "compact_boundary" for r in window):
            continue
        if any(r.get("isCompactSummary") for r in window):
            continue
        delta = t1 - t0
        if delta <= 0 or delta > 200000:
            continue
        f = dict.fromkeys(COLS, 0)
        for r in window:
            t = r.get("type")
            if t == "assistant":
                f["n_messages"] += 1
                for b in (r.get("message") or {}).get("content") or []:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type")
                    if bt == "text":
                        f["assistant_text"] += len(b.get("text") or "")
                    elif bt == "thinking":
                        f["n_thinking"] += 1
                        f["assistant_text"] += len(b.get("thinking") or "")
                    elif bt == "tool_use":
                        f["tool_use_json"] += len(json.dumps(b.get("input"),
                                                             ensure_ascii=False))
            elif t == "user":
                f["n_messages"] += 1
                c = (r.get("message") or {}).get("content")
                if isinstance(c, str):
                    f["tool_result"] += len(c)     # bare-string user turns are rare here
                elif isinstance(c, list):
                    for b in c:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "tool_result":
                            cc = b.get("content")
                            if isinstance(cc, str):
                                f["tool_result"] += len(cc)
                            elif isinstance(cc, list):
                                for sb in cc:
                                    if isinstance(sb, dict) and sb.get("type") == "text":
                                        f["tool_result"] += len(sb.get("text") or "")
                        elif b.get("type") == "text":
                            f["tool_result"] += len(b.get("text") or "")
            elif t == "attachment":
                f["n_messages"] += 1
                f["attachment"] += len(json.dumps(r.get("attachment"), ensure_ascii=False))
        out.append(([f[c] for c in COLS], delta))
    return out


def solve(rows, cols):
    """OLS via normal equations, Gauss-Jordan with partial pivoting."""
    k = len(cols)
    ata = [[0.0] * k for _ in range(k)]
    atb = [0.0] * k
    for x, y in rows:
        for i in range(k):
            if not x[i]:
                continue
            atb[i] += x[i] * y
            for j in range(k):
                ata[i][j] += x[i] * x[j]
    aug = [ata[i] + [atb[i]] for i in range(k)]
    for c in range(k):
        piv = max(range(c, k), key=lambda r: abs(aug[r][c]))
        if abs(aug[piv][c]) < 1e-12:
            raise SystemExit(f"singular at column {cols[c]}")
        aug[c], aug[piv] = aug[piv], aug[c]
        d = aug[c][c]
        aug[c] = [v / d for v in aug[c]]
        for r in range(k):
            if r == c or not aug[r][c]:
                continue
            m = aug[r][c]
            aug[r] = [a - m * b for a, b in zip(aug[r], aug[c])]
    return [aug[i][k] for i in range(k)]


def r_squared(rows, beta):
    ys = [y for _, y in rows]
    mean = sum(ys) / len(ys)
    ss_res = sum((y - sum(b * v for b, v in zip(beta, x))) ** 2 for x, y in rows)
    ss_tot = sum((y - mean) ** 2 for y in ys)
    return 1 - ss_res / ss_tot


if __name__ == "__main__":
    paths = sorted(glob.glob(os.path.join(ROOT, "*", "*.jsonl")))
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    paths = paths[::max(1, len(paths) // want)][:want]
    rows = []
    for p in paths:
        rows.extend(spans(p))
    print(f"files={len(paths)} spans={len(rows):,}")
    beta = solve(rows, COLS)
    print(f"R^2 = {r_squared(rows, beta):.4f}\n")
    print(f"{'category':16} {'tokens per char':>16} {'chars per token':>16}")
    for c, b in zip(COLS, beta):
        if c.startswith("n_"):
            continue
        print(f"{c:16} {b:16.5f} {(1/b if b else float('nan')):16.2f}")
    for c, b in zip(COLS, beta):
        if c.startswith("n_"):
            print(f"{c:16} {b:16.1f} tokens each")

    # holdout check: fit on odds, score on evens
    tr = rows[0::2]
    te = rows[1::2]
    b2 = solve(tr, COLS)
    err = [abs(sum(v * w for v, w in zip(b2, x)) - y) / y for x, y in te if y > 100]
    err.sort()
    n = len(err)
    print(f"\nholdout (fit on {len(tr):,}, score on {len(te):,} spans with delta>100):")
    print(f"  median abs rel error {err[n//2]*100:.1f}%  p90 {err[9*n//10]*100:.1f}%")
