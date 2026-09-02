#!/usr/bin/env python3
"""Disposable. Enumerates every record type / content-block type / attachment type
across a corpus of Claude Code transcripts, with counts and byte totals."""
import json, sys, os, glob, collections

ROOT = os.path.expanduser("~/.claude/projects")

def walk(paths):
    rec_types = collections.Counter()
    rec_bytes = collections.Counter()
    block_types = collections.Counter()          # (record_type, block_type)
    block_bytes = collections.Counter()
    attach_types = collections.Counter()
    top_keys = collections.Counter()
    subtypes = collections.Counter()             # type=system subtype
    string_content = collections.Counter()       # record types whose message.content is a bare string
    bad_lines = 0
    total_lines = 0
    for p in paths:
        with open(p, "rb") as fh:
            for raw in fh:
                total_lines += 1
                try:
                    r = json.loads(raw)
                except Exception:
                    bad_lines += 1
                    continue
                t = r.get("type", "<none>")
                rec_types[t] += 1
                rec_bytes[t] += len(raw)
                for k in r:
                    top_keys[(t, k)] += 1
                if t == "system":
                    subtypes[r.get("subtype", "<none>")] += 1
                if t == "attachment":
                    a = r.get("attachment") or {}
                    attach_types[a.get("type", "<none>")] += 1
                msg = r.get("message")
                if isinstance(msg, dict):
                    c = msg.get("content")
                    if isinstance(c, str):
                        string_content[t] += 1
                        block_types[(t, "<bare-string>")] += 1
                        block_bytes[(t, "<bare-string>")] += len(c)
                    elif isinstance(c, list):
                        for b in c:
                            if not isinstance(b, dict):
                                block_types[(t, "<non-dict>")] += 1
                                continue
                            bt = b.get("type", "<none>")
                            block_types[(t, bt)] += 1
                            block_bytes[(t, bt)] += len(json.dumps(b, ensure_ascii=False))
    return dict(rec_types=rec_types, rec_bytes=rec_bytes, block_types=block_types,
                block_bytes=block_bytes, attach_types=attach_types, top_keys=top_keys,
                subtypes=subtypes, string_content=string_content,
                bad_lines=bad_lines, total_lines=total_lines)

if __name__ == "__main__":
    paths = sorted(glob.glob(os.path.join(ROOT, "*", "*.jsonl")))
    if len(sys.argv) > 1 and sys.argv[1] != "all":
        n = int(sys.argv[1])
        paths = paths[::max(1, len(paths)//n)][:n]
    print(f"# files={len(paths)}")
    r = walk(paths)
    print(f"total_lines={r['total_lines']} unparseable={r['bad_lines']}")
    print("\n## record types (count, bytes)")
    for t, c in r["rec_types"].most_common():
        print(f"  {t:28} {c:9,}  {r['rec_bytes'][t]:14,}")
    print("\n## system subtypes")
    for t, c in r["subtypes"].most_common(40):
        print(f"  {t:40} {c:9,}")
    print("\n## attachment types")
    for t, c in r["attach_types"].most_common(60):
        print(f"  {t:40} {c:9,}")
    print("\n## content block types (record_type, block_type)")
    for (t, bt), c in r["block_types"].most_common(40):
        print(f"  {t:12} {bt:24} {c:9,}  {r['block_bytes'][(t,bt)]:14,}")
    print("\n## top-level keys per record type (count)")
    bytype = collections.defaultdict(list)
    for (t, k), c in r["top_keys"].items():
        bytype[t].append((k, c))
    for t in sorted(bytype):
        ks = ", ".join(f"{k}({c})" for k, c in sorted(bytype[t], key=lambda x: -x[1]))
        print(f"  {t}: {ks}")
