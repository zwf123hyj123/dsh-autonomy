#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量消化：把待消化知识按类型自动处置，剩下真正要「记」的留给人/agent。

规则：
- 情报/数据类（会过期）→ keep（留知识层按需检索）
- 过短（<120 字）→ drop（无价值）
- 方法/判据/结论类 → 标记 pending_remember（需要真正 remember）
用法：python3 批量消化.py [--apply]
"""
import os, json, sys, re, time, glob

ARCH = '/root/workspace/记忆档案'
KNOW = os.path.join(ARCH, '知识')
STATE = os.path.join(KNOW, '.digested.json')

INTEL = re.compile(r'情报|官方源|点位|缺口|运价|指数|股市|制裁|仓位|动态')
JUDGE = re.compile(r'判据|方法|原则|教训|结论|判断|规律')
TABLE = re.compile(r'^\|', re.M)

def main():
    apply = '--apply' in sys.argv
    try:
        d = json.load(open(STATE))
    except Exception:
        d = {}
    week = [f for f in glob.glob(KNOW + '/*.md') if os.path.getmtime(f) >= time.time() - 7 * 86400]
    pending = [f for f in week if os.path.basename(f) not in d]
    plan = []
    for f in pending:
        name = os.path.basename(f)
        try:
            txt = open(f, encoding='utf-8').read()
        except Exception:
            continue
        if len(txt) < 120:
            plan.append((name, 'drop', '过短'))
        elif INTEL.search(name) or len(TABLE.findall(txt)) > 6:
            plan.append((name, 'keep', '情报/数据类'))
        elif JUDGE.search(txt):
            plan.append((name, 'pending_remember', '方法/判据/结论'))
        else:
            plan.append((name, 'keep', '普通资料'))
    if apply:
        for name, action, _ in plan:
            d[name] = {'action': action if action != 'pending_remember' else 'pending',
                       'at': time.strftime('%Y-%m-%d %H:%M:%S')}
        tmp = STATE + '.tmp'
        json.dump(d, open(tmp, 'w'), ensure_ascii=False, indent=1)
        os.replace(tmp, STATE)
    from collections import Counter
    c = Counter(a for _, a, _ in plan)
    print(json.dumps({
        '待处理': len(plan),
        '自动处置': dict(c),
        '需要remember': [n for n, a, _ in plan if a == 'pending_remember'][:15],
        '已写入': apply,
    }, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()
