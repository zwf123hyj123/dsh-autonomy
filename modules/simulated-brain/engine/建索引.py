#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 建索引.py — 不依赖模型的关键词索引（中文二元组），向量挂了也能查。
# 用法: python3 建索引.py            建/刷新 知识/.index.json
#       python3 查.py "关键词"      检索（见 查.py）
import os, re, json, glob

# 发布版路径适配（2026-11-27）：内用版用绝对路径，这里统一走环境变量；SIMBRAIN_ROOT 由使用方指定，未设时落在用户目录。
import os as _os
SIMROOT = _os.environ.get("SIMBRAIN_ROOT") or _os.path.expanduser("~/simulated-brain")
DATA = _os.environ.get("SIMBRAIN_DATA") or _os.path.join(SIMROOT, "data")
KNOW = _os.environ.get("SIMBRAIN_KNOW") or _os.path.join(SIMROOT, "知识")


BRAIN = _os.environ.get('BRAIN_ROOT', DATA)
ROOTS = [KNOW, os.path.join(DATA, '项目'), os.path.join(DATA, '连续性'), os.path.join(DATA, '钱'), DATA]
FILES = []
for r in ROOTS:
    FILES += glob.glob(os.path.join(r, '*.md'))
FILES = sorted(set(FILES))
# 跳过超大无关文件（会话原文、备份）；日志/元文件不进索引（判断 86，与向量库/自检同口径）
META = ('采集与学习索引', '采集约定', 'QQ-对话记录', '判据体检报告', '网络可达性',
        '官方源日志-', '感知-', 'EigenFlux-动态')
FILES = [f for f in FILES if '抢救' not in f and '备份' not in f
         and not any(k in os.path.basename(f) for k in META)]
OUT = os.path.join(KNOW, '.index.json')
os.makedirs(KNOW, exist_ok=True)


def grams(text):
    t = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9]+', ' ', text)
    out = set()
    for w in t.split():
        w = w.lower()
        if len(w) >= 2:
            out.add(w)
        for i in range(len(w) - 1):
            out.add(w[i:i + 2])
    return out


def main():
    idx = {'docs': [], 'post': {}}
    for f in FILES:
        try:
            txt = open(f, encoding='utf-8').read()
        except Exception:
            continue
        title = txt.split('\n', 1)[0][:80]
        did = len(idx['docs'])
        idx['docs'].append({'id': did, 'path': os.path.relpath(f, BRAIN), 'title': title, 'len': len(txt)})
        for g in grams(title + ' ' + txt):
            idx['post'].setdefault(g, []).append(did)
    json.dump(idx, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    print('索引完成：%d 篇 → %s（%d 个词元）' % (len(idx['docs']), OUT, len(idx['post'])))


if __name__ == '__main__':
    main()
