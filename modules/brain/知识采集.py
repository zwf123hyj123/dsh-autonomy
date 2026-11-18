#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# brain/知识采集.py — 外部内容入库管线：原文归档 → ctxc 云+本地并发全程压缩 → 摘要入库（带出处）。
# 用法: python3 知识采集.py <原始文件> --title 主题 --source URL
# 环境: BRAIN_ROOT(默认 ~/.dsh/brain)、CTXC_BIN(压缩脚本，默认同仓 modules/dsh-ctxc/scripts/ctxc.py)、DSH_HOME
import os, sys, argparse, subprocess, datetime, hashlib

HOME = os.path.expanduser('~')
ROOT = os.environ.get('BRAIN_ROOT', os.path.join(HOME, '.dsh', 'brain'))
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
    out = subprocess.run(['python3', CTXC, args.file, '--keep-paths'],
                         capture_output=True, text=True, timeout=3600)
    summary = out.stdout.strip()

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
