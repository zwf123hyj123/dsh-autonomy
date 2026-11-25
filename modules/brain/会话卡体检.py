#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会话卡体检：检查会话卡是否对应活着的会话；死链加标记（不删，反幻门：原始记录不改）。

用法：python3 会话卡体检.py [--apply]
"""
import os, sys, glob, json

ARCH = '/root/workspace/记忆档案'
CARDS = os.path.join(ARCH, '连续性', '会话卡')
SESS = os.path.expanduser('~/.dsh/sessions')
REPORT = os.path.join(CARDS, '死链报告-2026-11-25.md')
MARK = '> ⚠ 原会话已不存在'

def session_exists(sid13):
    return bool(glob.glob(os.path.join(SESS, '*', 'session-' + sid13 + '*')))

def main():
    apply = '--apply' in sys.argv
    cards = sorted(glob.glob(os.path.join(CARDS, 'session-*.md')))
    dead = []
    for f in cards:
        sid = os.path.basename(f)[:-3].replace('session-', '')
        if not session_exists(sid):
            dead.append((f, sid))
    marked = 0
    if apply:
        for f, sid in dead:
            try:
                txt = open(f, encoding='utf-8').read()
            except Exception:
                continue
            if MARK in txt:
                continue
            rescue = glob.glob(os.path.join(ARCH, '抢救', 'session-' + sid + '-*')) + glob.glob(os.path.join(ARCH, '抢救', sid + '-*'))
            note = '%s（2026-11-25 检查）%s\n\n' % (MARK, ('；抢救件：' + '、'.join(os.path.basename(r) for r in rescue[:3])) if rescue else '；无抢救件')
            open(f, 'w', encoding='utf-8').write(note + txt)
            marked += 1
        lines = ['# 会话卡死链报告（2026-11-25）\n', '> 只标记不删除（反幻门：原始记录不改）。\n',
                 '| 会话卡 | 原会话 | 抢救件 |', '|---|---|---|']
        for f, sid in dead:
            rescue = glob.glob(os.path.join(ARCH, '抢救', 'session-' + sid + '-*')) + glob.glob(os.path.join(ARCH, '抢救', sid + '-*'))
            lines.append('| %s | 不存在 | %s |' % (os.path.basename(f), '、'.join(os.path.basename(r) for r in rescue[:2]) or '无'))
        open(REPORT, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(json.dumps({'会话卡总数': len(cards), '死链': len(dead), '本次加标记': marked,
                      '报告': os.path.basename(REPORT) if apply else '（未写）',
                      'dry': not apply}, ensure_ascii=False))

if __name__ == '__main__':
    main()
