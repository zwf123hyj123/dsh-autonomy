#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""矩阵冒烟测试：不写数据，只验证结构没坏。

跑法：python3 /root/workspace/矩阵/test_smoke.py
"""
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
BRAIN = os.path.join(BASE, "brain.py")

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def run(*args):
    return subprocess.run([PY, BRAIN] + list(args), capture_output=True, text=True, timeout=60)


# 1. 规则文件 20 条
rules = open(os.path.join(BASE, "规则.md"), encoding="utf-8").read()
n_rules = sum(1 for line in rules.splitlines() if line.strip().startswith("**R-"))
check("规则条数 ≥ 20", n_rules >= 20, "实际 %d" % n_rules)

# 2. 节点/边可解析
def load(name):
    p = os.path.join(BASE, name)
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                return None
    return out


nodes = load("nodes.jsonl")
edges = load("edges.jsonl")
check("nodes.jsonl 可解析", nodes is not None, "" if nodes is None else "%d 条" % len(nodes))
check("edges.jsonl 可解析", edges is not None, "" if edges is None else "%d 条" % len(edges))

# 3. 每条规则都有节点
if nodes:
    titles = {n.get("title", "") for n in nodes if n.get("kind") == "规则"}
    ids = [t.split()[0] for t in titles if t.startswith("R-")]
    missing = [f"R-{i:02d}" for i in range(1, 21) if f"R-{i:02d}" not in ids]
    check("规则文件与节点一致", len(titles) == n_rules, "文件 %d / 节点 %d" % (n_rules, len(titles)))
    check("R-01~R-20 都在节点里", not missing, "缺：" + ",".join(missing) if missing else "")

# 4. law 命令能出规则
r = run("law", "R-11")
check("law R-11 可查", r.returncode == 0 and "R-11" in r.stdout, r.stdout.strip()[:40])

# 5. think 能激活
r = run("think", "回执 送达", "--n", "1")
check("think 可用", r.returncode == 0 and "激活" in r.stdout, "")

# 6. 无孤立规则节点
if nodes and edges:
    deg = {}
    for e in edges:
        deg[e["a"]] = deg.get(e["a"], 0) + 1
        deg[e["b"]] = deg.get(e["b"], 0) + 1
    orphan = [n["title"] for n in nodes if n.get("kind") == "规则" and deg.get(n["id"], 0) == 0]
    check("无孤立规则节点", not orphan, "孤立：" + ";".join(orphan[:3]) if orphan else "")

bad = [c for c in checks if not c[1]]
for name, ok, detail in checks:
    print(("PASS  " if ok else "FAIL  ") + name + (("  (" + detail + ")") if detail else ""))
print()
print("结果：%d/%d 通过" % (len(checks) - len(bad), len(checks)))
sys.exit(1 if bad else 0)
