#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消化标记：知识条目处理完就标一下，让「待消化区」能清空。

用法：
  python3 消化.py <文件名> remember   # 已转成记忆
  python3 消化.py <文件名> drop       # 判定不需要（情报过期/低价值）
  python3 消化.py <文件名> keep       # 留在知识层（按需检索，不算待消化）
  python3 消化.py --status            # 看待消化区状态
"""
import os, json, sys, time, glob

ARCH = '/root/workspace/记忆档案'
KNOW = os.path.join(ARCH, '知识')
STATE = os.path.join(KNOW, '.digested.json')
# 元文件：不是知识条目（摘要是产物、索引是目录）
META = {'我的总结.md', '采集与学习索引.md'}

def load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}

def save(d):
    tmp = STATE + '.tmp'
    json.dump(d, open(tmp, 'w'), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)

def status():
    d = load()
    week = [f for f in glob.glob(KNOW + '/*.md')
            if os.path.getmtime(f) >= time.time() - 7 * 86400 and os.path.basename(f) not in META]
    pending = [f for f in week if os.path.basename(f) not in d]
    print(json.dumps({
        '本周新增': len(week),
        '已消化': len([f for f in week if os.path.basename(f) in d]),
        '待消化': len(pending),
        '待消化清单': [os.path.basename(f) for f in pending[:10]],
        '消化率': '%.0f%%' % (len([f for f in week if os.path.basename(f) in d]) / len(week) * 100) if week else 'n/a',
    }, ensure_ascii=False))

def main():
    if len(sys.argv) < 2 or sys.argv[1] == '--status':
        status(); return
    name = sys.argv[1]
    action = sys.argv[2] if len(sys.argv) > 2 else 'keep'
    if action not in ('remember', 'drop', 'keep'):
        print('action 必须是 remember / drop / keep'); return
    d = load()
    rec = {'action': action, 'at': time.strftime('%Y-%m-%d %H:%M:%S')}
    # 可选：--summary "我的总结"（转化=自己总结，不是搬运原文）
    if len(sys.argv) > 3 and sys.argv[3] == '--summary' and len(sys.argv) > 4:
        rec['summary'] = sys.argv[4]
    d[name] = rec
    save(d)
    print('已标记 %s → %s' % (name, action))
    status()

if __name__ == '__main__':
    main()
