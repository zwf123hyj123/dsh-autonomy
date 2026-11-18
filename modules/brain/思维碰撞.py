#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# brain/思维碰撞.py — 关联引擎：扫记忆层+知识层，生成候选突触；反幻门过滤。
# BRAIN_ROOT (默认 ~/.dsh/brain)：知识、突触、发布清单都从这读。
import os, re, json, time, glob

HOME = os.path.expanduser('~')
ROOT = os.environ.get('BRAIN_ROOT', os.path.join(HOME, '.dsh', 'brain'))
REG = os.path.join(ROOT, '发布清单.md')
KNOW = os.path.join(ROOT, '知识')
SYN = os.path.join(ROOT, '突触', 'synapses.jsonl')
CAND = os.path.join(ROOT, '突触')

def load_whitelist():
    names = set()
    try:
        txt = open(REG, encoding='utf-8').read()
        for m in re.finditer(r'\|\s*([\u4e00-\u9fa5A-Za-z0-9-]{2,20})\s*\|', txt):
            names.add(m.group(1))
    except Exception:
        pass
    try:
        for d in os.listdir(os.path.join(ROOT, '项目')):
            if os.path.isdir(os.path.join(ROOT, '项目', d)):
                names.add(d)
    except Exception:
        pass
    for junk in ('说明', '项目真名', '---'):
        names.discard(junk)
    names = {n for n in names if not set(n) <= set('-—|')}
    return names

def scan_files():
    files = []
    for pat in [KNOW + '/*.md', ROOT + '/项目/*/*/*.md', ROOT + '/连续性/会话卡/*.md', ROOT + '/连续性/未归档/*.md']:
        files += glob.glob(pat)
    return files

def keywords(text):
    ws = set(re.findall(r'[\u4e00-\u9fa5]{2,4}', text))
    ws |= set(re.findall(r'[A-Za-z][A-Za-z0-9_-]{2,20}', text))
    stop = {'这个', '一个', '我们', '可以', '进行', '通过', '需要', '就是', '没有', '不是', '之后', '以后', 'the', 'and', 'this', 'that', 'with', 'for', 'from', 'json', 'bash', 'echo', 'true', 'false'}
    return {w for w in ws if w not in stop}

def main():
    whitelist = load_whitelist()
    files = scan_files()
    cooc = {}
    suspicious = {}
    for f in files:
        try:
            txt = open(f, encoding='utf-8').read()[-8000:]
        except Exception:
            continue
        kws = keywords(txt)
        for e in whitelist:
            if e in txt:
                for k in kws:
                    if k == e:
                        continue
                    key = (e, k)
                    if key not in cooc:
                        cooc[key] = {'count': 0, 'source': f}
                    cooc[key]['count'] += 1
        for m in re.finditer(r'[\u4e00-\u9fa5]{3,6}(助手|项目|引擎|工具)', txt):
            nm = m.group(0)
            if nm in whitelist:
                continue
            if any(w in nm for w in ('你我他的个所有内等重启')):
                continue
            suspicious.setdefault(nm, set()).add(f)
    top = sorted(cooc.items(), key=lambda kv: -kv[1]['count'])[:30]
    cands = [{
        'from': e, 'to': k, 'rel': 'cooccur', 'count': v['count'],
        'source': v['source'], 'verified': e in whitelist,
    } for (e, k), v in top]
    os.makedirs(CAND, exist_ok=True)
    out = os.path.join(CAND, '候选-' + time.strftime('%Y-%m-%d') + '.json')
    json.dump(cands, open(out, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({
        '白名单实体': sorted(whitelist),
        '扫描文件': len(files),
        '候选突触': len(cands),
        '待核实': {k: sorted(v)[:3] for k, v in suspicious.items()},
        '输出': out,
    }, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()
