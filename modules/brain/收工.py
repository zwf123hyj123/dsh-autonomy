#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 收工.py — 每晚一次：重建判据索引 → 统计复用率 → 火花回灌（每天一次）→ 突触清理（每周一次）→ 写索引一行。
import os, subprocess, datetime, json

B = '/root/workspace/记忆档案'
STAMP = os.path.join(B, '知识', '.收工状态.json')
IDX = os.path.join(B, '知识', '采集与学习索引.md')

def run(*args):
    return subprocess.run(['python3'] + list(args), capture_output=True, text=True).stdout.strip()

def load():
    try: return json.load(open(STAMP, encoding='utf-8'))
    except Exception: return {}

def main():
    # 情感层：每日摇一次酒（调酒器接入日常）
    try:
        run('python3', '/root/workspace/记忆档案/调酒日检.py')
    except Exception:
        pass
    # 感知→知识通道
    try:
        run('python3', '/root/workspace/记忆档案/感知归档.py')
    except Exception:
        pass
    # 知识→记忆：生成候选（第二天自我唤醒时挑着 remember）
    try:
        run('python3', '/root/workspace/记忆档案/知识提炼.py')
    except Exception:
        pass
    # 导出「我的总结」（可撞、可调用）
    try:
        run('python3', '/root/workspace/记忆档案/知识摘要.py')
    except Exception:
        pass
    st = load(); today = datetime.date.today().isoformat()
    out = []
    out.append(run(os.path.join(B, '判据索引.py')))
    # 2026-11-25 修：判据索引变了，判据向量必须跟着重建（写≠读：85/86 曾因向量落后匹配不到）
    vec = run(os.path.join(B, '判据向量.py'))
    out.append(vec or '判据向量：跳过（ollama 离线）')
    stat = run(os.path.join(B, '判据调用.py'), '--统计')
    out.append(stat.split('\n')[0])
    if st.get('spark') != today:
        out.append(run(os.path.join(B, '火花回灌.py')))
        st['spark'] = today
    week = datetime.date.today().isocalendar()[:2]
    if st.get('syn') != list(week):
        out.append('突触清理：见 synapses.bak，本周已清')
        st['syn'] = list(week)
    # 2026-11-25 加：近一次对话缓存清理（preload 只用最近的；保留 cur-talk + 最近 3 个）
    try:
        import glob as _g2
        _nd = os.path.join(B, '近一次对话')
        _nf = sorted(_g2.glob(os.path.join(_nd, '*.md')), key=os.path.getmtime)
        _keep2 = set(_nf[-3:]) | {os.path.join(_nd, 'cur-talk.md')}
        _rm2 = 0
        for _f in _nf:
            if _f not in _keep2:
                try:
                    os.remove(_f); _rm2 += 1
                except Exception:
                    pass
        if _rm2:
            out.append('近一次对话清理：%d 个旧缓存' % _rm2)
    except Exception:
        pass
    # 2026-11-25 加：断点目录清理（保留 common.json + 最近 50 个，防无限增长）
    try:
        import glob as _glob
        _bd = os.path.join(B, '连续性', '断点')
        _bf = sorted(_glob.glob(os.path.join(_bd, '*.json')), key=os.path.getmtime)
        _keep = set(_bf[-50:]) | {os.path.join(_bd, 'common.json')}
        _rm = 0
        for _f in _bf:
            if _f not in _keep:
                try:
                    os.remove(_f); _rm += 1
                except Exception:
                    pass
        if _rm:
            out.append('断点清理：%d 个旧断点' % _rm)
    except Exception:
        pass
    # 预测结算提醒：到期未结算的列出来，不自动改结果（对错要我自己判）
    import re
    pl = os.path.join(B, '预测', '预测日志.md')
    if os.path.exists(pl):
        due = []
        for line in open(pl, encoding='utf-8'):
            m = re.match(r'\|\s*(P\d+)\s*\|.*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*待结算\s*\|', line)
            if m and m.group(2) <= today:
                due.append('%s（%s 到期）' % (m.group(1), m.group(2)))
        if due:
            out.append('预测待结算：' + '、'.join(due))
    # 八层自检（每日一次，有缺口就把结论记进索引）
    try:
        chk = subprocess.run(['python3', '/root/workspace/记忆档案/自检.py'],
                             capture_output=True, text=True, timeout=180)
        last = (chk.stdout or '').strip().split('\n')[-1]
        out.append('八层自检：' + (last or '无输出'))
    except Exception as e:
        out.append('八层自检失败：' + str(e)[:60])
    json.dump(st, open(STAMP, 'w', encoding='utf-8'))
    line = '- %s | 收工 | %s | 判据索引/调用统计/火花回灌/八层自检 | —\n' % (
        datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), '；'.join(x for x in out if x)[:220])
    open(IDX, 'a', encoding='utf-8').write(line)
    print('\n'.join(x for x in out if x))

if __name__ == '__main__':
    main()
