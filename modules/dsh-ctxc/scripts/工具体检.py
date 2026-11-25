#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工具体检：对应处理方案的 5（工具清单表）与 6（工具调用 id 不一致的探测与修复建议）。
只读 session 日志，不打印对话内容，只统计工具名与 id 配对。
用法：
  python3 工具体检.py                # 检查全部会话，输出汇总
  python3 工具体检.py <session-id前13位>  # 只查一个会话
"""
import sys, os, json, subprocess, glob, time
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

# ---------- 修复 ----------
import shutil

def read_raw_events(path):
    """返回 [(raw_line, event)]，保持原顺序"""
    out = []
    p = subprocess.Popen(['zstd', '-dc', path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for raw in p.stdout:
        txt = raw.decode('utf-8', errors='replace').rstrip('\n')
        try:
            out.append((txt, json.loads(txt)))
        except Exception:
            out.append((txt, None))
    p.wait()
    return out

def fix_session(path):
    """给悬空 tool/call 补一条失败 result。返回 (修复数, 说明)"""
    items = read_raw_events(path)
    calls, results = {}, set()
    max_seq = 0
    for txt, ev in items:
        if not ev:
            continue
        max_seq = max(max_seq, int(ev.get('seq') or 0))
        t = ev.get('type'); d = ev.get('data') or {}
        if t == 'tool/call':
            cid = d.get('callId')
            if cid: calls[cid] = {'name': d.get('name') or '?', 'turn': d.get('turn'), 'step': d.get('step')}
        elif t == 'tool/result':
            msg = d.get('message') or {}
            cid = msg.get('toolCallId') or (msg.get('source') or {}).get('callId')
            if cid: results.add(cid)
    dangling = [cid for cid in calls if cid not in results]
    if not dangling:
        return 0, '没有悬空调用'
    # 备份
    bak = path + '.bak-fix-' + time.strftime('%Y%m%d-%H%M%S')
    shutil.copy2(path, bak)
    # 组装新事件
    new_lines = []
    seq = max_seq
    for cid in dangling:
        info = calls[cid]
        seq += 1
        ev = {
            'type': 'tool/result',
            'seq': seq,
            'time': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime()),
            'data': {
                'turn': info.get('turn'),
                'step': info.get('step'),
                'message': {
                    'role': 'tool',
                    'toolCallId': cid,
                    'source': {'kind': 'tool', 'callId': cid},
                    'content': [{'type': 'text', 'text': '[修复] 调用被中断，未返回结果（工具体检补写）'}],
                },
                'meta': {'repairedBy': 'tools-check', 'note': 'dangling tool call repaired'},
            },
        }
        new_lines.append(json.dumps(ev, ensure_ascii=False))
    # 写临时文件再原子替换
    tmp = path + '.tmp-fix'
    p = subprocess.Popen(['zstd', '-q', '-f', '-o', tmp], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for txt, _ in items:
        p.stdin.write((txt + '\n').encode('utf-8'))
    for line in new_lines:
        p.stdin.write((line + '\n').encode('utf-8'))
    p.stdin.close(); p.wait()
    if p.returncode != 0:
        return 0, '重新压缩失败，已保留备份'
    # 验证
    res = check_session(tmp)
    if res['dangling']:
        os.remove(tmp)
        return 0, '验证仍有悬空（%d），未替换' % len(res['dangling'])
    shutil.move(tmp, path)
    return len(dangling), '已补 %d 条失败结果；备份 %s' % (len(dangling), os.path.basename(bak))

def main():
    args = [a for a in sys.argv[1:] if a != '--fix']
    do_fix = '--fix' in sys.argv
    target = args[0] if args else None
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
    if do_fix:
        print('')
        print('## 修复模式')
        if not target:
            print('- 修复需要指定会话（sid 前 13 位），避免误改正在运行的会话。')
        else:
            for p in paths:
                n, note = fix_session(p)
                print('- %s：%s' % (os.path.basename(os.path.dirname(p))[:13], note))
    elif total_dangling or total_orphans:
        print('修复建议：对悬空调用，可在下一次会话恢复时补一条「失败」结果或让调用方重试；不要手改日志。')
        print('（要真修：python3 工具体检.py <sid前13位> --fix）')
    else:
        print('全部配对正常。')

if __name__ == '__main__':
    main()
