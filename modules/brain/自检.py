#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自检：一键跑完模拟大脑八层 + 跨层一致性，输出红黄绿。

用法：python3 自检.py [--verbose]
判据来自 八层自检清单.md；全部是文件/统计级检查，不调模型（秒级）。
"""
import os, sys, json, glob, re, time, datetime, subprocess

ARCH = '/root/workspace/记忆档案'
KNOW = os.path.join(ARCH, '知识')
SYN = os.path.join(ARCH, '突触', 'synapses.jsonl')

def _ok(cond, good, bad):
    return (True, good) if cond else (False, bad)

def check_memory():
    cards = glob.glob(os.path.join(ARCH, '连续性', '会话卡', 'session-*.md'))
    dead = 0
    for f in cards:
        try:
            head = open(f, encoding='utf-8').read(200)
        except Exception:
            continue
        if '原会话已不存在' not in head:
            sid = os.path.basename(f)[:-3].replace('session-', '')
            if not glob.glob(os.path.expanduser('~/.dsh/sessions/*/session-' + sid + '*')):
                dead += 1
    return _ok(dead == 0, '会话卡 %d 张，无未标记死链' % len(cards), '未标记死链 %d 张' % dead)

def check_knowledge():
    try:
        d = json.load(open(os.path.join(KNOW, '.digested.json'), encoding='utf-8'))
    except Exception:
        d = {}
    META = {'我的总结.md', '采集与学习索引.md'}
    week = [f for f in glob.glob(KNOW + '/*.md')
            if os.path.getmtime(f) >= time.time() - 7 * 86400 and os.path.basename(f) not in META]
    pending = [f for f in week if os.path.basename(f) not in d]
    return _ok(len(pending) == 0, '知识 %d 条，待消化 0' % len(week), '待消化 %d 条' % len(pending))

def check_synapse():
    try:
        recs = [json.loads(l) for l in open(SYN, encoding='utf-8') if l.strip()]
    except Exception:
        recs = []
    KNOWN_2 = {'酒架', '突触', '海马体', '调酒器', '模拟大脑', '德缪哥矩阵', '知识', '记忆'}
    def _bad(v):
        v = str(v)
        if not v:
            return True
        if v in KNOWN_2:
            return False
        return len(v) < 3 or bool(re.fullmatch(r'[0-9a-f]{8,}', v)) or bool(re.search(r'\.(html|php|shtml)$', v, re.I))
    bad = 0
    for r in recs:
        if _bad(r.get('from')) or _bad(r.get('to')):
            bad += 1
    return _ok(len(recs) >= 10 and bad == 0, '突触 %d 条，实体对实体' % len(recs), '突触 %d 条中有 %d 条垃圾' % (len(recs), bad))

def check_tools():
    r = subprocess.run(['python3', '/root/workspace/dsh-ctxc/scripts/巡检.py', '--quiet'],
                       capture_output=True, text=True, timeout=120)
    return _ok(r.returncode == 0, '巡检全绿', '巡检有异常（详见 巡检.py）')

def check_collision():
    cands = glob.glob(os.path.join(ARCH, '突触', '候选-*.json'))
    try:
        latest = max(cands, key=os.path.getmtime)
        n = len(json.load(open(latest, encoding='utf-8')))
    except Exception:
        n = 0
    return _ok(n >= 30, '候选 %d 个' % n, '候选只有 %d 个（应 ≥30）' % n)

def check_emotion():
    out = os.path.join(ARCH, '调酒器', '产出-%s.md' % datetime.date.today())
    if not os.path.exists(out):
        return (False, '今日无调酒产出')
    txt = open(out, encoding='utf-8').read()
    return _ok('基酒配方' in txt, '调酒卡格式正确', '产出不是调酒卡（是 JSON？）')

def check_perception():
    try:
        txt = open(os.path.join(ARCH, '感知', '感知日志.md'), encoding='utf-8').read()
    except Exception:
        return (False, '无感知日志')
    today = datetime.date.today().isoformat()
    valid = [l for l in txt.splitlines() if today in l and '未取到' not in l and l.startswith('|')]
    return _ok(len(valid) > 0, '今日有效感知 %d 条' % len(valid), '今日无有效感知')

def check_spark():
    files = sorted(glob.glob(os.path.join(ARCH, '突触', '灵感-*.md')), key=os.path.getmtime)
    if not files:
        return (False, '无灵感文件')
    age = (time.time() - os.path.getmtime(files[-1])) / 86400
    txt = open(files[-1], encoding='utf-8').read()
    good = age <= 3 and '无火花' not in txt
    return _ok(good, '灵感 %s（%.1f 天前）' % (os.path.basename(files[-1]), age), '灵感断档或空（%.1f 天）' % age)

def check_consistency():
    issues = []
    # 判据速查同步
    r = subprocess.run(['python3', os.path.join(ARCH, '判据同步.py')], capture_output=True, text=True, timeout=60)
    if '缺失 0' not in (r.stdout or ''):
        issues.append('判据速查落后')
    # 关键词索引 vs 知识最新
    try:
        idx_t = os.path.getmtime(os.path.join(KNOW, '.index.json'))
        newest = max(os.path.getmtime(f) for f in glob.glob(KNOW + '/*.md'))
        if idx_t < newest - 60:
            issues.append('关键词索引陈旧')
    except Exception:
        issues.append('索引缺失')
    return _ok(not issues, '读写一致', '；'.join(issues))

CHECKS = [
    ('记忆层', check_memory), ('知识层', check_knowledge), ('突触层', check_synapse),
    ('工具层', check_tools), ('思维碰撞', check_collision), ('情感层', check_emotion),
    ('感知层', check_perception), ('自我点火', check_spark), ('跨层一致', check_consistency),
]

def main():
    if '--serve' in sys.argv:
        pass
    rows = []
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, '检查异常：' + str(e)[:60]
        rows.append((name, ok, detail))
    bad = [r for r in rows if not r[1]]
    print('# 八层自检')
    for name, ok, detail in rows:
        print(('✓ ' if ok else '✗ ') + name + '：' + detail)
    print('')
    print('结论：' + ('全部正常' if not bad else '%d 层有缺口' % len(bad)))
    sys.exit(0 if not bad else 1)

if __name__ == '__main__':
    main()
