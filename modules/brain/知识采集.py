#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# brain/知识采集.py — 外部内容入库管线：原文归档 → ctxc 云+本地并发全程压缩 → 摘要入库（带出处）。
# 用法: python3 知识采集.py <原始文件> --title 主题 --source URL
# 环境: BRAIN_ROOT(默认 ~/.dsh/brain)、CTXC_BIN(压缩脚本，默认同仓 modules/dsh-ctxc/scripts/ctxc.py)、DSH_HOME
import os, argparse, subprocess, datetime, hashlib, re

HOME = os.path.expanduser('~')
# 2026-11-25 修：默认写到 ~/.dsh/brain，但真实知识库在 /root/workspace/记忆档案
# （定时任务 prompt 里写了 BRAIN_ROOT，直接跑脚本时没有 → 写错地方）。改为自动探测。
_CANDIDATES = ['/root/workspace/记忆档案', os.path.join(HOME, '.dsh', 'brain')]
ROOT = os.environ.get('BRAIN_ROOT') or next((p for p in _CANDIDATES if os.path.isdir(p)), _CANDIDATES[-1])
KNOW = os.path.join(ROOT, '知识')
RAW = os.path.join(KNOW, '原始')
DEFAULT_CTXC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'dsh-ctxc', 'scripts', 'ctxc.py')
CTXC = os.environ.get('CTXC_BIN', DEFAULT_CTXC)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file')
    ap.add_argument('--title', required=True)
    ap.add_argument('--source', required=True, help='出处 URL 或平台名')
    args = ap.parse_args()

    text = open(args.file, encoding='utf-8').read()
    today = datetime.date.today().isoformat()
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(KNOW, exist_ok=True)

    h = hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]
    raw_name = '%s-%s-原文-%s.md' % (today, args.title, h)
    raw_path = os.path.join(RAW, raw_name)
    open(raw_path, 'w', encoding='utf-8').write(text)

    # 全文走 ctxc 混合并发（断点续传：中断重跑自动补）
    # 压缩：限时 180 秒；超时/失败走规则兜底（不让知识变空壳）
    summary = ''
    try:
        out = subprocess.run(['python3', CTXC, args.file, '--keep-paths'],
                             capture_output=True, text=True, timeout=180)
        # 2026-11-25 修：过滤 ctxc 调试行（[ctxc]/[断点]/# 来源），之前整段写进知识库污染了 16 个文件
        _lines = [ln for ln in (out.stdout or '').split('\n')
                  if not re.match(r'^\s*(\[ctxc\]|\[断点\]|# 来源:)', ln)]
        summary = '\n'.join(_lines).strip()
    except subprocess.TimeoutExpired:
        summary = ''
    except Exception:
        summary = ''
    if not summary:
        # 规则兜底：原文导语 + 含数字/结论的句子
        try:
            raw = open(args.file, encoding='utf-8', errors='ignore').read()
            import re as _re
            flat = _re.sub(r'\s+', ' ', raw).strip()
            lead = flat[:200]
            sents = _re.split(r'(?<=[。！？；])', flat)
            picks = [x.strip() for x in sents if 20 <= len(x.strip()) <= 160 and _re.search(r'\d|结论|说明|表明|发现|建议|方法|机制', x)][:3]
            summary = '**规则摘要（模型压缩超时/失败，规则兜底）**：\n\n' + lead + ('\n\n关键句：\n' + '\n'.join('- ' + x for x in picks) if picks else '')
        except Exception:
            summary = '（压缩失败，原文已归档）'

    know_path = os.path.join(KNOW, '%s-%s.md' % (today, args.title))
    header = (
        '# %s（%s）\n\n' % (args.title, today) +
        '> 来源: %s\n' % args.source +
        '> 原文: 知识/原始/%s\n' % raw_name +
        '> 压缩: ctxc 混合并发（本地 Ollama + 云端自动切换，断点续传）\n\n'
    )
    existed = os.path.exists(know_path)
    body = open(know_path, encoding='utf-8').read() if existed else header
    if existed:
        # 不重复收录：同主题文件已存在 → 追加更新段
        body = body.rstrip() + '\n\n## 更新 ' + today + '\n\n' + summary + '\n'
    else:
        body += summary + '\n'
    open(know_path, 'w', encoding='utf-8').write(body)

    # git 版控
    try:
        subprocess.run(['git', '-C', KNOW, 'add', '-A'], capture_output=True, timeout=60)
        subprocess.run(['git', '-C', KNOW, 'commit', '-qm', '采集 %s (%s)' % (args.title, today)], capture_output=True, timeout=60)
    except Exception:
        pass
    print('入库: %s（%s 字 → 摘要 %s 字；原文 %s）' % (know_path, len(text), len(summary), raw_path))

if __name__ == '__main__':
    main()
