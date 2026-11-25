#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""突触清洗：把 synapses.jsonl 分成「合格突触」和「火花区」，并写勘误记录。
规则：
- spark_common（通点广播）→ 火花区，不留在主突触层
- text 为空的 → 丢弃并记勘误
- 其余保留
"""
import os, json, time, shutil

SYN = '/root/workspace/记忆档案/突触/synapses.jsonl'
SPARK = '/root/workspace/记忆档案/突触/火花-%s.jsonl' % time.strftime('%Y-%m-%d')
ERR = '/root/workspace/记忆档案/突触/勘误-%s.md' % time.strftime('%Y-%m-%d')

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

    keep, spark, dropped = [], [], []
    for r in recs:
        rel = r.get('rel', '')
        text = str(r.get('text', '')).strip()
        if rel == 'spark_common':
            spark.append(r)
        elif len(text) < 2:
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
        f.write('- 丢弃（text 为空）：%d 条\n' % len(dropped))
        f.write('- 原始备份：%s\n' % os.path.basename(bak))
        f.write('- 判据：spark_common 属火花不属突触；text < 2 字符视为无意义\n')

    print(json.dumps({
        '清洗前': len(recs), '保留': len(keep), '火花区': len(spark), '丢弃': len(dropped),
        '备份': os.path.basename(bak),
    }, ensure_ascii=False))

if __name__ == '__main__':
    main()
