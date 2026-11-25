#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""感知归档：把感知日志里的有效条目按周汇总成知识条目（补上「感知→知识」通道）。

只收有效的（非「未取到」），一周一条；没有有效条目就写「本周无有效感知」——空跑也要留痕。
"""
import os, re, datetime

ARCH = '/root/workspace/记忆档案'
LOG = os.path.join(ARCH, '感知', '感知日志.md')
OUT_DIR = os.path.join(ARCH, '知识')

def main():
    try:
        txt = open(LOG, encoding='utf-8').read()
    except FileNotFoundError:
        print('没有感知日志'); return
    rows = []
    for line in txt.splitlines():
        m = re.match(r'\|\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|', line)
        if m:
            t, app, note = m.group(1), m.group(2).strip(), m.group(3).strip()
            if app and app != '未取到':
                rows.append((t, app, note))
    today = datetime.date.today()
    out = os.path.join(OUT_DIR, '感知-%s.md' % today.strftime('%Y-%m-%d'))
    if os.path.exists(out):
        # 2026-11-25 修：增量归档（原来文件存在就跳过，当天 12:00 后的新感知永远进不来）
        existing = set()
        try:
            for line in open(out, encoding='utf-8'):
                m = re.match(r'- (\d{4}-\d{2}-\d{2} \d{2}:\d{2})', line)
                if m:
                    existing.add(m.group(1))
        except Exception:
            pass
        new_rows = [r for r in rows if r[0] not in existing]
        if not new_rows:
            print('本周已归档（无新增）'); return
        with open(out, 'a', encoding='utf-8') as f:
            for t, app, note in new_rows[-50:]:
                f.write('- %s | %s | %s\n' % (t, app, note))
        print('增量归档 %d 条 → %s' % (len(new_rows), os.path.basename(out)))
        return
    with open(out, 'w', encoding='utf-8') as f:
        f.write('# 感知归档（%s）\n\n' % today)
        f.write('> 只收有效感知条目（非「未取到」），来源：感知/感知日志.md\n\n')
        if not rows:
            f.write('本周无有效感知（手机操控中断或全部未取到）。\n')
        else:
            for t, app, note in rows[-50:]:
                f.write('- %s | %s | %s\n' % (t, app, note))
    print('已归档 %d 条 → %s' % (len(rows), os.path.basename(out)))

if __name__ == '__main__':
    main()
