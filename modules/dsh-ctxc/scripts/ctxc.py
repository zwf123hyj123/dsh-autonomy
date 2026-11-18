#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ctxc.py v3 — 断点压缩：按功能/上下文分段；大段总结、小段原样；进度落盘，中断后续传。
# 参考断点下载：每完成一段立刻写盘，重跑只处理未完成的段（同一输入按内容哈希续传）。
#
# 用法:
#   python3 ctxc.py 文件.md                     # 分段压缩，自动断点续传
#   cat 长文.txt | python3 ctxc.py --keep-paths
#   python3 ctxc.py 文件.md --fresh             # 放弃旧进度重压
# 环境变量:
#   CTXC_API / CTXC_MODEL       本地端点与模型（默认 127.0.0.1:11436 / qwen2.5:1.5b-instruct）
#   CTXC_LOCAL_MAX              本地最多压多少字（默认 2600，超出上云）
#   CTXC_SMALL_KEEP             多少字以下原样保留（默认 120）
#   CTXC_STATE_DIR              断点状态目录（默认 /tmp/ctxc-state）
#   CTXC_CLOUD_API/KEY/MODEL    云端端点（缺省走 dsh-our-free-model 网关自动切换）
import sys, json, os, re, hashlib, argparse, time
from concurrent.futures import ThreadPoolExecutor
import urllib.request

LOCAL_API = os.environ.get("CTXC_API", "http://127.0.0.1:11436/v1/chat/completions")
LOCAL_MODEL = os.environ.get("CTXC_MODEL", "qwen2.5:1.5b-instruct")
LOCAL_MAX = int(os.environ.get("CTXC_LOCAL_MAX", "2600"))
SMALL_KEEP = int(os.environ.get("CTXC_SMALL_KEEP", "120"))
STATE_DIR = os.environ.get("CTXC_STATE_DIR", "/tmp/ctxc-state")
LOCAL_CHUNK = 380
CLOUD_CHUNK = 1500
CLOUD_API = os.environ.get("CTXC_CLOUD_API", "")
CLOUD_KEY = os.environ.get("CTXC_CLOUD_KEY", "")
CLOUD_MODEL = os.environ.get("CTXC_CLOUD_MODEL", "")
OFM_SETTINGS = os.path.expanduser("~/.dsh/our-free-model/settings.json")
SYSTEM = "你是上下文压缩器。把输入压缩成中文要点，每点不超过20字；保留数字、名称、结论，去掉客套与重复。只输出要点，不要解释。"

def resolve_cloud():
    if CLOUD_API:
        return CLOUD_API, CLOUD_KEY, CLOUD_MODEL or "kilo-auto/free"
    try:
        j = json.load(open(OFM_SETTINGS))
        relay = j.get("chanGateway", {}).get("relay", {})
        if relay.get("enabled"):
            api = "http://%s:%s/v1/chat/completions" % (
                relay.get("host", "127.0.0.1"), relay.get("port", 18326))
            return api, relay.get("key", ""), CLOUD_MODEL or "kilo-auto/free"
    except Exception:
        pass
    return "", "", ""

def segment(text):
    """按功能/上下文分段：标题起新段；空行分段；小碎块合并；不打断语义单元。"""
    raw = []
    buf = []
    for line in text.splitlines():
        is_head = re.match(r"^#{1,6}\s", line) is not None
        if (is_head or line.strip() == "") and buf:
            raw.append("\n".join(buf).strip())
            buf = []
        if line.strip():
            buf.append(line)
    if buf:
        raw.append("\n".join(buf).strip())
    # 合并小碎块（<40 字并入后一段），标题段不合并
    merged = []
    i = 0
    while i < len(raw):
        seg = raw[i]
        is_head = re.match(r"^#{1,6}\s", seg) is not None
        if not is_head and len(seg) < 40 and merged:
            merged[-1] = merged[-1] + "\n" + seg
        else:
            merged.append(seg)
        i += 1
    return [s for s in merged if s]

def sub_chunk(seg, cap):
    if len(seg) <= cap:
        return [seg]
    parts = re.split(r"(?<=[。！？；])", seg)
    out, cur = [], ""
    for p in parts:
        if len(cur) + len(p) > cap and cur:
            out.append(cur)
            cur = p
        else:
            cur += p
    if cur:
        out.append(cur)
    return out

def call(api, key, model, chunk, timeout=90):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": chunk},
        ],
        "max_tokens": 90,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(api, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        j = json.loads(r.read().decode("utf-8"))
    return (j["choices"][0]["message"].get("content") or "").strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="文件（缺省读 stdin）")
    ap.add_argument("--keep-paths", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="放弃旧进度重压")
    ap.add_argument("--no-hybrid", action="store_true")
    args = ap.parse_args()

    if args.file:
        src = "file:" + args.file
        text = open(args.file, encoding="utf-8").read()
    else:
        src = "stdin"
        text = sys.stdin.read()

    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    os.makedirs(STATE_DIR, exist_ok=True)
    state_path = os.path.join(STATE_DIR, h + ".json")

    def load_state():
        try:
            return json.load(open(state_path))
        except Exception:
            return None

    def save_state(state):
        tmp = state_path + ".tmp"
        json.dump(state, open(tmp, "w"), ensure_ascii=False)
        os.replace(tmp, state_path)

    # ── 建立/恢复单元列表（断点续传核心）────────────────────
    segs = segment(text)
    state = None if args.fresh else load_state()
    if state and state.get("units") is not None and state.get("count") == len(segs):
        units = state["units"]
        for u, s in zip(units, segs):
            u["text"] = s  # 以当前输入为准
        print("[ctxc] 断点续传：%d/%d 段已完成" % (
            sum(1 for u in units if u.get("done")), len(units)), file=sys.stderr)
    else:
        units = [{
            "i": i,
            "kind": "keep" if len(s) <= SMALL_KEEP else "compress",
            "text": s,
            "out": "" if len(s) <= SMALL_KEEP else None,
            "done": len(s) <= SMALL_KEEP,  # 小段原样，直接完成
        } for i, s in enumerate(segs)]
        save_state({"count": len(segs), "units": units, "src": src})
        print("[ctxc] 分段完成：%d 段（保留 %d / 压缩 %d）" % (
            len(segs),
            sum(1 for u in units if u["kind"] == "keep"),
            sum(1 for u in units if u["kind"] == "compress")), file=sys.stderr)

    # ── 路由：压缩段按本地预算分配 ─────────────────────────
    local_units, cloud_units, acc = [], [], 0
    for u in units:
        if u["kind"] != "compress" or u["done"]:
            continue
        if acc + len(u["text"]) <= LOCAL_MAX:
            local_units.append(u)
            acc += len(u["text"])
        else:
            cloud_units.append(u)

    cloud_api, cloud_key, cloud_model = resolve_cloud()
    use_cloud = bool(cloud_units) and bool(cloud_api) and not args.no_hybrid

    def unit_done(u, out):
        u["out"] = out
        u["done"] = True
        save_state({"count": len(units), "units": units, "src": src})

    def compress_unit(u, api, key, model, cap):
        outs = []
        for c in sub_chunk(u["text"], cap):
            outs.append(call(api, key, model, c))
        unit_done(u, "\n".join(outs))
        return u["out"]

    t0 = time.time()
    if use_cloud:
        def run_local():
            for u in local_units:
                compress_unit(u, LOCAL_API, "", LOCAL_MODEL, LOCAL_CHUNK)
                print("[ctxc] 本地段完成 (%d 字)" % len(u["text"]), file=sys.stderr)
        def run_cloud():
            models = [cloud_model]
            try:
                req = urllib.request.Request(
                    cloud_api.rsplit("/chat/completions", 1)[0] + "/models",
                    headers={"Authorization": "Bearer " + cloud_key} if cloud_key else {})
                with urllib.request.urlopen(req, timeout=20) as r:
                    j = json.loads(r.read().decode("utf-8"))
                for m in j.get("data", []):
                    if m.get("id") and m["id"] not in models:
                        models.append(m["id"])
            except Exception:
                pass
            for u in cloud_units:
                ok = False
                for m in models[:4]:
                    try:
                        compress_unit(u, cloud_api, cloud_key, m, CLOUD_CHUNK)
                        print("[ctxc] 云端段完成 (%d 字, %s)" % (len(u["text"]), m), file=sys.stderr)
                        ok = True
                        break
                    except Exception:
                        continue
                if not ok:
                    unit_done(u, "[云端压缩失败（已试自动切换）] 原文见: %s" % src)
        with ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(run_local)
            f2 = ex.submit(run_cloud)
            f1.result()
            f2.result()
    else:
        for u in local_units:
            compress_unit(u, LOCAL_API, "", LOCAL_MODEL, LOCAL_CHUNK)
            print("[ctxc] 本地段完成 (%d 字)" % len(u["text"]), file=sys.stderr)
        for u in cloud_units:
            unit_done(u, "[超出本地容量，云端未配置] 原文见: %s\n%s" % (src, u["text"]))

    # ── 输出 ──────────────────────────────────────────────
    if args.keep_paths:
        print("# 来源: %s" % src)
    for u in units:
        if u["kind"] == "keep":
            print("· " + u["text"].replace("\n", " ")[:200])
        else:
            print(u["out"] or "")
    print("[ctxc] 完成：保留 %d / 本地 %d / 云端 %d，耗时 %.1fs（断点状态: %s）" % (
        sum(1 for u in units if u["kind"] == "keep"),
        len(local_units), len(cloud_units) if use_cloud else 0,
        time.time() - t0, state_path), file=sys.stderr)

if __name__ == "__main__":
    main()
