#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识→记忆转化率：本周新增知识 vs 本周 remember 次数。

判据：转化率长期为 0 说明知识层只是「仓库」，没变成记忆。
数据源：知识/*.md 的 mtime；最近会话日志里的 tool/call name=remember。
"""
import os, glob, json, subprocess, time

ARCH = '/root/workspace/记忆档案'
SESS = os.path.expanduser('~/.dsh/sessions')
DAYS = 7
META = {'我的总结.md', '采集与学习索引.md'}

def knowledge_added():
    cutoff = time.time() - DAYS * 86400
    return [f for f in glob.glob(ARCH + '/知识/*.md')
            if os.path.getmtime(f) >= cutoff and os.path.basename(f) not in META]

def remember_calls():
    """扫最近会话日志，统计 remember 调用次数"""
    n = 0
    paths = glob.glob(os.path.join(SESS, '*', 'session-*', 'session.v4.jsonl.zstd'))
    cutoff_ms = (time.time() - DAYS * 86400) * 1000
    for p in paths:
        if os.path.getmtime(p) < time.time() - DAYS * 86400:
            continue
        try:
            out = subprocess.run(['zstd', '-dc', p], capture_output=True, timeout=60)
            for line in out.stdout.splitlines():
                try:
                    d = json.loads(line)
                    if d.get('type') == 'tool/call':
                        data = d.get('data') or {}
                        if data.get('name') == 'remember':
                            n += 1
                except Exception:
                    pass
        except Exception:
            pass
    return n

def high_value(ks):
    """高分候选：含判据/方法/结论，且不是情报数据类"""
    import re
    JUDGE = re.compile(r'判据|方法|原则|教训|结论|判断|规律|铁律')
    INTEL = re.compile(r'情报|官方源|点位|缺口|运价|指数|股市|制裁|仓位')
    TABLE = re.compile(r'^\|', re.M)
    n = 0
    for f in ks:
        try:
            txt = open(f, encoding='utf-8').read()
        except Exception:
            continue
        if INTEL.search(os.path.basename(f)) or len(TABLE.findall(txt)) > 6:
            continue
        if JUDGE.search(txt) or len(txt) >= 300:
            n += 1
    return n

def main():
    ks = knowledge_added()
    hv = high_value(ks)
    rm = remember_calls()
    rate_all = (rm / len(ks) * 100) if ks else 0
    rate_hv = (rm / hv * 100) if hv else 0
    print(json.dumps({
        '本周新增知识': len(ks),
        '高分候选': hv,
        '本周 remember': rm,
        '转化率(全部知识)': '%.0f%%' % rate_all,
        '转化率(高分候选)': '%.0f%%' % rate_hv,
        '目标': '60%',
        '判据': '按高分候选算更合理——分母只算「值得记的」，避免逼着记垃圾',
        '结论': '达标' if rate_hv >= 60 else '未达标：高分候选里只记了 %.0f%%' % rate_hv,
    }, ensure_ascii=False))

if __name__ == '__main__':
    main()
