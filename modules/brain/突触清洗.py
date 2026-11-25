#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""突触清洗：把 synapses.jsonl 分成「合格突触」和「火花区」，并写勘误记录。
规则：
- spark_common（通点广播）→ 火花区，不留在主突触层
- text 为空的 → 丢弃并记勘误
- text 里的来源是日志文件（采集与学习索引 等流水账）的 → 不算数：重算该实体对在知识文件里的真实共现，
  ≥2 次则保留并改写来源（source 字段只记第一个扫到的文件，可能恰好是日志，不能盲删），
  <2 次才丢弃（判断 86：日志不是知识，行内共现是偶然的）
- 其余保留
"""
import os, json, time, shutil, importlib.util

SYN = '/root/workspace/记忆档案/突触/synapses.jsonl'
SPARK = '/root/workspace/记忆档案/突触/火花-%s.jsonl' % time.strftime('%Y-%m-%d')
ERR = '/root/workspace/记忆档案/突触/勘误-%s.md' % time.strftime('%Y-%m-%d')

# 日志类文件：流水账不是知识，从里面挖出的"共现"是任务名偶然相邻，不是语义关联
NOISE_SOURCES = ('采集与学习索引', '采集约定', '官方源日志', '巡查日志', '自治日志', 'EigenFlux-动态', 'QQ-对话记录', '感知-2026', '网络可达性', '判据体检报告')

def _load_tc():
    spec = importlib.util.spec_from_file_location('tc_engine', '/root/workspace/记忆档案/思维碰撞.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def recheck(r, tc, ents, files):
    """重算一条突触在知识文件里的共现次数与主来源。"""
    frm, to = str(r.get('from', '')), str(r.get('to', ''))
    cnt, first = 0, ''
    for f in files:
        try:
            txt = open(f, encoding='utf-8').read()[-8000:]
        except Exception:
            continue
        kws = tc.keywords(txt, ents)
        if frm in kws and to in kws:
            cnt += 1
            if not first:
                first = f
    return cnt, first

def main():
    recs = []
    try:
        for line in open(SYN, encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    except FileNotFoundError:
        print('没有 synapses.jsonl'); return

    # 先重算「日志来源」条目：知识文件里共现 >=2 的是真突触，改写来源后保留
    log_src = [r for r in recs if any(n in str(r.get('text', '')) for n in NOISE_SOURCES)]
    recovered = 0
    if log_src:
        tc = _load_tc()
        ents = tc.build_entities()
        files = tc.scan_files()
        for r in log_src:
            cnt, src = recheck(r, tc, ents, files)
            if cnt >= 2 and src:
                r['text'] = '共现 %d 次 | 来源：%s' % (cnt, os.path.basename(src))
                r['_recovered'] = True
                recovered += 1
            else:
                r['_noise'] = cnt

    keep, spark, dropped = [], [], []
    for r in recs:
        rel = r.get('rel', '')
        text = str(r.get('text', '')).strip()
        if rel == 'spark_common':
            spark.append(r)
        elif len(text) < 2:
            dropped.append(r)
        elif '_recovered' in r:
            r.pop('_recovered', None)
            keep.append(r)
        elif '_noise' in r:
            dropped.append(r)
        else:
            keep.append(r)

    # 备份
    bak = SYN + '.bak-clean-' + time.strftime('%H%M%S')
    shutil.copy2(SYN, bak)

    # 写回合格
    with open(SYN, 'w', encoding='utf-8') as f:
        for r in keep:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    # 火花区（追加，不覆盖）
    if spark:
        with open(SPARK, 'a', encoding='utf-8') as f:
            for r in spark:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')

    # 勘误
    with open(ERR, 'w', encoding='utf-8') as f:
        f.write('# 突触清洗勘误（%s）\n\n' % time.strftime('%Y-%m-%d %H:%M'))
        f.write('- 清洗前：%d 条\n' % len(recs))
        f.write('- 保留（合格突触）：%d 条\n' % len(keep))
        f.write('- 移入火花区（spark_common）：%d 条 → %s\n' % (len(spark), os.path.basename(SPARK)))
        f.write('- 丢弃（text 为空）：%d 条\n' % sum(1 for r in dropped if '_noise' not in r))
        f.write('- 日志来源重算：%d 条在知识文件里共现 ≥2 次 → 保留并改写来源；其余丢弃（知识共现 <2）\n' % recovered)
        f.write('- 原始备份：%s\n' % os.path.basename(bak))
        f.write('- 判据：spark_common 属火花不属突触；text < 2 字符视为无意义；日志来源不盲删，重算知识共现 ≥2 才留（判断 86 + 读写一致）\n')

    print(json.dumps({
        '清洗前': len(recs), '保留': len(keep), '火花区': len(spark), '丢弃': len(dropped),
        '日志来源恢复': recovered, '备份': os.path.basename(bak),
    }, ensure_ascii=False))

if __name__ == '__main__':
    main()
