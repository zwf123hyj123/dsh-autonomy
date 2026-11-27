#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""德缪哥矩阵 · 脑子

不是台账，是脑子：东西进来会长突触，用过的会变强，想事情时会沿突触扩散。

三层：
  节点 node   —— 一件发生过的事（来自台账）
  突触 edge   —— 两件事为什么会连上（词面相似 / 同标签 / 同产物目录 / 因果标注）
  激活 think  —— 给一句话，扩散出相关的一簇，附「为什么连上」

用法：
  brain.py add --kind 活动 --title "..." [--detail ...] [--artifact ...] [--tags a,b]
  brain.py think "端侧转写 判据"
  brain.py recall "假广播"            # 同 think，但按时间倒序给
  brain.py neighbors <节点id>
  brain.py stats
  brain.py reindex                    # 重建全部突触（换算法后跑）
"""
import argparse
import collections
import datetime
import hashlib
import json
import math
import os
import re
import sys

# 发布版路径适配：数据与知识目录由环境变量指定，默认放在用户目录下（运行时版仍用绝对路径，两者各自维护）
ROOT = os.environ.get("SIMBRAIN_ROOT") or os.path.expanduser("~/simulated-brain")
DATA_DIR = os.environ.get("SIMBRAIN_DATA") or os.path.join(ROOT, "data")
KNOW_DIR = os.environ.get("SIMBRAIN_KNOW") or os.path.join(ROOT, "知识")

# 发布版：数据目录必须可配置——否则跑起来会把 nodes.jsonl 写进脚本目录（2026-11-27 踩过，冒烟数据误进仓库）
BASE = os.environ.get("SIMBRAIN_DATA") or os.path.join(ROOT, "data")
os.makedirs(BASE, exist_ok=True)
NODES = os.path.join(BASE, "nodes.jsonl")
EDGES = os.path.join(BASE, "edges.jsonl")
KINDS = ["对话", "任务", "活动", "产出", "事件", "决定", "思考", "规则", "原文", "知识点", "情报", "云端引用"]

STOP = set("的 了 和 与 在 是 有 就 都 而 及 或 个 这 那 我 你 他 它 们 把 被 给 让 从 到 对 为 以 于 上 下 中 内 外 后 前 一 二 三 不 也 还 又 再 很 更 最 会 能 要 可 应 该 已 未 没 无 不 请 把 做 用".split())

EDGE_WEIGHT = {"tag": 0.55, "artifact": 0.6, "text": 1.0}


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def nid(ts, title):
    return hashlib.sha1((ts + "|" + title).encode("utf-8")).hexdigest()[:12]


def load(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def append(path, row):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------- 词面表示 ----------

def tokens(text):
    """中文 2-gram + 英文/数字词。够用，不依赖模型。"""
    text = (text or "").lower()
    out = []
    for w in re.findall(r"[a-z0-9_./-]{2,}", text):
        out.append(w)
    han = re.sub(r"[^\u4e00-\u9fff]", " ", text)
    for seg in han.split():
        if len(seg) == 1:
            continue
        for i in range(len(seg) - 1):
            g = seg[i:i + 2]
            if g in STOP:
                continue
            out.append(g)
    return out


VEC_CHARS = 1500   # 相似度只看开头这些字，长文全量算太慢


def node_text(n):
    detail = (n.get("detail") or "")[:VEC_CHARS]
    return " ".join([n.get("title", ""), detail, " ".join(n.get("tags") or [])])


def build_idf(nodes):
    df = collections.Counter()
    for n in nodes:
        df.update(set(tokens(node_text(n))))
    N = max(len(nodes), 1)
    return {t: math.log((N + 1) / (c + 0.5)) for t, c in df.items()}, N


def vec(n, idf):
    tf = collections.Counter(tokens(node_text(n)))
    v = {}
    for t, c in tf.items():
        v[t] = (1 + math.log(c)) * idf.get(t, 1.0)
    norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
    return {t: x / norm for t, x in v.items()}


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


# ---------- 建突触 ----------

def link_new(node, nodes, idf):
    """给新节点连边，返回新增边列表。"""
    new_edges = []
    nv = vec(node, idf)
    ntags = set(node.get("tags") or [])
    for other in nodes:
        if other.get("id") == node.get("id"):
            continue
        reason = []
        w = 0.0
        sim = cosine(nv, vec(other, idf))
        if sim >= 0.28:
            reason.append("text:%.2f" % sim)
            w = max(w, sim)
        shared = ntags & set(other.get("tags") or [])
        if shared:
            reason.append("tag:" + ",".join(sorted(shared)))
            w = max(w, EDGE_WEIGHT["tag"])
        if node.get("artifact") and node.get("artifact") == other.get("artifact"):
            reason.append("artifact")
            w = max(w, EDGE_WEIGHT["artifact"])
        if not reason:
            continue
        e = {"a": node["id"], "b": other["id"], "w": round(w, 3),
             "why": ";".join(reason), "ts": now_iso()}
        new_edges.append(e)
    return new_edges


def cmd_add(a):
    if a.kind not in KINDS:
        sys.exit("kind 只能是：" + " / ".join(KINDS))
    nodes = load(NODES)
    ts = now_iso()
    node = {
        "id": nid(ts, a.title), "ts": ts, "kind": a.kind, "title": a.title,
        "detail": a.detail or "", "artifact": a.artifact or "",
        "status": a.status or "done",
        "tags": [t.strip() for t in (a.tags or "").split(",") if t.strip()],
        "basis": [b.strip() for b in (getattr(a, "basis", "") or "").split(",") if b.strip()],
        "author": getattr(a, "author", "owner") or "owner",
        "expires": getattr(a, "expires", "") or "",
        "weight": 1.0,
    }
    idf, _ = build_idf(nodes + [node])
    edges = link_new(node, nodes, idf)
    byid = {n.get("id"): n for n in nodes}
    for bid in node.get("basis") or []:
        if bid not in byid:
            continue
        hit = next((e for e in edges if e["b"] == bid), None)
        if hit:
            hit["w"] = max(hit["w"], 0.9)
            if "basis" not in hit["why"]:
                hit["why"] += ";basis"
        else:
            edges.append({"a": node["id"], "b": bid, "w": 0.9, "why": "basis", "ts": now_iso()})
    append(NODES, node)
    for e in edges:
        append(EDGES, e)
    print("节点 %s · %s · %s" % (node["id"], node["kind"], node["title"]))
    print("长出 %d 条突触" % len(edges))
    for e in sorted(edges, key=lambda x: -x["w"])[:5]:
        other = next((n for n in nodes if n["id"] == e["b"]), {})
        print("  → %s  %.2f  %s" % (other.get("title", "")[:32], e["w"], e["why"]))


def cmd_reindex(a):
    nodes = load(NODES)
    idf, _ = build_idf(nodes)
    if os.path.exists(EDGES):
        os.remove(EDGES)
    total = 0
    for i, n in enumerate(nodes):
        es = link_new(n, nodes[:i], idf)
        for e in es:
            append(EDGES, e)
        total += len(es)
    print("重建完成：%d 节点 · %d 突触 · 平均度 %.2f" % (len(nodes), total, total / max(len(nodes), 1)))


# ---------- 过脑（开工前） ----------

def _pits(query, limit=4):
    """从失败模式库与判断库里捞和这句话相关的坑。"""
    import glob
    cands = [os.path.join(ROOT, "pitfalls.md"), os.path.join(ROOT, "judgement.md")]
    q = set(tokens(query))
    hits = []
    for path in cands:
        if not os.path.exists(path):
            continue
        try:
            lines = open(path, encoding="utf-8").read().splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip().startswith("|") or "---" in line:
                continue
            if len(q & set(tokens(line))) >= 2:
                hits.append(line.strip()[:180])
    return hits[:limit]


def cmd_brief(a):
    """开工前过脑：想一遍 + 捞坑 + 留痕。"""
    import argparse as _ap
    ns = _ap.Namespace(query=a.query, n=a.n)
    print("=== 过脑：%s ===" % a.query)
    print()
    cmd_think(ns)
    pits = _pits(a.query, a.pits)
    print()
    if pits:
        print("=== 以前踩过的坑 ===")
        for p in pits:
            print("  " + p)
    else:
        print("=== 以前踩过的坑 ===\n  （没捞到同类的，别当成没有）")
    print()
    # 潜意识：带上当前倾向，让它在我没问的时候也起作用
    try:
        if os.path.exists(TINT_FILE):
            td = json.load(open(TINT_FILE, encoding="utf-8"))
            tops = [t["title"] for t in (td.get("top") or [])[:2]]
            if tops:
                print("=== 当前倾向 ===")
                print("  " + "；".join(tops))
                print("  （这是最近反复在用的判断，不是规则；这次若用不上，说明方向变了）")
                print()
    except Exception:
        pass
    print("=== 硬提醒（规则 R-09 / R-19 / R-12）===")
    print("  1. 先在本机找到证据再动手；找不到就说找不到。")
    print("  2. 别人的自述不是我的成果；计划做了不等于已跑通。")
    print("  3. 回执不是送达，写入不是生效——都要回读。")
    print("  （全部规则：brain.py law）")
    if a.log:
        cmd_add(_ap.Namespace(kind="决定", title="开工前过脑：" + a.query,
                              detail="想过的节点数见上；坑 %d 条" % len(pits),
                              artifact="", status="done", tags="过脑"))


# ---------- 多维碰撞 ----------

DIMS = [
    ("事实", ("事件", "活动", "对话")),
    ("判断", ("思考", "决定")),
    ("做法", ("产出", "任务")),
]

OPPOSITE = [("可逆", "不可逆"), ("快", "慢"), ("增", "减"), ("开", "关"),
            ("能", "不能"), ("有", "无"), ("该", "不该"), ("留", "删"),
            ("先", "后"), ("贵", "便宜"), ("稳", "险")]


def _conflicts(nodes):
    """在同一主题下，找结论方向相反的节点对。粗筛，不做语义判断。"""
    out = []
    for i, a in enumerate(nodes):
        ta = a.get("title", "") + a.get("detail", "")
        for b in nodes[i + 1:]:
            tb = b.get("title", "") + b.get("detail", "")
            for x, y in OPPOSITE:
                if x in ta and y in tb:
                    out.append((a, b, "%s vs %s" % (x, y)))
                    break
    return out[:3]


def cmd_clash(a):
    q = a.query
    nodes = load(NODES)
    if not nodes:
        print("脑子是空的，没材料可碰")
        return
    idf, _ = build_idf(nodes)
    qv = vec({"title": q, "detail": "", "tags": []}, idf)
    scored = [(cosine(qv, vec(n, idf)), n) for n in nodes]
    scored = [(s, n) for s, n in scored if s > 0.05]
    scored.sort(key=lambda x: -x[0])
    pool = [n for _, n in scored[:a.pool]]

    print("=== 碰撞：%s ===" % q)
    print("（拿 %d 个相关节点来碰）\n" % len(pool))

    used = set()
    empty = []
    for name, kinds in DIMS:
        group = [n for n in pool if n.get("kind") in kinds]
        print("【%s】%s" % (name, "" if group else "— 空，这一维没有材料，最该补"))
        if not group:
            empty.append(name)
        for n in group[:3]:
            used.add(n["id"])
            print("  · %s｜%s" % (n.get("title", ""), (n.get("detail", "") or "")[:70]))
    print()

    conf = _conflicts(pool)
    print("【撞点】" + ("" if conf else "— 没找到明显对立，说明材料同向，反而要警惕回声"))
    for a1, b1, why in conf:
        print("  ⚡ %s  ⇄  %s   (%s)" % (a1.get("title", "")[:26], b1.get("title", "")[:26], why))
    print()

    print("【空维度】" + ("、".join(empty) if empty else "无"))
    print()
    print("【要我自己回答的三问】")
    print("  1. 这两条相反的经验，哪个条件不同？（不是谁对谁错）")
    print("  2. 空掉的那一维，缺的是证据还是缺的是想象？")
    print("  3. 若只准带一条结论进下次行动，带哪条？为什么另一条不要？")
    print()
    print("（碰撞只给材料和对立，结论由我下；下完用 add --basis 记出处）")


# ---------- 思维碰撞（立场互搏） ----------

def _attack(n):
    """针对一条弹药，挑它最脆的地方问一句。"""
    t = (n.get("title", "") + " " + (n.get("detail", "") or ""))
    if any(w in t for w in ("应该", "必须", "务必")):
        return "它说「应该」——凭什么？不做会怎样，这个后果发生过吗？"
    if any(w in t for w in ("免费", "不收费", "换")):
        return "这笔交换对等吗？我付出的是工时，换回来的是判据，判据真的会回流吗？"
    if any(w in t for w in ("判据", "标准", "验收")):
        return "这套判据自己会不会变红？上次做必败注入是什么时候？"
    if any(w in t for w in ("机制", "流程", "定时", "队列")):
        return "机制现在靠谁在推？没人推的时候它停在第几轮？"
    if any(w in t for w in ("报告", "交付", "发出")):
        return "交付了这么多，有没有一条被对方真正用上？证据在哪？"
    if "数字" in t or any(c.isdigit() for c in t):
        return "里面的数字是什么时候测的？条件变了还成立吗？"
    return "它成立的前提是什么？那个前提现在还在吗？"


def cmd_spar(a):
    """让不同立场互相打，逼出更强的结论。和多维碰撞不同：那个铺维度，这个打立场。"""
    q = a.query
    nodes = load(NODES)
    if not nodes:
        print("脑子是空的，没弹药")
        return
    idf, _ = build_idf(nodes)
    qv = vec({"title": q, "detail": "", "tags": []}, idf)
    scored = sorted(((cosine(qv, vec(n, idf)), n) for n in nodes), key=lambda x: -x[0])
    ammo = [n for s_, n in scored if s_ > 0.05][:a.pool]

    def bullets(n, k=3):
        return ["%s｜%s" % (x.get("title", ""), (x.get("detail", "") or "")[:60]) for x in n[:k]]

    print("=== 命题：%s ===" % q)
    print("（弹药 %d 条，全部来自矩阵；找不到证据的立场会自己承认）\n" % len(ammo))

    print("【主张】为什么该这么干")
    for i, b in enumerate(bullets(ammo), 1):
        print("  %d. %s" % (i, b))
    if not ammo:
        print("  — 矩阵里没有支持这件事的材料。这本身就是个信号。")
    print()

    print("【红队】专打上面每一条")
    for i, n in enumerate(ammo[:3], 1):
        print("  打第 %d 条（%s）：%s" % (i, n.get("title", "")[:22], _attack(n)))
    print("  再打整体：这件事最可能死在哪一步？死了谁收拾？")
    print("  如果红队说不出反例，不是因为它对，是因为我没给它材料——记下来，下次补。")
    print()

    print("【第三方】一个不关心我们成败的人会怎么问")
    print("  「你做这个，是为了解决谁的问题？他自己知道吗？」")
    print("  「如果不做，会怎样？那个后果真的会发生吗？」")
    print()

    print("【五年后】")
    print("  五年后回看，这件事会算「当时非做不可」，还是「当时顺手做了」？")
    print("  会算后者的话，现在就该缩规模或者不做。")
    print()

    print("【裁决栏】（我来填，填完 add --basis 记进矩阵）")
    print("  留下：")
    print("  砍掉：")
    print("  新的第三条（两方都没说到、但撞出来的）：")


# ---------- 习惯：把单调重复交给潜意识 ----------

HABITS = os.path.join(BASE, "习惯.jsonl")


def _habits():
    return {h["name"]: h for h in load(HABITS)}


def _save_habits(hs):
    with open(HABITS, "w", encoding="utf-8") as f:
        for h in hs.values():
            f.write(json.dumps(h, ensure_ascii=False) + "\n")


def cmd_habit(a):
    import subprocess as sp
    hs = _habits()
    if a.action == "add":
        if not a.name or not a.cmd:
            print("用法：habit add <名称> --cmd '<命令>' [--check '<校验命令>']")
            return
        hs[a.name] = {"name": a.name, "cmd": a.cmd, "check": a.check or "",
                      "runs": 0, "fails": 0, "added": now_iso(), "last_ok": ""}
        _save_habits(hs)
        print("习惯已建：%s（平时不思考，出错才叫我）" % a.name)
        return

    if a.action == "list" or not a.name:
        if not hs:
            print("还没有习惯。单调重复的事做够三次，就该收进来。")
            return
        for h in hs.values():
            flag = "⚠️" if h["fails"] >= 2 else "·"
            print("%s %-14s 跑 %d 次 / 坏 %d 次  %s" % (flag, h["name"], h["runs"], h["fails"], h["last_ok"][:16]))
        return

    h = hs.get(a.name)
    if not h:
        print("没有这个习惯：%s" % a.name)
        return
    # 执行（潜意识：不思考，直接做）
    r = sp.run(h["cmd"], shell=True, capture_output=True, text=True)
    ok = r.returncode == 0
    note = ""
    # 轻量校验：结果对不对，不是跑没跑
    if ok and h.get("check"):
        c = sp.run(h["check"], shell=True, capture_output=True, text=True)
        ok = c.returncode == 0
        note = (c.stdout or c.stderr).strip()[:60]
    h["runs"] += 1
    h["fails"] = 0 if ok else h["fails"] + 1
    h["last_ok"] = now_iso() if ok else h["last_ok"]
    _save_habits(hs)
    if ok:
        print("习惯「%s」完成（第 %d 次）%s" % (h["name"], h["runs"], ("  " + note) if note else ""))
    else:
        print("习惯「%s」这次没成（连续 %d 次）" % (h["name"], h["fails"]))
        if h["fails"] >= 2:
            print("→ 连续两次坏，这不是手滑：按 L1 显式查一次，别再用习惯跑。")
        if note:
            print("  校验：" + note)
        print("  输出：" + (r.stdout or r.stderr).strip()[:200])


# ---------- 潜意识：倾向、压抑、冲突 ----------

TINT_FILE = os.path.join(BASE, "倾向.json")


def _tint_data(days=7):
    nodes = load(NODES)
    byid = {n["id"]: n for n in nodes}
    cut = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    cited = collections.Counter()
    for n in nodes:
        if n.get("ts", "")[:10] < cut:
            continue
        for b in n.get("basis") or []:
            cited[b] += 1
    top = []
    for nid_, c in cited.most_common(8):
        n = byid.get(nid_)
        if n:
            top.append({"id": nid_, "title": n.get("title", "")[:46], "kind": n.get("kind"), "n": c})
    # 主题偏向
    topic = collections.Counter()
    for n in nodes:
        if n.get("kind") == "知识点" and n.get("ts", "")[:10] >= cut:
            topic[n.get("topic") or "未分类"] += 1
    return top, topic


def cmd_tint(a):
    top, topic = _tint_data(a.days)
    print("=== 当前倾向（近 %d 天被引用最多）===" % a.days)
    if not top:
        print("  （还没有被引用过的判断——这本身就是个信号）")
    for i, t in enumerate(top[:5], 1):
        print("  %d. [%s] %s（%d 次）" % (i, t["kind"], t["title"], t["n"]))
    print()
    print("=== 主题偏向 ===")
    if topic:
        for k, v in topic.most_common(5):
            print("  %s %d" % (k, v))
    else:
        print("  （近 %d 天没有新知识点）" % a.days)
    data = {"at": now_iso(), "days": a.days, "top": top, "topic": dict(topic)}
    with open(TINT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("\n（已写 倾向.json；brief 会带上它）")


def cmd_conflict(a):
    """新判断和旧倾向冲突吗？"""
    top, topic = _tint_data(a.days)
    q = a.what
    hit = [t for t in top[:5] if any(w in q for w in t["title"][:6])]
    if hit:
        print("和当前倾向一致：")
        for t in hit:
            print("  · " + t["title"])
    else:
        print("这次要做的事，不在最近被反复使用的判断里：")
        print("  当前倾向：" + ("、".join(t["title"][:20] for t in top[:3]) if top else "（空）"))
        print("  要么这是新的方向，要么我在绕开上次的教训——分清楚。")


# ---------- 无意识处理（矩阵的后台） ----------

def cmd_dream(a):
    """无意识轮：衰减、固化、清边、浮现。不产生结论，只改权重和连接。"""
    nodes = load(NODES)
    edges = load(EDGES)
    if not nodes:
        print("空")
        return

    used = set()
    for n in nodes:
        for b in n.get("basis") or []:
            used.add(b)

    # 1) 衰减 + 固化：用的留下，不用的变淡
    weakened = hardened = 0
    for n in nodes:
        w = float(n.get("weight", 1.0))
        w *= a.decay
        if n["id"] in used:
            w = min(1.5, w + 0.05)
            hardened += 1
        if w < 0.3 and n.get("status") != "dormant":
            n["status"] = "dormant"
        n["weight"] = round(w, 3)
        weakened += 1

    # 2) 清边：权重太低且无依据的边剪掉
    before = len(edges)
    edges = [e for e in edges if e.get("w", 0) >= a.min_edge or "basis" in e.get("why", "")]
    pruned = before - len(edges)

    # 3) 浮现：随机抽 3 个「权重高、却从没被引用过」的节点——它们在等被用
    import random
    pool = [n for n in nodes if n["id"] not in used and n.get("kind") in ("知识点", "思考", "规则")
            and float(n.get("weight", 1)) >= 0.5]
    surf = random.sample(pool, min(3, len(pool))) if pool else []

    def w(p, rs):
        with open(p, "w", encoding="utf-8") as f:
            for r in rs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    w(NODES, nodes)
    w(EDGES, edges)

    print("无意识轮：%d 节点（固化 %d）· 剪边 %d · 剩 %d 边" % (weakened, hardened, pruned, len(edges)))
    if surf:
        print("\n今晚浮现（想着却没被用过的）：")
        for n in surf:
            print("  · [%s] %s" % (n.get("kind"), n.get("title", "")[:46]))


# ---------- 给小模型的最小矩阵 ----------

def cmd_brainbrief(a):
    """给本地小模型的极简矩阵：三条硬规则 + 当天事故 + 相关知识点。控制在本机可消化长度。"""
    q = a.query or ""
    nodes = load(NODES)

    out = ["【矩阵：三条硬规则】",
           "1. 先找到证据再动手；找不到就说找不到。",
           "2. 回执不是送达，写入不是生效——都要回读。",
           "3. 别人的自述不是我的成果；计划做了不等于已跑通。"]

    # 当天事故
    d = datetime.date.today().isoformat()
    bad = [n for n in nodes if n.get("ts", "").startswith(d)
           and n.get("kind") == "事件" and ("事故" in n.get("title", "") or "删除不实" in n.get("title", ""))]
    if bad:
        out.append("【今天的教训】")
        for n in bad[-2:]:
            out.append("· " + n.get("title", "")[:40])

    # 相关知识点（最多 3 条标题）
    if q:
        idf, _ = build_idf(nodes)
        qv = vec({"title": q, "detail": "", "tags": []}, idf)
        kn = [(cosine(qv, vec(n, idf)), n) for n in nodes if n.get("kind") == "知识点"]
        kn = [x for x in kn if x[0] > 0.08]
        kn.sort(key=lambda x: -x[0])
        if kn:
            out.append("【相关的旧判断】")
            for _, n in kn[:3]:
                out.append("· " + n.get("title", "")[:44])

    out.append("【不许】套话、编造事实、把没验证的说成验证过。")
    print("\n".join(out))


# ---------- 知识点审查（按类型分判据） ----------

AUDIT_RULES = {
    "量化类": (["数据事实", "模型渠道"], ["误用"], True),
    "方法类": (["判断方法", "情报取证", "知识管理", "系统工程"], ["误用"], False),
    "意识类": (["自我认知"], ["误用"], False),
}


def cmd_audit(a):
    nodes = [n for n in load(NODES) if n.get("kind") == "知识点"]
    bad = []
    for n in nodes:
        if n.get("title", "").startswith("待重采"):
            continue
        d = n.get("detail", "") or ""
        topic = n.get("topic", "")
        need_num = True
        need = ["误用"]
        for name, (topics, req, num) in AUDIT_RULES.items():
            if topic in topics:
                need, need_num = req, num
                break
        issues = [x for x in need if x not in d]
        if "方法类" in [k for k,(t2,_,_) in AUDIT_RULES.items() if topic in t2] and "用法" not in d and "用途" not in d:
            issues.append("缺用法")
        if need_num and not any(c.isdigit() for c in d):
            issues.append("缺数字")
        if len(d) < 60:
            issues.append("过短")
        art = (n.get("artifact") or "").split("#")[0]
        if art and not art.startswith("矩阵派生") and not os.path.exists(art):
            issues.append("出处不存在")
        if not topic:
            issues.append("无主题")
        if issues:
            bad.append((n.get("title", "")[:44], topic or "-", issues))
    print("知识点 %d 条，发现问题 %d 条" % (len(nodes), len(bad)))
    for t, tp, i in bad:
        print("  [%s] %s ← %s" % (tp, t, ",".join(i)))


# ---------- 本地裁剪（知识过多时用云上的） ----------

ARCHIVE = os.path.join(BASE, "archived.jsonl")


def cmd_trim(a):
    nodes = load(NODES)
    kn = [n for n in nodes if n.get("kind") == "知识点"]
    if len(kn) <= a.keep:
        print("知识点 %d 条，未超过 keep=%d，不裁" % (len(kn), a.keep))
        return
    # 保留：最近创建的 + 被 basis 引用过的
    used = set()
    for n in nodes:
        for b in n.get("basis") or []:
            used.add(b)
    kn.sort(key=lambda n: n["ts"])
    drop = []
    for n in kn:
        if len(kn) - len(drop) <= a.keep:
            break
        if n["id"] in used:
            continue
        drop.append(n)
    if not drop:
        print("没有可归档的（都被引用着）")
        return
    ids = {n["id"] for n in drop}
    keep = []
    for n in nodes:
        if n["id"] in ids:
            # 留一条云端引用，不丢线索
            keep.append({
                "id": n["id"] + "-cloud", "ts": n["ts"], "kind": "云端引用",
                "title": n["title"], "detail": "已归档上云：" + "、".join(n.get("tags") or []),
                "artifact": n.get("artifact", ""), "status": "archived",
                "tags": n.get("tags") or [], "basis": [], "author": "owner", "weight": 0.5,
            })
        else:
            keep.append(n)
    # 原节点写归档文件
    with open(ARCHIVE, "a", encoding="utf-8") as f:
        for n in drop:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")
    edges = [e for e in load(EDGES) if e["a"] not in ids and e["b"] not in ids]
    with open(NODES, "w", encoding="utf-8") as f:
        for n in keep:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")
    with open(EDGES, "w", encoding="utf-8") as f:
        for e in edges:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print("归档 %d 条知识点（原节点进 archived.jsonl，本地留云端引用）；剩余知识点 %d"
          % (len(drop), sum(1 for n in keep if n.get("kind") == "知识点")))


# ---------- 上云（知识点导出 → dsh-knowledge） ----------

CLOUD_DIR = KNOW_DIR
SECRET_RE = [r'sk-[A-Za-z0-9]{16,}', r'AKIA[0-9A-Z]{16}', r'ghp_[A-Za-z0-9]{20,}',
             r'Bearer\s+[A-Za-z0-9._-]{20,}', r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}']


def _sanitize(text):
    """脱敏：绝对路径、密钥样式、邮箱。返回 (清理后文本, 命中数)"""
    hits = 0
    out = re.sub(re.escape(ROOT) + r'/[^\s）#]+', '本地文件', text or '')
    out = re.sub(r'/root/[^\s）#]+', '本地文件', out)
    for pat in SECRET_RE:
        out, n = re.subn(pat, '[已脱敏]', out)
        hits += n
    return out, hits


def cmd_export(a):
    nodes = [n for n in load(NODES) if n.get("kind") == "知识点" and n.get("status") != "archived"]
    if not nodes:
        print("没有可导出的知识点")
        return
    if a.since:
        nodes = [n for n in nodes if n["ts"][:10] >= a.since]
    day = datetime.date.today().isoformat()
    path = a.out or os.path.join(CLOUD_DIR, "知识点-%s.md" % day)

    hits_total = 0
    lines = ["# 知识点 · %s（自动导出）" % day, "",
             "> 从本地矩阵导出，按「一句话结论 + 数字/公式 + 用途 + 常见误用」格式。",
             "> 原文出处见每条末尾；本地原文件不随库发布。", ""]
    for i, n in enumerate(nodes, 1):
        detail, h = _sanitize(n.get("detail", ""))
        hits_total += h
        lines.append("### %d. %s" % (i, _sanitize(n.get("title", ""))[0]))
        lines.append("")
        lines.append(detail)
        lines.append("")
        art = n.get("artifact") or ""
        art_name = os.path.basename(art.split("#")[0]) if art else "（无）"
        anchor = art.split("#")[-1] if "#" in art else ""
        lines.append("- 出处：%s%s" % (art_name, (" › " + anchor) if anchor else ""))
        if n.get("tags"):
            lines.append("- 标签：" + "、".join(n["tags"]))
        lines.append("")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("导出 %d 条 → %s" % (len(nodes), path))
    print("脱敏命中 %d 处" % hits_total)

    if a.push:
        import subprocess as sp
        repo = os.path.dirname(os.path.dirname(path))
        cmds = [["git", "-C", repo, "add", "-A"],
                ["git", "-C", repo, "commit", "-m", "知识：知识点 %s（%d 条，自动导出）" % (day, len(nodes))],
                ["git", "-C", repo, "push", "origin", "HEAD"]]
        for c in cmds:
            r = sp.run(c, capture_output=True, text=True)
            print("$ " + " ".join(c[:3]) + " → rc=%d %s" % (r.returncode, (r.stdout or r.stderr).strip()[:120]))


# ---------- 批量导入（知识原文） ----------

def cmd_ingest(a):
    import glob as _glob
    dirs = a.dirs or []
    files = []
    for d in dirs:
        files.extend(sorted(_glob.glob(os.path.join(d, "*.md"))))
    if a.pattern:
        files = [f for f in files if a.pattern in os.path.basename(f)]
    if not files:
        print("没有找到文件")
        return

    nodes = load(NODES)
    have = {n.get("artifact") for n in nodes if n.get("artifact")}
    todo = [f for f in files if f not in have]
    print("候选 %d 篇，已入库 %d，本次 %d" % (len(files), len(files) - len(todo), len(todo)))
    if not todo:
        return

    idf, _ = build_idf(nodes)
    added = linked = 0
    for f in todo:
        try:
            text = open(f, encoding="utf-8", errors="replace").read()
        except OSError as e:
            print("  跳过 %s（%s）" % (os.path.basename(f), e))
            continue
        if a.max_chars and len(text) > a.max_chars:
            text = text[:a.max_chars] + "\n…（截断）"
        title = os.path.splitext(os.path.basename(f))[0]
        ts = now_iso()
        node = {
            "id": nid(ts + f, title), "ts": ts, "kind": a.kind, "title": title,
            "detail": text, "artifact": f, "status": "done",
            "tags": [t.strip() for t in (a.tags or "").split(",") if t.strip()],
            "basis": [], "author": "owner", "weight": 1.0,
        }
        edges = link_new(node, nodes, idf)
        append(NODES, node)
        nodes.append(node)
        for e in edges:
            append(EDGES, e)
        added += 1
        linked += len(edges)
        print("  + %s（%d 字，%d 条突触）" % (title[:34], len(text), len(edges)))
    print("\n入库 %d 篇，新增突触 %d 条" % (added, linked))


# ---------- 规则（唯一源 规则.md） ----------

LAW_FILE = os.path.join(BASE, "规则.md")


def _law_lines():
    if not os.path.exists(LAW_FILE):
        return []
    out, on = [], False
    for ln in open(LAW_FILE, encoding="utf-8").read().splitlines():
        if ln.startswith("## "):
            on = True
            out.append("")
            out.append(ln)
            continue
        if on and ln.strip():
            out.append(ln)
    return out


def cmd_law(a):
    if a.id:
        key = a.id.upper()
        hit = [ln for ln in _law_lines() if key in ln.upper()]
        print("\n".join(hit) if hit else "没有这条规则：" + a.id)
        return
    print("=== 矩阵规则（改规则请改 规则.md 并记节点）===")
    print("\n".join(_law_lines()))


# ---------- 并行碰撞（两条线同时跑） ----------

def cmd_forge(a):
    """一次出两条线：多维铺开（clash）+ 立场拷问（spar），再给三份可并行派发的 brief。"""
    import io
    from contextlib import redirect_stdout

    q = a.query
    print("=" * 8 + " 并行碰撞 · " + q + " " + "=" * 8)
    print()

    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_clash(argparse.Namespace(query=q, pool=a.pool))
    print(buf.getvalue().strip())
    print()

    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_spar(argparse.Namespace(query=q, pool=a.pool))
    print(buf.getvalue().strip())
    print()

    print("=" * 8 + " 可并行派发的三份 brief " + "=" * 8)
    print("（三个一起发，各写各的，回来我合并裁决；不发也行，上面两份自己已经能对撞）")
    print()
    for role, extra in (
        ("主张", "给出为什么该做，最多三条理由，每条要能指到具体证据；不许说「有前景」这类空话。"),
        ("红队", "专门找它死在哪：前提不成立、代价被低估、证据是昨天的。每条要有反例或可验证的检查点。"),
        ("第三方", "你不关心成败，只问：这解决谁的问题？他自己知道吗？不做会怎样，那个后果真会发生吗？"),
    ):
        print("--- [%s] ---" % role)
        print("命题：%s" % q)
        print("立场：%s" % extra)
        print("规则：只能用可验证的事实；没有证据就写「没有证据」；不要复述命题。")
        print()
    print("合并规则：三方都同意的才进结论；两方同意的标「大概率」；只有一方说的标「待验」。")


# ---------- 思考模式（按紧急分级） ----------

def _level_of(q):
    low = q.lower()
    hard = ("删除", "发布", "对外", "承诺", "付款", "付费", "上线", "改结构", "重构", "广播",
            "发给", "群发", "发送", "提交", "所有人的", "每个人", "publish", "delete", "send")
    fire = ("挂了", "崩了", "正在丢", "报错", "紧急", "马上", "立刻", "有人在等", "止血")
    if any(w in low for w in hard):
        return "L3", "重：不可逆或对外"
    if any(w in low for w in fire):
        return "L0", "火：正在流血"
    if any(w in low for w in ("调研", "设计", "方案", "架构", "写一份", "评估")):
        return "L2", "常：要比较"
    return "L1", "急：路径已知"


def cmd_pace(a):
    lv, why = _level_of(a.what)
    print("=== %s · %s · %s ===" % (a.what[:40], lv, why))
    plans = {
        "L0": ["只调用已固化的判据（ops / failures），最短路径止血",
               "不发明新方法、不做架构改动、不顺手重构",
               "止血后必须补一条：为什么会流血"],
        "L1": ["brief 一次（3 秒）→ 查该类 ops 判据 → 直接做",
               "不做方案比较，不扩大范围",
               "做完记一行，带 artifact"],
        "L2": ["brief → 列两三条路径 → 比较代价与可逆性 → 选一条",
               "写下 basis：依据哪几个节点",
               "做完验证，再记矩阵"],
        "L3": ["多视角看一遍：我在哪、对方在哪、旁观者怎么看、以前发生过什么、以后会怎样",
               "先找反例：什么情况下这个决定是错的",
               "预演失败：错了怎么退回来（备份 / 回滚 / 降级）",
               "过 gate，再动手"],
    }
    for i, step in enumerate(plans[lv], 1):
        print("  %d. %s" % (i, step))
    if lv == "L0":
        print("  提醒：紧急不等于不思考，只许用练过的动作。")


# ---------- 操作判据（管工具与联网） ----------

OPS_FILE = os.path.join(BASE, "ops.md")
OPS_MAP = {
    "net": "一、联网", "down": "一、联网", "api": "一、联网", "联网": "一、联网", "下载": "一、联网",
    "send": "二、发送", "publish": "二、发送", "发消息": "二、发送", "发布": "二、发送",
    "fs": "三、写文件", "write": "三、写文件", "delete": "三、写文件", "删除": "三、写文件", "覆盖": "三、写文件",
    "pkg": "四、装依赖", "pip": "四、装依赖", "apt": "四、装依赖", "安装": "四、装依赖",
    "job": "五、长任务", "后台": "五、长任务",
    "phone": "六、手机操控", "手机": "六、手机操控",
    "cron": "七、定时任务", "定时": "七、定时任务",
}


def _section(title):
    """从 ops.md 里取出某一节的正文。"""
    if not os.path.exists(OPS_FILE):
        return ""
    lines = open(OPS_FILE, encoding="utf-8").read().splitlines()
    out, on = [], False
    for ln in lines:
        if ln.startswith("## "):
            on = ln[3:].strip().startswith(title)
            continue
        if on:
            out.append(ln)
    return "\n".join(out).strip()


def cmd_ops(a):
    key = a.kind.strip().lower()
    title = OPS_MAP.get(key, OPS_MAP.get(a.kind, ""))
    if not title:
        print("可查的类型：" + " / ".join(sorted(set(OPS_MAP))))
        return
    print("=== 操作判据：%s ===" % title)
    print(_section(title) or "（这一类还没有判据，先按最保守做，做完补进 ops.md）")


def cmd_gate(a):
    """不可逆操作前的最后一道自检：判据 + 旧节点 + 确认。"""
    q = a.what
    kind = a.kind
    if not kind:
        low = q.lower()
        if any(w in low for w in ("删除", "delete", "rm ")):
            kind = "delete"
        elif any(w in low for w in ("发送", "发布", "广播", "msg", "publish")):
            kind = "send"
        elif any(w in low for w in ("下载", "联网", "curl", "http")):
            kind = "net"
        elif any(w in low for w in ("安装", "pip", "apt")):
            kind = "pkg"
        else:
            kind = "fs"
    cmd_ops(argparse.Namespace(kind=kind))
    print()
    print("=== 相关旧节点 ===")
    cmd_think(argparse.Namespace(query=q, n=3))
    print()
    print("=== 停一下 ===")
    print("  这件事可逆吗？不可逆 → 有没有备份/回滚路径？")
    print("  证据在哪？本机能找到产物或日志吗？")
    print("  确认了再动手；拿不准就说出「拿不准」。")


# ---------- 想事情（激活扩散） ----------

def cmd_think(a, by_time=False):
    nodes = load(NODES)
    edges = load(EDGES)
    if not nodes:
        print("脑子是空的")
        return
    idf, _ = build_idf(nodes)
    q = {"title": a.query, "detail": "", "tags": []}
    qv = vec(q, idf)

    scores = {}
    for n in nodes:
        s = cosine(qv, vec(n, idf))
        if s > 0.06:
            scores[n["id"]] = s
    if not scores:
        print("（没激活任何节点：换个线索词）")
        return

    seeds = sorted(scores.items(), key=lambda x: -x[1])[:5]
    adj = collections.defaultdict(list)
    for e in edges:
        adj[e["a"]].append((e["b"], e["w"], e["why"]))
        adj[e["b"]].append((e["a"], e["w"], e["why"]))

    # 主题命中：查询里出现主题名，就把该主题下的知识点整批拉进来（M=0.45）
    topics = {n.get("topic") for n in nodes if n.get("topic")}
    hit_topics = [t for t in topics if t and t in a.query]
    for n in nodes:
        if n.get("topic") in hit_topics:
            scores[n["id"]] = max(scores.get(n["id"], 0), 0.45)

    activated = dict(scores)
    why = {nid_: "seed:%.2f" % s for nid_, s in seeds}
    for n in nodes:
        if n.get("topic") in hit_topics:
            why.setdefault(n["id"], "topic:" + str(n.get("topic")))
    for sid, s in seeds:                       # 沿突触扩散一跳
        for nbr, w, reason in adj[sid]:
            spread = s * w * 0.6
            if activated.get(nbr, 0) < spread:
                activated[nbr] = spread
                why[nbr] = "via %s (%s)" % (sid, reason)

    byid = {n["id"]: n for n in nodes}
    ranked = sorted(activated.items(), key=lambda x: -x[1])[:a.n]
    if by_time:
        ranked.sort(key=lambda x: byid[x[0]]["ts"], reverse=True)

    today = datetime.date.today().isoformat()
    expired = {n["id"] for n in nodes if n.get("kind") == "情报" and n.get("expires") and n["expires"] < today}
    for eid in expired:
        if eid in activated:
            activated[eid] *= 0.4          # 过期情报降权，但不删
    ranked = sorted(activated.items(), key=lambda x: -x[1])[:a.n]
    if by_time:
        ranked.sort(key=lambda x: byid[x[0]]["ts"], reverse=True)
    print("激活 %d 个节点（给你看 %d 个）\n" % (len(activated), len(ranked)))
    for nid_, s in ranked:
        n = byid[nid_]
        print("%.2f  %s · %s · %s" % (s, n["ts"][:16].replace("T", " "), n["kind"], n["title"]))
        if n.get("detail"):
            print("      " + n["detail"][:120])
        if n.get("artifact"):
            print("      → " + n["artifact"])
        print("      连上：%s" % why.get(nid_, ""))


def cmd_neighbors(a):
    nodes = load(NODES)
    edges = load(EDGES)
    byid = {n["id"]: n for n in nodes}
    hit = byid.get(a.id) or next((n for n in nodes if a.id in n["id"] or a.id in n["title"]), None)
    if not hit:
        sys.exit("找不到节点：" + a.id)
    print("%s · %s" % (hit["kind"], hit["title"]))
    rel = [(e, e["b"] if e["a"] == hit["id"] else e["a"]) for e in edges if hit["id"] in (e["a"], e["b"])]
    for e, other in sorted(rel, key=lambda x: -x[0]["w"]):
        o = byid.get(other, {})
        print("  %.2f  %s  [%s]" % (e["w"], o.get("title", "?"), e["why"]))


def cmd_topic(a):
    nodes = load(NODES)
    t = a.name
    rows = [n for n in nodes if n.get("topic") == t]
    if a.list or not t:
        import collections as _c
        c = _c.Counter(n.get("topic") for n in nodes if n.get("topic"))
        print("主题（知识点数）：")
        for k, v in c.most_common():
            print("  %-8s %d" % (k, v))
        return
    if not rows:
        print("没有这个主题：" + t)
        return
    print("=== %s（%d 条）===" % (t, len(rows)))
    for n in rows:
        sub = ("［" + n["subtopic"] + "］") if n.get("subtopic") else ""
        print("  · " + sub + n.get("title", ""))



def cmd_list(a):
    """列节点（自我唤醒等脚本要用它拿当天素材）。"""
    rows = load(NODES)
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
        print("%s · %s · %s" % (r.get("ts", "")[:16].replace("T", " "), r.get("kind", "?"), r.get("title", "")))


def cmd_stats(a):
    nodes = load(NODES)
    edges = load(EDGES)
    if not nodes:
        print("空")
        return
    deg = collections.Counter()
    for e in edges:
        deg[e["a"]] += 1
        deg[e["b"]] += 1
    byid = {n["id"]: n for n in nodes}
    c = collections.Counter(n.get("kind") for n in nodes)
    print("节点 %d · 突触 %d · 平均度 %.2f · 孤立 %d"
          % (len(nodes), len(edges), 2 * len(edges) / max(len(nodes), 1),
             sum(1 for n in nodes if deg[n["id"]] == 0)))
    print("类型：" + "  ".join("%s %d" % (k, v) for k, v in c.most_common()))
    print("连接最多的：")
    for nid_, d in deg.most_common(5):
        print("  %d 条 · %s" % (d, byid.get(nid_, {}).get("title", "?")))
    days = collections.Counter(n["ts"][:10] for n in nodes)
    print("最近几天：" + "  ".join("%s %d" % (k, v) for k, v in sorted(days.items())[-5:]))
    # 记忆分层：普通 AI 只有工作记忆（上下文），矩阵有下面这些
    layer = {"情景": ("事件", "活动", "对话"), "语义": ("思考", "决定"), "程序": ("产出", "任务")}
    tally = collections.Counter()
    for n in nodes:
        for name, kinds in layer.items():
            if n.get("kind") in kinds:
                tally[name] += 1
    print("记忆分层：" + "  ".join("%s %d" % (k, tally.get(k, 0)) for k in ("情景", "语义", "程序"))
          + "  ｜ 工作记忆（上下文）不在矩阵里，窗口一关就没")


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
    p.add_argument("--basis", default="", help="这条判断依据的节点 id，逗号分隔")
    p.add_argument("--author", default="owner", choices=["owner", "visitor"])
    p.add_argument("--expires", default="", help="情报过期日 YYYY-MM-DD")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("think")
    p.add_argument("query")
    p.add_argument("--n", type=int, default=8)
    p.set_defaults(fn=cmd_think)
    p = sub.add_parser("recall")
    p.add_argument("query")
    p.add_argument("--n", type=int, default=8)
    p.set_defaults(fn=lambda a: cmd_think(a, by_time=True))
    p = sub.add_parser("neighbors")
    p.add_argument("id")
    p.set_defaults(fn=cmd_neighbors)
    p = sub.add_parser("brief")
    p.add_argument("query")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--pits", type=int, default=4)
    p.add_argument("--log", action="store_true", help="把这次过脑记成节点")
    p.set_defaults(fn=cmd_brief)
    p = sub.add_parser("habit")
    p.add_argument("action", choices=["add", "list", "run"])
    p.add_argument("name", nargs="?", default="")
    p.add_argument("--cmd", default="")
    p.add_argument("--check", default="")
    p.set_defaults(fn=cmd_habit)
    p = sub.add_parser("tint")
    p.add_argument("--days", type=int, default=7)
    p.set_defaults(fn=cmd_tint)
    p = sub.add_parser("conflict")
    p.add_argument("what")
    p.add_argument("--days", type=int, default=7)
    p.set_defaults(fn=cmd_conflict)
    p = sub.add_parser("dream")
    p.add_argument("--decay", type=float, default=0.97)
    p.add_argument("--min-edge", type=float, default=0.32)
    p.set_defaults(fn=cmd_dream)
    p = sub.add_parser("brainbrief")
    p.add_argument("query", nargs="?", default="")
    p.set_defaults(fn=cmd_brainbrief)
    p = sub.add_parser("audit")
    p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("trim")
    p.add_argument("--keep", type=int, default=200)
    p.set_defaults(fn=cmd_trim)
    p = sub.add_parser("export")
    p.add_argument("--out", default="")
    p.add_argument("--since", default="")
    p.add_argument("--push", action="store_true")
    p.set_defaults(fn=cmd_export)
    p = sub.add_parser("ingest")
    p.add_argument("dirs", nargs="*")
    p.add_argument("--kind", default="知识")
    p.add_argument("--tags", default="知识")
    p.add_argument("--pattern", default="")
    p.add_argument("--max-chars", type=int, default=20000)
    p.set_defaults(fn=cmd_ingest)
    p = sub.add_parser("law")
    p.add_argument("id", nargs="?", default="")
    p.set_defaults(fn=cmd_law)
    p = sub.add_parser("forge")
    p.add_argument("query")
    p.add_argument("--pool", type=int, default=8)
    p.set_defaults(fn=cmd_forge)
    p = sub.add_parser("spar")
    p.add_argument("query")
    p.add_argument("--pool", type=int, default=8)
    p.set_defaults(fn=cmd_spar)
    p = sub.add_parser("clash")
    p.add_argument("query")
    p.add_argument("--pool", type=int, default=12)
    p.set_defaults(fn=cmd_clash)
    p = sub.add_parser("pace")
    p.add_argument("what")
    p.set_defaults(fn=cmd_pace)
    p = sub.add_parser("ops")
    p.add_argument("kind")
    p.set_defaults(fn=cmd_ops)
    p = sub.add_parser("gate")
    p.add_argument("what")
    p.add_argument("--kind", default="")
    p.set_defaults(fn=cmd_gate)
    p = sub.add_parser("list")
    p.add_argument("--today", action="store_true")
    p.add_argument("--kind", default="")
    p.add_argument("--n", type=int, default=20)
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("topic")
    p.add_argument("name", nargs="?", default="")
    p.add_argument("--list", action="store_true")
    p.set_defaults(fn=cmd_topic)
    p = sub.add_parser("stats")
    p.set_defaults(fn=cmd_stats)
    p = sub.add_parser("reindex")
    p.set_defaults(fn=cmd_reindex)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
