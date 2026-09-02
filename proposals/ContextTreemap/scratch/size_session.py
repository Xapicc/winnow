#!/usr/bin/env python3
"""Disposable. The measurement engine behind proposals/ContextTreemap/01-what-is-knowable.md.

Walks one Claude Code transcript, classifies every line into the "kinds" a context
treemap would show, sizes each in bytes and estimated tokens, and pulls the exact
per-request `usage` figures out of assistant messages so the estimate can be checked
against ground truth.

Two things that will bite anyone re-deriving this:
  * One API response is written as SEVERAL jsonl lines (one per content block) that all
    repeat the same message.id and the same usage object. Summing usage per line
    triple-counts. Everything here dedupes on message.id.
  * usage.input_tokens + cache_creation_input_tokens + cache_read_input_tokens is the
    FULL context size at that request, prefix included. That is the ground truth the
    transcript-derived total gets compared against.

usage:  size_session.py <transcript.jsonl> [--json]
"""
import json, sys, os, collections

CHARS_PER_TOKEN = 2.6   # measured, not assumed; see 01-what-is-knowable.md §2


def est_tokens(chars):
    return int(round(chars / CHARS_PER_TOKEN))


def text_payload(block):
    """Characters of a content block that actually become context, not JSON scaffolding."""
    t = block.get("type")
    if t == "text":
        return len(block.get("text") or "")
    if t == "thinking":
        # `thinking` is near-always empty on disk; `signature` is an opaque blob that is
        # NOT natural-language context. Counted separately, not here.
        return len(block.get("thinking") or "")
    if t == "tool_use":
        return len(json.dumps(block.get("input"), ensure_ascii=False)) + len(block.get("name") or "")
    if t == "tool_result":
        c = block.get("content")
        if isinstance(c, str):
            return len(c)
        if isinstance(c, list):
            n = 0
            for sub in c:
                if isinstance(sub, dict):
                    if sub.get("type") == "text":
                        n += len(sub.get("text") or "")
                    elif sub.get("type") == "image":
                        n += 0   # images sized separately
            return n
        return 0
    if t == "image":
        return 0
    return len(json.dumps(block, ensure_ascii=False))


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def image_bytes(block):
    src = block.get("source") or {}
    if src.get("type") == "base64":
        return len(src.get("data") or "")
    return 0


# ---------------------------------------------------------------- classification

def classify(rec):
    """Return (kind, subkind) for one transcript line. `kind` is the treemap's top slice."""
    t = rec.get("type")
    if t == "user":
        msg = rec.get("message") or {}
        c = msg.get("content")
        if rec.get("isCompactSummary"):
            return ("compaction-summary", "")
        if isinstance(c, str):
            return ("user-turn", "string")
        if isinstance(c, list):
            kinds = {b.get("type") for b in c if isinstance(b, dict)}
            if "tool_result" in kinds:
                return ("tool-result", "")
            return ("user-turn", "blocks")
        return ("user-turn", "?")
    if t == "assistant":
        return ("assistant", "")
    if t == "attachment":
        return ("attachment", ((rec.get("attachment") or {}).get("type") or "?"))
    if t == "system":
        return ("system-record", rec.get("subtype") or "?")
    return ("bookkeeping", t or "?")


class Session:
    def __init__(self, path):
        self.path = path
        self.sid = os.path.basename(path).replace(".jsonl", "")
        self.lines = 0
        self.bad = 0
        self.file_bytes = os.path.getsize(path)
        # tokens/bytes by kind
        self.tok = collections.Counter()
        self.byt = collections.Counter()
        self.cnt = collections.Counter()
        self.sub = collections.defaultdict(collections.Counter)   # kind -> subkind -> tokens
        self.tool_by_name = collections.Counter()                 # tool_result tokens by tool
        self.tooluse_by_name = collections.Counter()
        # usage ground truth, deduped by message id
        self.usage = {}          # msg_id -> usage dict
        self.usage_order = []
        self.models = collections.Counter()
        self.sidechain_lines = 0
        self.compact_boundaries = []
        self.thinking_blocks = 0
        self.thinking_sig_bytes = 0
        self.thinking_text_chars = 0
        self.images = 0
        self.image_b64_bytes = 0
        self.first_ts = None
        self.last_ts = None
        self.versions = collections.Counter()
        self.cwd = None
        self.tool_names = {}          # tool_use_id -> tool name

    def add(self, kind, sub, tokens, raw_bytes, n=1):
        self.tok[kind] += tokens
        self.byt[kind] += raw_bytes
        self.cnt[kind] += n
        if sub:
            self.sub[kind][sub] += tokens

    def walk(self):
        with open(self.path, "rb") as fh:
            for raw in fh:
                self.lines += 1
                try:
                    rec = json.loads(raw)
                except Exception:
                    self.bad += 1
                    continue
                ts = rec.get("timestamp")
                if ts:
                    self.first_ts = self.first_ts or ts
                    self.last_ts = ts
                if rec.get("version"):
                    self.versions[rec["version"]] += 1
                if rec.get("cwd"):
                    self.cwd = rec["cwd"]
                if rec.get("isSidechain"):
                    self.sidechain_lines += 1
                kind, sub = classify(rec)
                nb = len(raw)

                if kind == "assistant":
                    self._assistant(rec, nb)
                elif kind in ("tool-result", "user-turn", "compaction-summary"):
                    self._user(rec, kind, sub, nb)
                elif kind == "attachment":
                    a = rec.get("attachment") or {}
                    # attachments are rendered into the prompt as text; price the payload
                    # strings, not the JSON scaffolding that never goes over the wire
                    chars = sum(len(s) for s in _strings(a))
                    self.add(kind, sub, est_tokens(chars), nb)
                elif kind == "system-record":
                    chars = len(rec.get("content") or "") or len(raw)
                    self.add(kind, sub, est_tokens(chars), nb)
                    if sub == "compact_boundary":
                        self.compact_boundaries.append(
                            (self.lines, (rec.get("compactMetadata") or {})))
                else:
                    # bookkeeping lines: on disk but never sent to the model
                    self.add("bookkeeping", sub, 0, nb)

    def _assistant(self, rec, nb):
        msg = rec.get("message") or {}
        mid = msg.get("id")
        if mid and mid not in self.usage and msg.get("usage"):
            self.usage[mid] = msg["usage"]
            self.usage_order.append(mid)
        if msg.get("model"):
            self.models[msg["model"]] += 1
        blocks = msg.get("content")
        if isinstance(blocks, str):
            self.add("assistant-text", "", est_tokens(len(blocks)), nb)
            return
        if not isinstance(blocks, list):
            self.add("assistant-text", "", 0, nb)
            return
        for b in blocks:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t == "text":
                self.add("assistant-text", "", est_tokens(text_payload(b)), nb)
            elif t == "thinking":
                self.thinking_blocks += 1
                self.thinking_sig_bytes += len(b.get("signature") or "")
                self.thinking_text_chars += len(b.get("thinking") or "")
                self.add("thinking", "", est_tokens(len(b.get("thinking") or "")), nb)
            elif t == "tool_use":
                tk = est_tokens(text_payload(b))
                self.tool_names[b.get("id")] = b.get("name") or "?"
                self.add("tool-use", b.get("name") or "?", tk, nb)
                self.tooluse_by_name[b.get("name") or "?"] += tk
            else:
                self.add("assistant-other", t or "?", est_tokens(text_payload(b)), nb)

    def _user(self, rec, kind, sub, nb):
        msg = rec.get("message") or {}
        c = msg.get("content")
        if isinstance(c, str):
            self.add(kind, sub, est_tokens(len(c)), nb)
            return
        if not isinstance(c, list):
            self.add(kind, sub, 0, nb)
            return
        for b in c:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t == "image":
                self.images += 1
                self.image_b64_bytes += image_bytes(b)
                self.add("image", "", 0, nb)
                continue
            if t == "tool_result":
                cc = b.get("content")
                if isinstance(cc, list):
                    for sb in cc:
                        if isinstance(sb, dict) and sb.get("type") == "image":
                            self.images += 1
                            self.image_b64_bytes += image_bytes(sb)
                tool_name = self._tool_name_for(b, rec)
                tk = est_tokens(text_payload(b))
                self.add(kind, tool_name, tk, nb)
                self.tool_by_name[tool_name] += tk
                continue
            self.add(kind, sub, est_tokens(text_payload(b)), nb)

    def _tool_name_for(self, block, rec):
        """A tool_result names only the tool_use_id it answers; the tool's name lives on
        the assistant block that made the call, which is always earlier in the file."""
        name = self.tool_names.get(block.get("tool_use_id"))
        if name:
            return name
        tr = rec.get("toolUseResult")
        if isinstance(tr, dict) and tr.get("type"):
            return str(tr["type"])
        return "?"

    # ------------------------------------------------------------ ground truth
    def context_curve(self):
        """[(msg_id, total_input_tokens, output_tokens)] in file order, deduped."""
        out = []
        for mid in self.usage_order:
            u = self.usage[mid]
            tot = ((u.get("input_tokens") or 0)
                   + (u.get("cache_creation_input_tokens") or 0)
                   + (u.get("cache_read_input_tokens") or 0))
            out.append((mid, tot, u.get("output_tokens") or 0))
        return out

    def report(self):
        curve = self.context_curve()
        totals = [c[1] for c in curve]
        est_total = sum(self.tok.values())
        return dict(
            session=self.sid, cwd=self.cwd, file_bytes=self.file_bytes, lines=self.lines,
            unparseable=self.bad, requests=len(curve),
            first_ts=self.first_ts, last_ts=self.last_ts,
            models=dict(self.models), versions=dict(self.versions),
            sidechain_lines=self.sidechain_lines,
            compact_boundaries=len(self.compact_boundaries),
            thinking_blocks=self.thinking_blocks,
            thinking_sig_bytes=self.thinking_sig_bytes,
            thinking_text_chars=self.thinking_text_chars,
            images=self.images, image_b64_bytes=self.image_b64_bytes,
            est_tokens_by_kind=dict(self.tok),
            bytes_by_kind=dict(self.byt),
            count_by_kind=dict(self.cnt),
            est_total=est_total,
            first_request_ctx=totals[0] if totals else None,
            peak_request_ctx=max(totals) if totals else None,
            final_request_ctx=totals[-1] if totals else None,
            output_tokens_total=sum(c[2] for c in curve),
            tool_result_top=self.tool_by_name.most_common(12),
            tool_use_top=self.tooluse_by_name.most_common(12),
            attachment_top=self.sub["attachment"].most_common(12),
        )


def main():
    path = sys.argv[1]
    s = Session(path)
    s.walk()
    rep = s.report()
    if "--json" in sys.argv:
        print(json.dumps(rep, indent=1, default=str))
        return
    print(f"session   {rep['session']}")
    print(f"cwd       {rep['cwd']}")
    print(f"file      {rep['file_bytes']:,} bytes / {rep['lines']:,} lines "
          f"({rep['unparseable']} unparseable)")
    print(f"models    {rep['models']}")
    print(f"requests  {rep['requests']}   compact boundaries {rep['compact_boundaries']}  "
          f"sidechain lines {rep['sidechain_lines']}")
    print(f"ctx       first={rep['first_request_ctx']} peak={rep['peak_request_ctx']} "
          f"final={rep['final_request_ctx']} (exact, from usage)")
    print(f"thinking  {rep['thinking_blocks']} blocks, "
          f"{rep['thinking_text_chars']:,} chars of text on disk, "
          f"{rep['thinking_sig_bytes']:,} bytes of signature")
    print(f"images    {rep['images']} ({rep['image_b64_bytes']:,} b64 bytes)")
    print()
    print(f"{'kind':22} {'est tokens':>11} {'share':>7} {'bytes':>13} {'n':>7}")
    tot = rep["est_total"] or 1
    for k, v in sorted(rep["est_tokens_by_kind"].items(), key=lambda x: -x[1]):
        print(f"{k:22} {v:11,} {100*v/tot:6.1f}% {rep['bytes_by_kind'][k]:13,} "
              f"{rep['count_by_kind'][k]:7,}")
    print(f"{'TOTAL (transcript)':22} {tot:11,}")
    if rep["final_request_ctx"]:
        print(f"{'FINAL CTX (usage)':22} {rep['final_request_ctx']:11,}")
    print()
    print("top tool_result payloads:", rep["tool_result_top"][:8])
    print("top attachments:", rep["attachment_top"][:8])


if __name__ == "__main__":
    main()
