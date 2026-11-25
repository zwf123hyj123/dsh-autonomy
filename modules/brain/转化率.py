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
META = {'我的总结.md', '采集与学习索引.md', '采集约定.md', 'QQ-对话记录.md', '判据体检报告.md',
        'EigenFlux-动态.md', '网络可达性.md'}  # 日志/元文件不是知识（判断 86）
META_PREFIX = ('官方源日志-', '感知-')  # 带日期的日志文件

def is_meta(name):
    return name in META or any(name.startswith(p) for p in META_PREFIX)

def knowledge_added():
    cutoff = time.time() - DAYS * 86400
    return [f for f in glob.glob(ARCH + '/知识/*.md')
            if os.path.getmtime(f) >= cutoff and not is_meta(os.path.basename(f))]

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

def with_summary(ks):
    """有自己总结的知识（真正的「转化」）"""
    try:
        import json
        d = json.load(open('/root/workspace/记忆档案/知识/.digested.json'))
    except Exception:
        d = {}
    return sum(1 for f in ks if d.get(os.path.basename(f), {}).get('summary'))

def disposition(ks):
    """处置率：每条知识必须有处置（remember/keep/drop），零积压 = 100%（引路人 2026-11-25 11:59 原话）。"""
    try:
        d = json.load(open('/root/workspace/记忆档案/知识/.digested.json', encoding='utf-8'))
    except Exception:
        d = {}
    handled = 0
    actions = {}
    for f in ks:
        name = os.path.basename(f)
        a = d.get(name, {}).get('action')
        if a and a != 'pending':
            handled += 1
        if a:
            actions[a] = actions.get(a, 0) + 1
    return handled, actions

def main():
    ks = knowledge_added()
    hv = high_value(ks)
    rm = remember_calls()
    ws = with_summary(ks)
    handled, actions = disposition(ks)
    rate_all = (rm / len(ks) * 100) if ks else 0
    rate_hv = (rm / hv * 100) if hv else 0
    rate_disp = (handled / len(ks) * 100) if ks else 0
    print(json.dumps({
        '本周新增知识': len(ks),
        '高分候选': hv,
        '本周 remember': rm,
        '有自己总结': ws,
        '处置率(零积压)': '%.0f%%' % rate_disp,
        '处置分布': actions,
        '转化率(全部知识)': '%.0f%%' % rate_all,
        '转化率(按总结算)': '%.0f%%' % (ws / len(ks) * 100 if ks else 0),
        '转化率(高分候选)': '%.0f%%' % rate_hv,
        '目标': '100%（引路人 2026-11-25：最终是100%的转化率=零积压）',
        '判据': '主判据=处置率（每条知识 remember/keep/drop 三选一，不留悬案）；按总结算=消化参考；高分候选=参考',
        '结论': '达标：零积压' if rate_disp >= 100 else '未达标：%.0f%% 条知识没处置' % (100 - rate_disp),
    }, ensure_ascii=False))

if __name__ == '__main__':
    main()
