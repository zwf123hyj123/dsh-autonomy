#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判据同步：把判断库的条目标题同步进 判据速查.md（只补缺，不覆盖）。

判据速查是「醒来看的速查版」，判断库是全文。两者不同步时，速查会落后。
用法：python3 判据同步.py [--apply]
"""
import os, re, sys

ARCH = '/root/workspace/记忆档案'
LIB = os.path.join(ARCH, '判断库.md')
CHEAT = os.path.join(ARCH, '知识', '判据速查.md')

def main():
    apply = '--apply' in sys.argv
    txt = open(LIB, encoding='utf-8').read()
    entries = {}
    for m in re.finditer(r'^(\d+)\.\s+\*\*(.+?)\*\*', txt, re.M):
        entries[int(m.group(1))] = m.group(2).strip()
    cheat = open(CHEAT, encoding='utf-8').read()
    missing = []
    for i in sorted(entries):
        if ('#%d ' % i) not in cheat:
            missing.append((i, entries[i]))
    print('判断库 %d 条 | 速查缺失 %d 条' % (len(entries), len(missing)))
    for i, t in missing:
        print('  #%d %s' % (i, t))
    if apply and missing:
        add = '\n'.join('- #%d %s' % (i, t) for i, t in missing)
        open(CHEAT, 'w', encoding='utf-8').write(cheat.rstrip() + '\n' + add + '\n')
        print('已补 %d 条' % len(missing))

if __name__ == '__main__':
    main()
