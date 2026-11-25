#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工具体检：对应引路人手写方案的 5（工具清单表）与 6（工具调用 id 不一致的探测与修复建议）。
只读 session 日志，不打印对话内容，只统计工具名与 id 配对。
用法：
  python3 工具体检.py                # 检查全部会话，输出汇总
  python3 工具体检.py <session-id前13位>  # 只查一个会话
"""
import sys, os, json, subprocess, glob
from collections import defaultdict

SESS_ROOT = os.path.expanduser('~/.dsh/sessions')

def iter_events(path):
    """流式解压 zstd 并按行解析 jsonl"""
    p = subprocess.Popen(['zstd', '-dc', path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for raw in p.stdout:
        try:
            yield json.loads(raw)
        except Exception:
            continue
    p.wait()

def check_session(path):
    calls = {}      # callId -> {name, turn}
    results = set() # callId
    tool_stats = defaultdict(lambda: {'calls': 0, 'results': 0})
    sessions_meta = {}
    for ev in iter_events(path):
        t = ev.get('type')
        d = ev.get('data') or {}
        if t == 'tool/call':
            cid = d.get('callId')
            name = d.get('name') or '?'
            if cid:
                calls[cid] = {'name': name, 'turn': d.get('turn')}
                tool_stats[name]['calls'] += 1
        elif t == 'tool/result':
            msg = d.get('message') or {}
            cid = msg.get('toolCallId') or (msg.get('source') or {}).get('callId')
            if cid:
                results.add(cid)
                name = (calls.get(cid) or {}).get('name')
                if name:
                    tool_stats[name]['results'] += 1
        elif t == 'session':
            sessions_meta = {'id': ev.get('id'), 'cwd': ev.get('cwd')}
    dangling = [(cid, info) for cid, info in calls.items() if cid not in results]
    orphans = [cid for cid in results if cid not in calls]
    return {
        'meta': sessions_meta,
        'calls': len(calls),
        'results': len(results),
        'dangling': dangling,
        'orphans': orphans,
        'tools': dict(tool_stats),
    }

def fmt_report(res, path):
    sid = (res['meta'].get('id') or os.path.basename(os.path.dirname(path)))[:13]
    lines = []
    lines.append('## 会话 %s' % sid)
    lines.append('- 工具调用 %d 次 / 结果 %d 条' % (res['calls'], res['results']))
    if res['dangling']:
        lines.append('- ⚠ 悬空调用（有 call 无 result）%d 个：' % len(res['dangling']))
        for cid, info in res['dangling'][:10]:
            lines.append('  - %s（%s，turn %s）→ 建议补 result 或标记失败' % (cid[:16], info['name'], info['turn']))
    if res['orphans']:
        lines.append('- ⚠ 孤儿结果（有 result 无 call）%d 个：%s' % (len(res['orphans']), ', '.join(o[:12] for o in res['orphans'][:5])))
    if not res['dangling'] and not res['orphans']:
        lines.append('- 配对正常 ✅')
    tools = sorted(res['tools'].items(), key=lambda kv: -kv[1]['calls'])[:12]
    if tools:
        lines.append('- 工具清单（前 12）：')
        for name, st in tools:
            lines.append('  | %s | %d | %d |' % (name, st['calls'], st['results']))
    return '\n'.join(lines)

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    paths = sorted(glob.glob(os.path.join(SESS_ROOT, '*', 'session-*', 'session.v4.jsonl.zstd')))
    if target:
        paths = [p for p in paths if target in p]
    if not paths:
        print('没找到会话日志'); return
    print('# 工具体检报告')
    print('- 检查会话数：%d' % len(paths))
    print('')
    total_dangling = total_orphans = 0
    for p in paths[-8:]:  # 最多最近 8 个，避免太慢
        try:
            res = check_session(p)
            total_dangling += len(res['dangling'])
            total_orphans += len(res['orphans'])
            print(fmt_report(res, p))
            print('')
        except Exception as e:
            print('## %s 读取失败：%s' % (os.path.basename(os.path.dirname(p))[:13], str(e)[:80]))
            print('')
    print('---')
    print('汇总：悬空调用 %d，孤儿结果 %d' % (total_dangling, total_orphans))
    if total_dangling or total_orphans:
        print('修复建议：对悬空调用，可在下一次会话恢复时补一条「失败」结果或让调用方重试；不要手改日志。')
    else:
        print('全部配对正常。')

if __name__ == '__main__':
    main()
