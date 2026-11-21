#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# brain/本地模型注入.py — 生成带学习笔记的 prompt 前缀。
import os
HOME = os.path.expanduser('~')
NOTE = os.path.join(os.environ.get('BRAIN_ROOT', os.path.join(HOME, '.dsh', 'brain')), '本地模型学习.md')

def prompt_head(role='助手'):
    try:
        note = open(NOTE, encoding='utf-8').read()
    except Exception:
        note = ''
    return '你是使用者的%s。以下是你已学习过的知识要点（滚动笔记）：\n%s\n现在回答下面的任务，只基于学习笔记与任务本身，不编造笔记里没有的事实。\n' % (role, note[:1500])

if __name__ == '__main__':
    print(prompt_head())
