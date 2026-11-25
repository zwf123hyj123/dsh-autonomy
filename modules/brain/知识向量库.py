#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 知识向量库.py — RAG 库段：把知识区条目向量化，存本地向量库（仅库与检索用，不替代突触）。
import os, json, glob, re, hashlib, datetime, urllib.request

BRAIN = os.environ.get('BRAIN_ROOT', '/root/workspace/记忆档案')
KNOW = os.path.join(BRAIN, '知识')
RAG = os.path.join(KNOW, '.rag')
VEC = os.path.join(RAG, 'vectors.json')
OLLAMA = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11436')
EMB = os.environ.get('EMB_MODEL', 'nomic-embed-text:latest')  # 2026-11-25 修：缺 :latest 会 400 卡 30 秒

def embed(texts):
    body = json.dumps({'model': EMB, 'input': texts}).encode()
    req = urllib.request.Request(OLLAMA + '/api/embed', data=body,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=600) as r:
        j = json.loads(r.read().decode())
    return j['embeddings']

def chunks_of(text, cap=400):
    # 2026-11-25 修：同主题重采会追加「## 更新」段；只索引最新段，
    # 旧摘要（规则兜底/压缩失败）不再进向量库，避免污染检索。
    if '\n## 更新 ' in text:
        head = text.split('\n## 更新 ')[0].split('\n')[0]
        last = '## 更新 ' + text.split('\n## 更新 ')[-1]
        text = head + '\n\n' + last
    text = re.sub(r'\n{3,}', '\n\n', text)
    out, cur = [], ''
    for para in text.split('\n\n'):
        if len(cur) + len(para) > cap and cur:
            out.append(cur.strip()); cur = ''
        cur += para + '\n\n'
    if cur.strip():
        out.append(cur.strip())
    return [c for c in out if len(c) > 20]

def main():
    files = sorted(glob.glob(KNOW + '/*.md'))
    files = [f for f in files if not any(k in f for k in ('.rag', '动态', '约定', '索引', '原始'))]
    items = []
    for f in files:
        txt = open(f, encoding='utf-8').read()
        title = os.path.basename(f).replace('.md', '')
        for i, ch in enumerate(chunks_of(txt)):
            items.append({'id': '%s#%d' % (title, i), 'text': ch[:1000]})
    os.makedirs(RAG, exist_ok=True)
    # 2026-11-25 改增量：读旧库按 text hash 复用向量，只 embed 新/变更块
    # （原来全量 256 块 × 1-2 秒 = 4-8 分钟，超过 300s 超时重建不完）
    import hashlib as _hl
    cache = {}
    try:
        _old = json.load(open(VEC, encoding='utf-8'))
        for _it in _old.get('items', []):
            if _it.get('text') and _it.get('vec'):
                cache[_hl.sha256(_it['text'].encode()).hexdigest()] = _it['vec']
    except Exception:
        pass
    need = []
    for it in items:
        h = _hl.sha256(it['text'].encode()).hexdigest()
        if h not in cache:
            need.append(it['text'])
    vecs_new = []
    for b in range(0, len(need), 16):
        vecs_new += embed(need[b:b + 16])
    idx_new = 0
    vecs = []
    for it in items:
        h = _hl.sha256(it['text'].encode()).hexdigest()
        if h in cache:
            vecs.append(cache[h])
        else:
            vecs.append(vecs_new[idx_new]); idx_new += 1
    store = {'built_at': datetime.datetime.now().isoformat(), 'emb_model': EMB,
             'items': [{'id': it['id'], 'text': it['text'], 'vec': v} for it, v in zip(items, vecs)]}
    print('增量：复用 %d / 新增 %d' % (len(items) - len(need), len(need)), file=sys.stderr)
    tmp = VEC + '.tmp'
    json.dump(store, open(tmp, 'w'), ensure_ascii=False)
    os.replace(tmp, VEC)
    print(json.dumps({'条目': len(items), '向量': len(vecs), '库': VEC}, ensure_ascii=False))

if __name__ == '__main__':
    main()
