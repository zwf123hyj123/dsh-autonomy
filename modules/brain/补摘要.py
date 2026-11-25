#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补摘要：给「摘要未生成（压缩失败）」的知识条目补规则摘要（不依赖模型）。

规则：原文前 200 字作导语 + 含数字/结论的句子最多 3 句。
标注「规则摘要（模型压缩失败，规则兜底）」，不冒充模型摘要。
"""
import os, re, glob, json

ARCH = '/root/workspace/记忆档案'
KNOW = os.path.join(ARCH, '知识')
RAW = os.path.join(KNOW, '原始')

def extract(raw_text):
    t = re.sub(r'\s+', ' ', raw_text).strip()
    lead = t[:200]
    sents = re.split(r'(?<=[。！？；])', t)
    picks = []
    for s in sents:
        s = s.strip()
        if 20 <= len(s) <= 160 and re.search(r'\d|结论|说明|表明|发现|建议|方法|机制', s):
            if s not in lead:
                picks.append(s)
        if len(picks) >= 3:
            break
    return lead + ('\n\n关键句：\n' + '\n'.join('- ' + p for p in picks) if picks else '')

def main():
    fixed = []
    for f in glob.glob(KNOW + '/*.md'):
        try:
            txt = open(f, encoding='utf-8').read()
        except Exception:
            continue
        if '摘要未生成' not in txt:
            continue
        # 找原文路径
        m = re.search(r'原文[:：]\s*(\S+\.md)', txt)
        if not m:
            continue
        raw_path = m.group(1)
        if not os.path.isabs(raw_path):
            raw_path = os.path.join(ARCH, raw_path)
        if not os.path.exists(raw_path):
            continue
        raw = open(raw_path, encoding='utf-8', errors='ignore').read()
        if len(raw.strip()) < 100:
            continue
        summary = extract(raw)
        new = txt.replace('摘要未生成（压缩失败），原文已归档。',
                          '**规则摘要（模型压缩失败，规则兜底）**：\n\n' + summary)
        if new != txt:
            open(f, 'w', encoding='utf-8').write(new)
            fixed.append(os.path.basename(f))
    print(json.dumps({'补摘要': len(fixed), '清单': fixed}, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()
