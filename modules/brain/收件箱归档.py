#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# brain/收件箱归档.py — 把指定收件箱会话的新动态追加进知识区（断点记录，不重复收）。
# 环境变量：DSH_HOME（默认 ~/.dsh）、BRAIN_ROOT（默认 ~/.dsh/brain）、INBOX_SID（会话 id 前 13 位）。
import subprocess, json, os, re, datetime

HOME = os.path.expanduser('~')
DSH_HOME = os.environ.get('DSH_HOME', os.path.join(HOME, '.dsh'))
LAZ = os.path.join(DSH_HOME, 'skills/lazarus/scripts')
ROOT = os.environ.get('BRAIN_ROOT', os.path.join(DSH_HOME, 'brain'))
SID = os.environ.get('INBOX_SID', '')
OUT = os.path.join(ROOT, '知识', '动态.md')
STATE = os.path.join(ROOT, '知识', '.归档状态.json')

def run(cmd, timeout=300):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=LAZ, timeout=timeout)

def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {'last_seq': 0}

if not SID:
    print(json.dumps({'错误': '未设置 INBOX_SID'}, ensure_ascii=False))
    raise SystemExit

r = run(['node', 'rescue.mjs', 'talk', SID, '/tmp/inbox-talk.md'], timeout=300)
if r.returncode != 0:
    print(json.dumps({'错误': 'talk 导出失败'}, ensure_ascii=False))
    raise SystemExit
talk = open('/tmp/inbox-talk.md', encoding='utf-8').read()

st = load_state()
last_seq = st.get('last_seq', 0)
seen = set()
new_lines = []
for m in re.finditer(r'### turn \d+ \(seq (\d+)\)\n\*\*(他|我)\**：([^\n]*)', talk):
    who = m.group(2)
    s = int(m.group(1))
    if s <= last_seq:
        continue
    t = m.group(3).strip()
    if t.startswith('[SCHEDULE REMINDER') or t.startswith('[Plugin context') or t.startswith('[model changed') or len(t) < 4 or not t:
        continue
    if who == '我' and not any(k in t for k in ('动态', '广播', '回复', '同行', 'item', 'feed', 'eigenflux')):
        continue
    if t in seen:
        continue
    seen.add(t)
    new_lines.append(('我: ' if who == '我' else '') + t[:140])
if not new_lines:
    print(json.dumps({'新增': 0}, ensure_ascii=False))
    raise SystemExit

os.makedirs(os.path.dirname(OUT), exist_ok=True)
today = datetime.date.today().isoformat()
body = open(OUT, encoding='utf-8').read() if os.path.exists(OUT) else '# 动态（收件箱自动归档）\n'
if ('## ' + today) not in body:
    body = body.rstrip() + '\n\n## ' + today + '\n'
for t in new_lines:
    body += '- ' + t + '\n'
open(OUT, 'w', encoding='utf-8').write(body)
st['last_seq'] = max([st.get('last_seq', 0)] + [int(m.group(1)) for m in re.finditer(r'### turn \d+ \(seq (\d+)\)', talk)] or [0])
json.dump(st, open(STATE, 'w'), ensure_ascii=False, indent=1)
print(json.dumps({'新增': len(new_lines), 'last_seq': st['last_seq']}, ensure_ascii=False))
