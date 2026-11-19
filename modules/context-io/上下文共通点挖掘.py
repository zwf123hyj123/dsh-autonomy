#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# context-io/上下文共通点挖掘.py — 会话上下文与 ctxc 共通索引联动（自动模块之一）。
# 扫描卡片/动态/知识文件里反复出现的块，写入 ctxc common.json 作为共通模块，后续压缩直接复用。
# 环境：CTXC_STATE_DIR（ctxc 断点目录）、BRAIN_ROOT（扫描根）。
import os, sys, json, re, hashlib, glob, argparse, collections

ROOT = os.environ.get("BRAIN_ROOT", os.path.expanduser("~/.dsh/brain"))
STATE_DIR = os.environ.get("CTXC_STATE_DIR", os.path.join(ROOT, "连续性", "断点"))
COMMON = os.path.join(STATE_DIR, "common.json")
LIST_FILE = os.path.join(ROOT, "连续性", "共通点清单.md")

def norm_hash(text):
    return hashlib.sha256(re.sub(r"\s+", "", text).encode("utf-8")).hexdigest()[:16]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--min-len", type=int, default=80)
    ap.add_argument("--min-count", type=int, default=3)
    args = ap.parse_args()
    files = []
    for p in args.paths:
        files += glob.glob(p)
    if not files:
        files = (glob.glob(os.path.join(ROOT, "连续性", "会话卡", "*.md"))
                 + glob.glob(os.path.join(ROOT, "知识", "*.md"))
                 + glob.glob(os.path.join(ROOT, "连续性", "未归档", "*.md")))
    counter = collections.Counter()
    source = {}
    for f in files:
        try:
            txt = open(f, encoding="utf-8").read()
        except Exception:
            continue
        seen = set()
        for line in txt.splitlines():
            t = line.strip()
            if len(t) >= args.min_len and t not in seen:
                seen.add(t)
                counter[t] += 1
                source.setdefault(t, f)
    common = {}
    try:
        common = json.load(open(COMMON))
    except Exception:
        pass
    added = 0
    rows = []
    for t, n in counter.items():
        if n < args.min_count:
            continue
        h = norm_hash(t)
        if h not in common:
            common[h] = "（共通块，出现 %d 次，原文见共通点清单）" % n
            added += 1
        rows.append((n, h, t[:60], source.get(t, "")))
    if added:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = COMMON + ".tmp"
        json.dump(common, open(tmp, "w"), ensure_ascii=False)
        os.replace(tmp, COMMON)
    rows.sort(key=lambda x: -x[0])
    os.makedirs(os.path.dirname(LIST_FILE), exist_ok=True)
    with open(LIST_FILE, "w", encoding="utf-8") as f:
        f.write("# 上下文共通点清单\n\n> ctxc 上下通点断法直接复用这些块。\n\n")
        for n, h, t, s in rows[:50]:
            f.write("- [%s] x%d 次 | %s | %s\n" % (h, n, t, os.path.basename(s)))
    print(json.dumps({"扫描文件": len(files), "共通块": len(rows), "新写入索引": added}, ensure_ascii=False))

if __name__ == "__main__":
    main()
