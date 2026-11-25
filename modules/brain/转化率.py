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

def knowledge_added():
    cutoff = time.time() - DAYS * 86400
    return [f for f in glob.glob(ARCH + '/知识/*.md') if os.path.getmtime(f) >= cutoff]

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

def main():
    ks = knowledge_added()
    rm = remember_calls()
    rate = (rm / len(ks) * 100) if ks else 0
    print(json.dumps({
        '本周新增知识': len(ks),
        '本周 remember': rm,
        '转化率': '%.0f%%' % rate,
        '判据': '低于 10% 视为「只存不用」',
        '结论': '正常' if rate >= 10 else '偏低：知识没有转成记忆',
    }, ensure_ascii=False))

if __name__ == '__main__':
    main()
