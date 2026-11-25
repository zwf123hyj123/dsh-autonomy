#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识出处体检：按采集约定四类来源，检查外部知识是否带出处；自己的产出不算违规。"""
import os, re, glob, json

ARCH = '/root/workspace/记忆档案'
KNOW = os.path.join(ARCH, '知识')
SRC = re.compile(r'来源[:：]|出处|https?://')
SELF = re.compile(r'我的总结|自拆|二次推理|读本|判据体检|判据速查|动态|对话记录|采集与学习索引|回声|我的|自评|改进建议|缺口清单|镜片|阵营图|敌友矩阵|五问')
OWN = re.compile(r'引路人[：:]|ta[：:]|我的判断|我的总结|我推|我的产|我说|我写|我整理')
INTEL = re.compile(r'^\d{4}-\d{2}-\d{2}-')

def main():
    rows = []
    for f in sorted(glob.glob(KNOW + '/*.md')):
        name = os.path.basename(f)
        try:
            txt = open(f, encoding='utf-8').read()
        except Exception:
            continue
        is_self = bool(SELF.search(name)) or bool(OWN.search(txt))
        is_external = bool(INTEL.match(name)) and not is_self
        has_src = bool(SRC.search(txt))
        if is_self:
            kind, ok = '自己的产出', True
        elif is_external:
            kind, ok = '外部知识', has_src
        else:
            kind, ok = '未分类', has_src
        if not ok:
            rows.append({'file': name, 'kind': kind, '问题': '外部知识无出处'})
    print(json.dumps({
        '知识总数': len(glob.glob(KNOW + '/*.md')),
        '违规（外部知识无出处）': len(rows),
        '清单': rows[:12],
    }, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()
