#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 查.py — 关键词检索（二元组打分），不依赖本地模型。
import os, sys, json, re, math

# 发布版路径适配（2026-11-27）：内用版用绝对路径，这里统一走环境变量；SIMBRAIN_ROOT 由使用方指定，未设时落在用户目录。
import os as _os
SIMROOT = _os.environ.get("SIMBRAIN_ROOT") or _os.path.expanduser("~/simulated-brain")
DATA = _os.environ.get("SIMBRAIN_DATA") or _os.path.join(SIMROOT, "data")
KNOW = _os.environ.get("SIMBRAIN_KNOW") or _os.path.join(SIMROOT, "知识")


BRAIN = _os.environ.get('BRAIN_ROOT', DATA)
IDX = os.path.join(KNOW, '.index.json')

def grams(text):
    t = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9]+', ' ', text)
    out = set()
    for w in t.split():
        w = w.lower()
        if len(w) >= 2: out.add(w)
        for i in range(len(w) - 1): out.add(w[i:i+2])
    return out

def main():
    q = ' '.join(sys.argv[1:]) or '情报'
    idx = json.load(open(IDX, encoding='utf-8'))
    docs, post = idx['docs'], idx['post']
    score = {}
    for g in grams(q):
        for d in post.get(g, []):
            score[d] = score.get(d, 0) + 1
    if not score:
        print('没命中'); return
    n = len(docs)
    ranked = sorted(score.items(), key=lambda kv: -kv[1])[:8]
    for d, s in ranked:
        doc = docs[d]
        idf = math.log(1 + n / (1 + len(post.get(next(iter(grams(q))), []))))
        print('%-4d %-52s %s' % (s, doc['path'], doc['title'][:40]))

if __name__ == '__main__':
    main()
