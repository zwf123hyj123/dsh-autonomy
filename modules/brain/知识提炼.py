#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识提炼：从本周新增知识里挑「值得转成记忆」的候选。

判据（对应转化率目标 60%）：
- 含具体数字/阈值（+2）
- 含判据/方法/原则/教训（+2）
- 含结论/判断/发现（+1）
- 篇幅完整（>=300 字，+1）
输出：记忆候选-<日期>.md，按分数排序，附理由与摘录。
后续：自我唤醒时读它，挑前 2-3 条 remember。
"""
import os, re, glob, time, json

ARCH = '/root/workspace/记忆档案'
KNOW = os.path.join(ARCH, '知识')
OUT = os.path.join(ARCH, '记忆候选-%s.md' % time.strftime('%Y-%m-%d'))

NUM = re.compile(r'\d+(?:\.\d+)?\s*(?:%|bp|亿|万|条|次|天|小时|元|GB|MB)')
JUDGE = re.compile(r'判据|方法|原则|教训|结论|判断|规律|铁律')
CONCL = re.compile(r'发现|结论|证明|验证|反证')

INTEL = re.compile(r'情报|官方源|点位|缺口|运价|指数|股市|制裁|仓位')
TABLE = re.compile(r'^\|', re.M)

# 日志/元文件不是知识，不参与提炼（判断 86）
META = {'采集与学习索引.md', '采集约定.md', '我的总结.md', 'QQ-对话记录.md', '判据体检报告.md',
        'EigenFlux-动态.md', '网络可达性.md'}
META_PREFIX = ('官方源日志-', '感知-')

STATE = os.path.join(KNOW, '.digested.json')

def score_file(path):
    name = os.path.basename(path)
    if name in META or any(name.startswith(p) for p in META_PREFIX):
        return None
    # 2026-11-25 修：已 remember 的不再进候选（之前候选不排除已消费的，会重复推荐）
    try:
        _d = json.load(open(STATE, encoding='utf-8'))
        if _d.get(name, {}).get('action') == 'remember':
            return None
    except Exception:
        pass
    try:
        txt = open(path, encoding='utf-8').read()
    except Exception:
        return None
    score = 0
    reasons = []
    # 类型判断：情报/数据类不进记忆（会过期，按需检索）
    if INTEL.search(name) or len(TABLE.findall(txt)) > 6:
        score -= 3
        reasons.append('情报/数据类（不推荐进记忆）')
    if NUM.search(txt):
        score += 2; reasons.append('含具体数字')
    if JUDGE.search(txt):
        score += 2; reasons.append('含判据/方法')
    if CONCL.search(txt):
        score += 1; reasons.append('含结论/发现')
    if len(txt) >= 300:
        score += 1; reasons.append('篇幅完整')
    if len(txt) < 120:
        score -= 2; reasons.append('过短')
    return {'file': os.path.basename(path), 'score': score,
            'reasons': reasons, 'excerpt': txt.strip()[:120].replace('\n', ' ')}

def main():
    cutoff = time.time() - 7 * 86400
    files = [f for f in glob.glob(KNOW + '/*.md') if os.path.getmtime(f) >= cutoff]
    rows = [r for r in (score_file(f) for f in files) if r]
    rows.sort(key=lambda r: -r['score'])
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('# 记忆候选（%s）\n\n' % time.strftime('%Y-%m-%d'))
        # 2026-11-25 修：建议条数不超过实际列出的候选数（原来建议 30 但只列 15，数字误导）
        f.write('> 本周知识 %d 条；目标转化率 60%%，建议本轮 remember 前 %d 条。\n\n' % (len(rows), max(1, min(15, len(rows) * 6 // 10))))
        for r in rows[:15]:
            f.write('- **%s**（分 %d：%s）\n  %s\n' % (r['file'], r['score'], '、'.join(r['reasons']), r['excerpt']))
    print(json.dumps({'本周知识': len(rows), '建议remember': max(1, min(15, len(rows) * 6 // 10)),
                      '候选文件': os.path.basename(OUT)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
