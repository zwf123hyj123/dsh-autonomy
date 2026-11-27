#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 神经突触.py v1 — 可塑的神经交流网络（脑神经元特性版）。
# 节点=概念；边=带权通道（兴奋/抑制）；赫布学习；用进废退衰减；LTP/LTD；不应期；胜者通吃。
import os, re, json, glob, random, datetime, collections

# 发布版路径适配（2026-11-27）：内用版用绝对路径，这里统一走环境变量；SIMBRAIN_ROOT 由使用方指定，未设时落在用户目录。
import os as _os
SIMROOT = _os.environ.get("SIMBRAIN_ROOT") or _os.path.expanduser("~/simulated-brain")
DATA = _os.environ.get("SIMBRAIN_DATA") or _os.path.join(SIMROOT, "data")
KNOW = _os.environ.get("SIMBRAIN_KNOW") or _os.path.join(SIMROOT, "知识")


BRAIN = _os.environ.get('BRAIN_ROOT', DATA)
SYN = os.path.join(BRAIN, '突触', 'synapses.json')
FLOW = os.path.join(BRAIN, '突触', '思维流-')
REG = os.path.join(BRAIN, '发布清单.md')
ETA, DECAY, THR, TOPK, REF = 0.05, 0.97, 0.35, 8, 1

NOISE = ('的', '了', '是', '在', '和', '与', '或', '这', '那', '有', '也', '都', '会', '可以', '需要', '一个', '没有', '不是', '之后', '这个', 'the', 'and', 'this', 'that', 'for', 'from', 'json', 'bash', 'echo', 'true', 'false', 'tmp', 'job', 'background', '触发', '继续')

REGION_FIX = {
    '小助手爱莉希雅': '前额叶', 'dsh-ctxc': '前额叶', 'dsh-autonomy': '前额叶', 'dsh-knowledge': '前额叶',
    '调酒器': '边缘系统', '酒架': '边缘系统', 'EigenFlux': '社会脑', '思维碰撞': '前额叶',
    '上下文压缩': '前额叶', 'Agent记忆': '前额叶', '移动端小模型': '前额叶',
    '自我核心': '默认模式网络', '自省': '默认模式网络', '灵感': '默认模式网络',
}
REGION_COLOR = {'海马体': '#7aa2f7', '前额叶': '#e0af68', '语言中枢': '#9ece6a', '边缘系统': '#f7768e',
                '感觉皮层': '#7dcfff', '运动习惯区': '#bb9af7', '社会脑': '#2ac3de', '默认模式网络': '#c0caf5', '未分区': '#888888'}

def region_of(name):
    for k, v in REGION_FIX.items():
        if k in name:
            return v
    return '未分区'

def load_whitelist():
    names = set()
    try:
        txt = open(REG, encoding='utf-8').read()
        for m in re.finditer(r'\|\s*([\u4e00-\u9fa5A-Za-z0-9-]{2,20})\s*\|', txt):
            names.add(m.group(1))
    except Exception:
        pass
    names = {n for n in names if not set(n) <= set('-—|') and n not in ('说明', '项目真名', '---')}
    return names

def load_nodes():
    nodes = dict(load_whitelist() and [(n, {}) for n in load_whitelist()])
    # 知识条目标题（2026-11-25 修：日志/元文件同步排除，与 思维碰撞/自检 同口径——判断 86）
    META = ('.rag', '动态', '约定', '索引', '原始', 'QQ-对话记录', '判据体检报告', '网络可达性', '官方源日志-', '感知-')
    for f in glob.glob(os.path.join(BRAIN, '知识', '*.md')):
        if any(k in os.path.basename(f) for k in META):
            continue
        t = os.path.basename(f).replace('.md', '').replace('2026-', '').replace('2025-', '')
        nodes.setdefault(t, {})
    # 高频概念词（频次≥4 且非噪音）
    cnt = collections.Counter()
    # 2026-11-25 修：只扫未归档（会话卡含系统提示词噪音，与 scan_files 一致）
    for f in glob.glob(os.path.join(BRAIN, '知识', '*.md')) + glob.glob(os.path.join(BRAIN, '连续性', '未归档', '*.md')):
        try:
            txt = open(f, encoding='utf-8').read()[-6000:]
        except Exception:
            continue
        for w in set(re.findall(r'[\u4e00-\u9fa5]{2,4}', txt)):
            if w not in NOISE:
                cnt[w] += 1
    for w, n in cnt.most_common(60):
        if n >= 4:
            nodes.setdefault(w, {})
    return nodes

def load_syn():
    try:
        return json.load(open(SYN, encoding='utf-8'))
    except Exception:
        return {'edges': {}, 'nodes': {}, 'last': ''}

def k(a, b):
    return a + '||' + b if a <= b else b + '||' + a

def find_suspects():
    """反幻门神经化：清单外疑似项目名 = 抑制源。"""
    wl = load_whitelist()
    suspects = set()
    pat = re.compile(r'[\u4e00-\u9fa5]{3,6}(助手|项目|引擎|工具)')
    # 2026-11-25 修：只扫未归档（会话卡含系统提示词噪音，与 scan_files 一致）
    for f in glob.glob(os.path.join(BRAIN, '知识', '*.md')) + glob.glob(os.path.join(BRAIN, '连续性', '未归档', '*.md')):
        try:
            txt = open(f, encoding='utf-8').read()[-6000:]
        except Exception:
            continue
        for m in pat.finditer(txt):
            nm = m.group(0)
            if nm in wl or nm in ('思维碰撞引擎', '知识库子项目', '清单外疑似项目', '字幕提取工具', '智能体图记忆引擎', '及量化和推理引擎', '导入小助手', '导入小助手项目', '读取小助手'):
                continue
            if any(w in nm for w in ('你我他的个所有内等重启')):
                continue
            suspects.add(nm)
    return list(suspects)[:8]

def init_edges(syn, nodes):
    # v2：抑制突触——疑似项目名对白名单实体发抑制信号（幻觉在神经层面被压住）
    wl = load_whitelist()
    for s in find_suspects():
        nodes.setdefault(s, {})
        for e in list(wl)[:6]:
            key = k(s, e)
            if key not in syn['edges']:
                syn['edges'][key] = {'w': -0.5, 'acts': 0, 'last_act': '', 'inh': True}
    # 2026-11-25 修：真突触（synapses.jsonl，经质量门）也进网络——
    # 之前只从候选 json 初始化，思维碰撞发现的真突触进不了神经网络（写≠读）
    try:
        for _line in open(os.path.join(BRAIN, '突触', 'synapses.jsonl'), encoding='utf-8'):
            _line = _line.strip()
            if not _line:
                continue
            try:
                _d = json.loads(_line)
            except Exception:
                continue
            _a, _b = str(_d.get('from', '')), str(_d.get('to', ''))
            if not _a or not _b or (_a not in nodes and _b not in nodes):
                continue
            _key = k(_a, _b)
            _w = min(0.9, 0.3 + int(_d.get('count', 2)) * 0.03)  # 真突触权重高于候选
            if _key not in syn['edges']:
                syn['edges'][_key] = {'w': round(_w, 3), 'acts': 0, 'last_act': ''}
    except FileNotFoundError:
        pass
    # 从候选突触 json 初始化权重（cooccur 归一化）
    for c in glob.glob(os.path.join(BRAIN, '突触', '候选-*.json')):
        try:
            cands = json.load(open(c, encoding='utf-8'))
        except Exception:
            continue
        for it in cands[-40:]:
            a, b = it['from'], it['to']
            if a not in nodes and b not in nodes:
                continue
            key = k(a, b)
            w = min(0.8, 0.2 + it['count'] * 0.02)
            if key not in syn['edges']:
                syn['edges'][key] = {'w': round(w, 3), 'acts': 0, 'last_act': ''}

def step(syn, nodes, seeds):
    act = {n: 0.0 for n in nodes}
    for s in seeds:
        if s in act:
            act[s] = 1.0
    fired, ref = [], {}
    for _ in range(3):  # 3 轮传播
        wave = []
        for a, av in act.items():
            if av >= THR and ref.get(a, 0) <= 0:
                wave.append((a, av))
        if not wave:
            break
        wave.sort(key=lambda x: -x[1])
        wave = wave[:TOPK]  # 胜者通吃
        fired.extend(a for a, _ in wave if a not in fired)
        fired_set = set(wave[0] for wave in [])  # placeholder replaced below
        for a, av in wave:
            ref[a] = REF
        for a, av in wave:
            for key, e in syn['edges'].items():
                x, y = key.split('||')
                o = y if x == a else (x if y == a else None)
                if o is None or o not in act:
                    continue
                act[o] = act.get(o, 0) + av * e['w']  # 幅度×权重（负权=抑制）
        # 侧抑制：胜者通吃后，未发放节点被压制（同区竞争，稀疏编码）
        winners = {a for a, _ in wave}
        for n in act:
            if n not in winners:
                act[n] *= 0.3
        for n in act:
            act[n] *= 0.6  # 衰减
            ref[n] = ref.get(n, 0) - 1
    return fired, act

def plasticity(syn, fired, today):
    # 赫布学习：共同发放的连在一起
    for i in range(len(fired)):
        for j in range(i + 1, len(fired)):
            key = k(fired[i], fired[j])
            e = syn['edges'].setdefault(key, {'w': 0.1, 'acts': 0, 'last_act': ''})
            e['w'] = min(1.0, e['w'] + ETA)
            e['acts'] += 1
            e['last_act'] = today
            if e['acts'] >= 3:
                e['w'] = min(1.0, e['w'] + 0.1)  # LTP
    # 用进废退：全图衰减，弱边剪除；LTD：今日只被路过一次的兴奋边弱化
    for key in list(syn['edges'].keys()):
        e = syn['edges'][key]
        if e['last_act'] == today:
            if e['acts'] == 1 and e['w'] > 0 and not e.get('inh'):
                e['w'] = round(e['w'] - 0.05, 3)
        else:
            e['w'] = round(e['w'] * DECAY, 3)
            if e['last_act'] and (datetime.date.today() - datetime.date.fromisoformat(e['last_act'])).days >= 30 and abs(e['w']) < 0.05:
                del syn['edges'][key]
    return syn

def main():
    today = datetime.date.today().isoformat()
    nodes = load_nodes()
    syn = load_syn()
    init_edges(syn, nodes)
    # 种子：白名单实体 + 随机概念
    wl = [n for n in nodes if n in load_whitelist()]
    seeds = random.sample(wl, min(3, len(wl))) + random.sample(list(nodes), min(2, max(0, len(nodes) - len(wl))))
    fired, act = step(syn, nodes, seeds)
    syn = plasticity(syn, fired, today)
    syn['last'] = today
    json.dump(syn, open(SYN, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    with open(FLOW + today + '.md', 'w', encoding='utf-8') as f:
        f.write('# 神经思维流（%s）\n\n' % today)
        f.write('发放序列：' + ' → '.join(fired[:20]) + '\n\n')
        f.write('边数：%d（其中新增强化 %d 条）\n' % (len(syn['edges']), sum(1 for e in syn['edges'].values() if e['last_act'] == today)))
    visualize(syn, nodes, fired, today)
    print(json.dumps({'节点': len(nodes), '边': len(syn['edges']), '发放': len(fired), '路径': ' → '.join(fired[:12])}, ensure_ascii=False))

def visualize(syn, nodes, fired, today):
    """思维流可视化：SVG 图（节点=圆按脑区着色，边=线粗∝权重，抑制=红虚线，发放路径=高亮折线）。"""
    import math as _m  # 2026-11-25 恢复：清理脚本误删（math 别名）

    used = [n for n in nodes if any(n in k for k in syn['edges'])]
    groups = {}
    for n in used:
        groups.setdefault(region_of(n), []).append(n)
    pos = {}
    order = list(groups.keys())
    for gi, gname in enumerate(order):
        members = groups[gname]
        base_ang = gi * (360.0 / len(order))
        for mi, m in enumerate(members):
            ang = _m.radians(base_ang + mi * (min(50, 360.0 / max(1, len(members)))))
            pos[m] = (400 + 300 * _m.cos(ang), 300 + 300 * _m.sin(ang))
    lines = []
    for key, e in syn['edges'].items():
        a, b = key.split('||')
        if a not in pos or b not in pos or abs(e['w']) < 0.05:
            continue
        x1, y1 = pos[a]; x2, y2 = pos[b]
        width = 0.8 + abs(e['w']) * 5
        color = '#e64553' if e['w'] < 0 else '#8c8c8c'
        dash = ' stroke-dasharray="5,4"' if e['w'] < 0 else ''
        lines.append('<line x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f" stroke="%s" stroke-width="%.2f"%s/>' % (x1, y1, x2, y2, color, width, dash))
    pts = []
    for n in fired[:24]:
        if n in pos:
            pts.append('<circle cx="%.0f" cy="%.0f" r="13" fill="%s" stroke="#111" stroke-width="2"/><text x="%.0f" y="%.0f" font-size="9" text-anchor="middle" fill="#111">%s</text>' % (pos[n][0], pos[n][1], REGION_COLOR.get(region_of(n), '#888'), pos[n][0], pos[n][1] + 3, n[:8]))
    html = ('<!DOCTYPE html><html><head><meta charset="utf-8"><title>思维流 %s</title></head><body style="background:#fafafa">'
            '<h2 style="font-family:sans-serif">德缪哥矩阵 · 思维流 %s</h2>'
            '<svg width="800" height="600" style="background:white;border:1px solid #ddd">%s%s</svg>'
            '<p style="font-family:sans-serif;font-size:12px;color:#666">圆=概念节点（按脑区着色）；线粗=突触权重；红虚线=抑制；深色圆=今日发放路径。发放序列：%s</p>'
            '</body></html>') % (today, today, ''.join(lines), ''.join(pts), ' → '.join(fired[:24]))
    open(FLOW + today + '.html', 'w', encoding='utf-8').write(html)

if __name__ == '__main__':
    main()
