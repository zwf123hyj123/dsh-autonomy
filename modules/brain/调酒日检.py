#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调酒日检：读今日事实 → 摇一次酒 → 写产出。把情感层接进日常，避免「建了没用」。"""
import os, subprocess, time

ARCH = '/root/workspace/记忆档案'
FACT = os.path.join(ARCH, '连续性', '今日事实.md')
SHAKE = os.path.join(ARCH, '调酒器', '摇酒.py')
OUT = os.path.join(ARCH, '调酒器', '产出-' + time.strftime('%Y-%m-%d') + '.md')

def main():
    try:
        txt = open(FACT, encoding='utf-8').read()
    except FileNotFoundError:
        print('没有今日事实，跳过')
        return
    idea = txt[-400:].strip()  # 取今天最新的一段
    if len(idea) < 20:
        print('今日事实太短，跳过')
        return
    if os.path.exists(OUT):
        print('今天已经调过：' + os.path.basename(OUT))
        return
    # 先出规则配方（快，毫秒级）；本地模型文案太慢，默认不调
    r = subprocess.run(['python3', SHAKE, idea],
                       capture_output=True, text=True, timeout=60)
    out = (r.stdout or '').strip()
    if not out:
        print('摇酒失败：' + (r.stderr or '')[:100])
        return
    # 把 JSON 配方转成人读的调酒卡（原来是调试 JSON，不可读）
    try:
        import json as _json
        recipe = _json.loads(out)
    except Exception:
        recipe = None
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('# 调酒产出（%s）\n\n' % time.strftime('%Y-%m-%d'))
        f.write('> 原料：今日事实（%d 字）\n\n' % len(idea))
        if recipe:
            emo = recipe.get('情绪识别') or []
            f.write('## 情绪识别\n%s\n\n' % ('、'.join(emo) if emo else '（无）'))
            bases = recipe.get('基酒') or []
            f.write('## 基酒配方\n')
            for b in bases:
                f.write('- %s %s（%s）：%s\n' % (b.get('emoji', ''), b.get('名', ''), b.get('类', ''), '、'.join(b.get('风味', []))))
            f.write('\n## 比例与调制\n%s\n\n' % recipe.get('调制说明', ''))
            f.write('## 一句话\n（文案待生成：本地模型离线或未调用 --ollama）\n')
        else:
            f.write(out + '\n')
    print('已产出：' + os.path.basename(OUT))

if __name__ == '__main__':
    main()
