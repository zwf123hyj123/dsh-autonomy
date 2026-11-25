#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 知识检索.py — RAG 检索段：查询 → 向量相似度 top-k（近义可命中；仅检索，不建突触）。
import os, sys, json, math, urllib.request, re

BRAIN = os.environ.get('BRAIN_ROOT', '/root/workspace/记忆档案')
VEC = os.path.join(BRAIN, '知识', '.rag', 'vectors.json')
OLLAMA = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11436')
EMB = os.environ.get('EMB_MODEL', 'nomic-embed-text:latest')  # 2026-11-25 修：缺 :latest 会 400 卡 30 秒

def embed(text):
    body = json.dumps({'model': EMB, 'input': [text]}).encode()
    req = urllib.request.Request(OLLAMA + '/api/embed', data=body,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())['embeddings'][0]

def cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

def fallback(query, topk):
    """ollama 挂掉时的降级：走关键词索引 查.py（2026-11-25 接血管）"""
    import subprocess
    r = subprocess.run(['python3', '/root/workspace/记忆档案/查.py', query],
                       capture_output=True, text=True)
    print('【降级·关键词检索】是' if r.stdout else '【降级失败】' if r.returncode else '')
    print(r.stdout[:1200])
    return 0


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else '上下文压缩'
    topk = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    region = None
    cond = None
    if '--区' in sys.argv:
        i = sys.argv.index('--区')
        region = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    if '--条件' in sys.argv:
        i = sys.argv.index('--条件')
        cond = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    try:
        regions = json.load(open(os.path.join(BRAIN, '知识', '分区.json'), encoding='utf-8'))
    except Exception:
        regions = {}
    def reg_of(item_id):
        for k, v in regions.items():
            if k in item_id:
                return v
        return '未分区'
    # 条件记忆（Engram 启发）：当前心情 + 任务语境对检索加权——记忆按条件召回，不只是按相似度
    mood = ''
    try:
        mood = json.load(open(os.path.join(BRAIN, '连续性', '情感态.json'), encoding='utf-8')).get('mood', '')
    except Exception:
        pass
    def cond_boost(it):
        b = 0.0
        txt = it['id'] + it['text']
        if cond and cond in txt:
            b += 0.04
        if mood and mood in txt:
            b += 0.03  # 情绪一致性的记忆更容易被想起
        if region and reg_of(it['id']) == region:
            b += 0.06
        return b
    store = json.load(open(VEC, encoding='utf-8'))
    qv = embed(query)
    scored = sorted([(cos(qv, it['vec']) + cond_boost(it), it) for it in store['items']], key=lambda x: -x[0])
    if region:
        scored = [(s, it) for s, it in scored if reg_of(it['id']) == region]
    # 2026-11-25 混合检索：nomic 是英文模型，中文语义弱 → 并行跑关键词检索兜底
    import subprocess as _sp
    kw_files = []
    try:
        _r = _sp.run(['python3', '/root/workspace/记忆档案/查.py', query],
                     capture_output=True, text=True, timeout=20)
        for _line in (_r.stdout or '').splitlines():
            _m = re.match(r'^\d+\s+(\S+\.md)', _line)
            if _m:
                kw_files.append(_m.group(1).strip())
    except Exception:
        pass
    seen_ids = set()
    printed = 0
    for s, it in scored[:topk]:
        seen_ids.add(it['id'].split('#')[0])
        print('%.3f | [%s] | %s | %s' % (s, reg_of(it['id']), it['id'], it['text'][:60].replace('\n', ' ')))
        printed += 1
    # 关键词命中但向量没进前 k 的文件，补进来
    for kf in kw_files:
        if printed >= topk + 2:
            break
        kf = kf.replace('知识/', '').replace('.md', '')
        if kf in seen_ids:
            continue
        for it in store['items']:
            if it['id'].startswith(kf + '#'):
                print('KW    | [关键词] | %s | %s' % (it['id'], it['text'][:60].replace('\n', ' ')))
                printed += 1
                break

if __name__ == '__main__':
    main()
