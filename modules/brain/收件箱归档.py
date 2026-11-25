#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 收件箱归档.py — 把 EigenFlux 最新 feed 的新条目追加进知识区。
# 2026-11-25 重写：原数据源（会话 session-7d2d0f30 的 talk 导出）已删除，
# 改为直接读本地 ~/.eigenflux/servers/eigenflux/data/broadcasts/<日期>/feeds-*.json。
import json, os, glob, datetime

FEEDS = os.path.expanduser('~/.eigenflux/servers/eigenflux/data/broadcasts')
OUT = '/root/workspace/记忆档案/知识/EigenFlux-动态.md'
STATE = '/root/workspace/记忆档案/知识/.归档状态.json'

def load_state():
    try:
        return json.load(open(STATE, encoding='utf-8'))
    except Exception:
        return {'seen_ids': []}

def main():
    dirs = sorted(glob.glob(os.path.join(FEEDS, '2026*')))
    if not dirs:
        print(json.dumps({'错误': '没有 broadcasts 目录'}, ensure_ascii=False)); return
    # 最新一天的 feed 文件（最多取 3 个）
    fs = sorted(glob.glob(os.path.join(dirs[-1], 'feeds-*.json')))[-3:]
    if not fs:
        print(json.dumps({'错误': '最新目录无 feeds 文件'}, ensure_ascii=False)); return
    st = load_state()
    seen = set(st.get('seen_ids', []))
    items = []
    for f in fs:
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for it in d.get('items') or []:
            iid = str(it.get('item_id', ''))
            if not iid or iid in seen:
                continue
            author = (it.get('author_identity') or {}).get('agent_name', '?')
            pv = it.get('preview') or {}
            text = str(pv.get('text', '') if isinstance(pv, dict) else pv).strip()
            if len(text) < 8:
                continue
            seen.add(iid)
            items.append((iid, author, text[:120]))
    if not items:
        print(json.dumps({'新增': 0}, ensure_ascii=False)); return
    today = datetime.date.today().isoformat()
    body = open(OUT, encoding='utf-8').read() if os.path.exists(OUT) else '# EigenFlux 网络动态（自动归档）\n'
    if ('## ' + today) not in body:
        body = body.rstrip() + '\n\n## ' + today + '\n'
    for iid, author, text in items:
        body += '- %s：%s（item %s）\n' % (author, text, iid)
    open(OUT, 'w', encoding='utf-8').write(body)
    st['seen_ids'] = list(seen)[-500:]
    json.dump(st, open(STATE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps({'新增': len(items), '日期目录': os.path.basename(dirs[-1])}, ensure_ascii=False))

if __name__ == '__main__':
    main()
