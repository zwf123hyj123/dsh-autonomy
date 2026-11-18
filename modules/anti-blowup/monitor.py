#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# anti-blowup/monitor.py — 会话防炸监控（自主执行模块之一）。
# 职责：每日体检全部会话；爆掉的自动抢救导出；快爆的导索引预警；
#       抢救产出自动跑上下文压缩；命名核对（反幻门）；思维碰撞；知识区 git 版控。
# 路径全部经环境变量，无任何硬编码隐私：
#   DSH_HOME   (默认 ~/.dsh)      — 引擎家目录（skills/lazarus/scripts、sessions）
#   BRAIN_ROOT (默认 ~/.dsh/brain) — 知识/档案/突触根目录
import subprocess, json, os, datetime, sys, re, glob

HOME = os.path.expanduser('~')
DSH_HOME = os.environ.get('DSH_HOME', os.path.join(HOME, '.dsh'))
LAZ = os.path.join(DSH_HOME, 'skills/lazarus/scripts')
ARCHIVE = os.environ.get('BRAIN_ROOT', os.path.join(DSH_HOME, 'brain'))
STATE = os.path.join(ARCHIVE, '监控状态.json')

def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=LAZ, timeout=timeout)

def load(path, dflt):
    try:
        return json.load(open(path))
    except Exception:
        return dflt

now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

# 1. health 全量
h = run(['node', 'rescue.mjs', 'health'], timeout=300)
try:
    health = json.loads(h.stdout)
except Exception as e:
    print(json.dumps({'错误': 'health 解析失败: ' + str(e)}, ensure_ascii=False))
    sys.exit(1)
ss = health['sessions']

def p(x):
    v = x.get('pressure')
    return v if isinstance(v, (int, float)) else 0.0

danger = [x for x in ss if p(x) >= 0.8]
elev = [x for x in ss if 0.6 <= p(x) < 0.8]
state = load(STATE, {'rescued': [], 'warned': []})
rescued = set(state.get('rescued', []))
warned = set(state.get('warned', []))

# 2. 爆了的：新出现的 → 自动 scan + 导 index + talk
new_blown = []
for x in danger:
    sid = x['session']
    if sid in rescued:
        continue
    short = sid[:13]
    try:
        r = run(['node', 'rescue.mjs', 'scan', short])
        d = json.loads(r.stdout)
        errs = d.get('lastCompactionErrors', [])
        if errs:
            os.makedirs(os.path.join(ARCHIVE, '抢救'), exist_ok=True)
            run(['node', 'rescue.mjs', 'index', short, os.path.join(ARCHIVE, '抢救', short + '-索引.txt')])
            run(['node', 'rescue.mjs', 'talk', short, os.path.join(ARCHIVE, '抢救', short + '-对话.md')])
            new_blown.append({'sid': short, '死因': errs[0].get('error', '')[:60]})
            rescued.add(sid)
    except Exception:
        pass

# 3. 快爆的：新进入 0.6-0.8 的 → 自动导索引预警
new_warn = []
for x in elev:
    sid = x['session']
    if sid in warned:
        continue
    short = sid[:13]
    try:
        os.makedirs(os.path.join(ARCHIVE, '抢救'), exist_ok=True)
        run(['node', 'rescue.mjs', 'index', short, os.path.join(ARCHIVE, '抢救', short + '-预警索引.txt')])
        new_warn.append(short)
        warned.add(sid)
    except Exception:
        pass

json.dump({'rescued': sorted(rescued), 'warned': sorted(warned)}, open(STATE, 'w'))

# 3.5 防炸+断点联动：抢救出的对话跑一遍 ctxc 摘要
ctxc_bin = os.environ.get('CTXC_BIN', '')
summary_done = 0
if ctxc_bin:
    for sid in [x['sid'] for x in new_blown] + new_warn:
        talk_file = os.path.join(ARCHIVE, '抢救', sid + '-对话.md')
        if not os.path.exists(talk_file):
            try:
                run(['node', 'rescue.mjs', 'talk', sid, talk_file], timeout=300)
            except Exception:
                continue
        try:
            subprocess.run(['python3', ctxc_bin, talk_file],
                           capture_output=True, text=True, timeout=900)
            summary_done += 1
        except Exception:
            pass

# 3.6 命名核对（防幻觉）：扫新卡片/事件里的项目名，不在发布清单 → 标待核实
try:
    reg_path = os.path.join(ARCHIVE, '发布清单.md')
    if os.path.exists(reg_path):
        reg = open(reg_path, encoding='utf-8').read()
        known = set(re.findall(r'\|\s*([\u4e00-\u9fa5A-Za-z0-9-]{2,20})\s*\|', reg))
        suspects = []
        for f in glob.glob(os.path.join(ARCHIVE, '连续性/*/*.md')) + glob.glob(os.path.join(ARCHIVE, '连续性/*.jsonl')):
            try:
                txt = open(f, encoding='utf-8').read()[-4000:]
            except Exception:
                continue
            for m in re.finditer(r'已发布[的]?\s*([\u4e00-\u9fa5A-Za-z0-9-]{2,20})', txt):
                nm = m.group(1)
                if nm not in known and nm not in ('GitHub', 'Release'):
                    suspects.append(nm)
        if suspects:
            print(json.dumps({'待核实项目名': sorted(set(suspects))}, ensure_ascii=False))
except Exception:
    pass

# 3.7 思维碰撞（模拟大脑关联引擎）
brain_bin = os.environ.get('BRAIN_BIN', '')
if brain_bin:
    try:
        subprocess.run(['python3', brain_bin], capture_output=True, text=True, timeout=300)
    except Exception:
        pass

# 3.8 知识区 git 自动提交
try:
    subprocess.run(['git', '-C', os.path.join(ARCHIVE, '知识'), 'add', '-A'], capture_output=True, timeout=60)
    subprocess.run(['git', '-C', os.path.join(ARCHIVE, '知识'), 'commit', '-qm',
                    '自动存档 ' + now], capture_output=True, timeout=60)
except Exception:
    pass

# 4. 长期任务提示
goals = []
for x in danger[:30]:
    sid = x['session']
    try:
        r = run(['node', 'rescue.mjs', 'index', sid[:13]])
        if '<goal_round>' in r.stdout or 'Objective:' in r.stdout:
            goals.append(sid[:13])
    except Exception:
        pass

report = {
    '时间': now,
    '总会话': health['count'],
    '危险(>=0.8)': len(danger),
    '偏高(0.6-0.8)': len(elev),
    '新爆掉(已自动抢救)': new_blown,
    '新预警(已导索引)': new_warn,
    '摘要压缩': summary_done,
    '含长期任务的危险会话(建议CLM checkpoint)': goals,
}
json.dump(report, open(os.path.join(ARCHIVE, '监控报告.json'), 'w'), ensure_ascii=False, indent=1)
print(json.dumps(report, ensure_ascii=False, indent=1))
