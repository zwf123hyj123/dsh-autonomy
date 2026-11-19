#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 摇酒.py — 模拟大脑子项目「调酒器」的摇酒引擎。
# 基酒=七情六欲；原料=人物设定卡；摇酒=分析想法选基酒（相关/随机/可调）→ 出配方 → 文案由主人侧模型按配方生成。
import json, os, sys, random, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
BASES = json.load(open(os.path.join(HERE, '基酒.json'), encoding='utf-8'))
KEYS = {}
for cat in ('七情', '六欲'):
    for k, v in BASES[cat].items():
        KEYS[k] = {**v, 'cat': cat}

HINTS = {
    '开心': ['喜'], '高兴': ['喜'], '快乐': ['喜'], '哈哈': ['喜'], '爽': ['喜'],
    '生气': ['怒'], '气死': ['怒'], '烦': ['怒'], '讨厌': ['怒'], '火大': ['怒'],
    '累': ['忧'], '疲惫': ['忧'], '焦虑': ['忧', '恐'], '担心': ['忧'], '难过': ['悲', '忧'],
    '伤心': ['悲'], '哭': ['悲'], '想': ['思'], '思考': ['思'], '迷茫': ['思', '忧'],
    '怕': ['恐'], '吓': ['惊', '恐'], '哇': ['惊'], '震惊': ['惊'],
    '想吃': ['味欲'], '香': ['香欲'], '听': ['听欲'], '看': ['见欲'], '碰': ['触欲'], '想要': ['意欲'],
}

def classify(text):
    found = []
    for hint, ks in HINTS.items():
        if hint in text:
            for k in ks:
                if k not in found:
                    found.append(k)
    return found

def pick_bases(found, mode, n=3):
    if mode == 'random':
        return random.sample(list(KEYS), n)
    if mode == 'unrelated':
        # 相关 1 个 + 不相关 2 个（可调）
        rel = found[:1] or [random.choice(list(KEYS))]
        rest = [k for k in KEYS if k not in rel]
        return rel + random.sample(rest, n - 1)
    # related / auto：相关优先，不足随机补
    out = found[:]
    rest = [k for k in KEYS if k not in out]
    random.shuffle(rest)
    while len(out) < n and rest:
        out.append(rest.pop())
    return out[:n]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('idea', help='想法/心情原文')
    ap.add_argument('--原料', default='无', help='人物设定卡名')
    ap.add_argument('--mode', choices=['auto', 'related', 'random', 'unrelated'], default='auto')
    ap.add_argument('--base', default='', help='指定基酒（逗号分隔，可调）')
    ap.add_argument('--ratio', default='3:2:1', help='混合比例')
    args = ap.parse_args()

    found = classify(args.idea)
    if args.base:
        bases = [b for b in args.base.split(',') if b in KEYS]
        if not bases:
            print(json.dumps({'错误': '基酒名无效，可用: ' + '、'.join(KEYS)}, ensure_ascii=False)); return
    else:
        bases = pick_bases(found, args.mode)

    parts = args.ratio.split(':')
    recipe = {
        '想法': args.idea,
        '情绪识别': found or ['（无明确情绪，随机补基）'],
        '原料': args.原料,
        '基酒': [{'名': b, '类': KEYS[b]['cat'], '风味': KEYS[b]['风味'], 'emoji': KEYS[b]['emoji']} for b in bases],
        '比例': args.ratio,
        '调制说明': '，'.join('%s %s 份' % (b, p) for b, p in zip(bases, parts + ['1'] * len(bases))) + '（基酒可按心情替换，可调）',
    }
    print(json.dumps(recipe, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()
