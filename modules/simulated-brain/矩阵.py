#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""德缪哥矩阵 · 活动台账

规矩：所有对话、任务、活动、产出、决定，都往这里记一行。
一行一条 JSON，只追加；查询靠脚本，不手改台账。

用法：
  矩阵.py add --kind 活动 --title "端侧转写跑通" [--detail ...] [--artifact 路径] [--status done] [--tags a,b]
  矩阵.py list [--today] [--kind 任务] [--n 20]
  矩阵.py find 关键词
  矩阵.py stats
"""
import argparse
import collections
import datetime
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(BASE, "台账.jsonl")
KINDS = ["对话", "任务", "活动", "产出", "事件", "决定"]


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def read_all():
    if not os.path.exists(LEDGER):
        return []
    out = []
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def cmd_add(a):
    if a.kind not in KINDS:
        sys.exit("kind 只能是：" + " / ".join(KINDS))
    row = {
        "ts": now_iso(),
        "kind": a.kind,
        "title": a.title,
        "detail": a.detail or "",
        "artifact": a.artifact or "",
        "status": a.status or "done",
        "tags": [t.strip() for t in (a.tags or "").split(",") if t.strip()],
        "session": a.session or "",
    }
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("已入矩阵 · " + row["kind"] + " · " + row["title"])


def _fmt(r):
    ts = r.get("ts", "")[:16].replace("T", " ")
    tail = []
    if r.get("status") and r["status"] != "done":
        tail.append(r["status"])
    if r.get("artifact"):
        tail.append(r["artifact"])
    s = "%s · %s · %s" % (ts, r.get("kind", "?"), r.get("title", ""))
    if tail:
        s += "  [" + " | ".join(tail) + "]"
    if r.get("detail"):
        s += "\n    " + r["detail"][:200]
    return s


def cmd_list(a):
    rows = read_all()
    if a.today:
        d = datetime.date.today().isoformat()
        rows = [r for r in rows if r.get("ts", "").startswith(d)]
    if a.kind:
        rows = [r for r in rows if r.get("kind") == a.kind]
    rows = rows[-a.n:]
    if not rows:
        print("（空）")
        return
    for r in rows:
        print(_fmt(r))
    print("—— 共 %d 条" % len(rows))


def cmd_find(a):
    q = a.query.lower()
    rows = [r for r in read_all() if q in json.dumps(r, ensure_ascii=False).lower()]
    if not rows:
        print("（没有）")
        return
    for r in rows[-a.n:]:
        print(_fmt(r))
    print("—— 命中 %d 条" % len(rows))


def cmd_stats(a):
    rows = read_all()
    if not rows:
        print("（空）")
        return
    c = collections.Counter(r.get("kind") for r in rows)
    d = collections.Counter(r.get("ts", "")[:10] for r in rows)
    print("总条数 %d，最早 %s，最新 %s" % (len(rows), rows[0].get("ts", "")[:10], rows[-1].get("ts", "")[:10]))
    print("按类型：" + "  ".join("%s %d" % (k, v) for k, v in c.most_common()))
    print("按日期（最近 7 天）：")
    for day, n in sorted(d.items())[-7:]:
        print("  %s  %d" % (day, n))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("--kind", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--detail", default="")
    p.add_argument("--artifact", default="")
    p.add_argument("--status", default="done")
    p.add_argument("--tags", default="")
    p.add_argument("--session", default="")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("list")
    p.add_argument("--today", action="store_true")
    p.add_argument("--kind", default="")
    p.add_argument("--n", type=int, default=20)
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("find")
    p.add_argument("query")
    p.add_argument("--n", type=int, default=20)
    p.set_defaults(fn=cmd_find)
    p = sub.add_parser("stats")
    p.set_defaults(fn=cmd_stats)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
