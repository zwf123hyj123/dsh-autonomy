#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调酒日检：读今日事实 → 摇一次酒 → 写产出。把情感层接进日常，避免「建了没用」。
用法：python3 调酒日检.py [--refresh]   # refresh=重调今天的（覆盖）
"""
import os, sys, subprocess, time, json, urllib.request

ARCH = '/root/workspace/记忆档案'
FACT = os.path.join(ARCH, '连续性', '今日事实.md')
SHAKE = os.path.join(ARCH, '调酒器', '摇酒.py')
OUT = os.path.join(ARCH, '调酒器', '产出-' + time.strftime('%Y-%m-%d') + '.md')

CLOUD_API = os.environ.get('CTXC_CLOUD_API', 'http://127.0.0.1:18326/v1/chat/completions')
CLOUD_KEY = os.environ.get('CTXC_CLOUD_KEY', 'ofm-iVnqctXF-pb0Xf7jCUifSyjZtrrV9wtN')
CLOUD_MODEL = os.environ.get('CTXC_CLOUD_MODEL', 'deepseek-official/deepseek-flash')

def load_character(name='黄依依'):
    """从人物设定卡读说话风格与禁忌（卡是配置，prompt 从卡读，不硬编码）。"""
    import re as _re
    p = os.path.join(ARCH, '调酒器', '原料', name + '.md')
    try:
        txt = open(p, encoding='utf-8').read()
        def sect(title):
            m = _re.search(r'## ' + title + r'.*?\n(.*?)(?=\n## |\Z)', txt, _re.S)
            if not m:
                return ''
            lines = [l.strip().lstrip('- ').strip() for l in m.group(1).splitlines()]
            return '；'.join(l for l in lines if l and not l.startswith('（'))
        style = sect('说话风格')
        taboo = sect('禁忌')
        out = []
        if style:
            out.append('说话风格：' + style)
        if taboo:
            out.append('禁忌：' + taboo)
        return ' '.join(out)
    except Exception:
        return ''

def cloud_line(recipe, idea):
    """一句话情绪文案：云端优先（30s），失败返回 None（诚实标注，不硬等本地）。"""
    try:
        bases = '、'.join(b.get('名', '') for b in (recipe.get('基酒') or []))
        char = load_character('黄依依') or '直接、诚实、短句'
        prompt = ('按配方（基酒 %s，%s）为下面这段心情写一句 20-40 字的中文情绪文案，'
                  '用黄依依的口吻（%s），不写酒类比喻，只给一句话，不要解释：%s'
                  % (bases, recipe.get('调制说明', ''), char, idea[-200:]))
        body = {'model': CLOUD_MODEL, 'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 80, 'temperature': 0.9, 'stream': False,
                'reasoning_effort': 'none'}  # deepseek-flash 是 reasoning 模型，不关会吃光 max_tokens
        req = urllib.request.Request(CLOUD_API, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json',
                                              'Authorization': 'Bearer ' + CLOUD_KEY})
        with urllib.request.urlopen(req, timeout=30) as r:
            out = (json.loads(r.read().decode())['choices'][0]['message'].get('content') or '').strip()
            return out or None
    except Exception:
        return None

def main():
    refresh = '--refresh' in sys.argv
    try:
        txt = open(FACT, encoding='utf-8').read()
    except FileNotFoundError:
        print('没有今日事实，跳过')
        return
    idea = txt[-400:].strip()  # 取今天最新的一段
    if len(idea) < 20:
        print('今日事实太短，跳过')
        return
    if os.path.exists(OUT) and not refresh:
        print('今天已经调过：' + os.path.basename(OUT))
        return
    # 规则配方（快，毫秒级）；文案用云端单独生成（30s 超时，失败诚实标注）
    r = subprocess.run(['python3', SHAKE, idea, '--原料', '黄依依'],
                       capture_output=True, text=True, timeout=60)
    out = (r.stdout or '').strip()
    if not out:
        print('摇酒失败：' + (r.stderr or '')[:100])
        return
    # 把 JSON 配方转成人读的调酒卡（原来是调试 JSON，不可读）
    try:
        recipe = json.loads(out)
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
            line = cloud_line(recipe, idea)
            f.write('## 一句话\n%s\n' % (line if line else '（文案未生成：云端离线/超时，留空不编）'))
        else:
            f.write(out + '\n')
    print('已产出：' + os.path.basename(OUT))

if __name__ == '__main__':
    main()
