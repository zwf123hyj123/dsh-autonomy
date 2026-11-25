#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识摘要：把所有「已消化且有自己总结」的条目，导出成一份可撞、可调用的清单。

引路人的话（2026-11-25）：「只有知识是自己总结的才好撞，且总结的知识更方便云端上下调用」。
所以这份清单只收 summary（自己的话），不收原文。
"""
import os, json, time

ARCH = '/root/workspace/记忆档案'
KNOW = os.path.join(ARCH, '知识')
STATE = os.path.join(KNOW, '.digested.json')
OUT = os.path.join(KNOW, '我的总结.md')

def main():
    try:
        d = json.load(open(STATE))
    except Exception:
        d = {}
    rows = [(k, v) for k, v in d.items() if v.get('summary')]
    rows.sort(key=lambda kv: kv[0])
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('# 我的总结（可撞、可调用）\n\n')
        f.write('> 只收自己写过 summary 的条目；原文留在知识层，这里只放「我的话」。\n')
        f.write('> 生成时间：%s；条目数：%d\n\n' % (time.strftime('%Y-%m-%d %H:%M'), len(rows)))
        for name, v in rows:
            f.write('## %s\n' % name)
            f.write('- 处置：%s ｜ 时间：%s\n' % (v.get('action'), v.get('at')))
            f.write('- **我的总结**：%s\n\n' % v['summary'])
    print(json.dumps({'有条目的总结了': len(rows), '输出': os.path.basename(OUT)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
