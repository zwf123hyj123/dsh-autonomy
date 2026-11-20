#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# brain/本地模型学习.py — 本地模型「学习」：知识区条目滚动提炼成学习笔记，调用时注入。
# 环境：BRAIN_ROOT（默认 ~/.dsh/brain）、CTXC_BIN、OLLAMA_URL、BRAIN_MODEL
import os, sys, json, glob, datetime, hashlib, re

HOME = os.path.expanduser('~')
BRAIN = os.environ.get('BRAIN_ROOT', os.path.join(HOME, '.dsh', 'brain'))
KNOW = os.path.join(BRAIN, '知识')
NOTE = os.path.join(BRAIN, '本地模型学习.md')

def main():
    files = sorted(glob.glob(KNOW + '/*.md'))
    files = [f for f in files if '动态' not in f and '约定' not in f and '索引' not in f and '原始' not in f]
    try:
        note = open(NOTE, encoding='utf-8').read()
    except Exception:
        note = ''
    seen = set(re.findall(r'## (.+?)\n', note))
    added = 0
    for f in files:
        title = os.path.basename(f).replace('.md', '')
        if title in seen:
            continue
        txt = open(f, encoding='utf-8').read()
        note = note.rstrip() + '\n\n## %s\n\n%s\n' % (title, txt[:700])
        seen.add(title)
        added += 1
    parts = note.split('## ')
    note = parts[0].rstrip() + '\n\n' + '## ' + '## '.join(parts[1:][-40:])
    if added:
        open(NOTE, 'w', encoding='utf-8').write(note)
    print(json.dumps({'学习条目新增': added, '笔记总条目': max(0, len(parts) - 1)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
