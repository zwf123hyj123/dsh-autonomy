#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 思维碰撞.py — 模拟大脑的关联引擎：扫描记忆层+知识层，生成候选突触；反幻门过滤。
import os, re, json, sys, time, glob

ARCHIVE = '/root/workspace/记忆档案'
REG = os.path.join(ARCHIVE, '发布清单.md')
KNOW = os.path.join(ARCHIVE, '知识')
SYN = os.path.join(ARCHIVE, '突触', 'synapses.jsonl')
CAND = os.path.join(ARCHIVE, '突触')

SPARK = os.path.join(os.path.dirname(SYN), '火花-' + time.strftime('%Y-%m-%d') + '.jsonl')
STATE = os.path.join(os.path.dirname(SYN), '.count.json')
FRAGMENTS = {'每轮对话', '后自动滚', '原文已归', '压缩失败', '知识', '一句话', '以下是', '好的', '可以'}

def is_quality(rec):
    """质量门：text >= 2 字符、from/to >= 2 字符、to 不是碎片词"""
    text = str(rec.get('text', '')).strip()
    to = str(rec.get('to', '')).strip()
    frm = str(rec.get('from', '')).strip()
    if len(text) < 2:
        return False
    if len(to) < 2 or len(frm) < 2:
        return False
    if to in FRAGMENTS or frm in FRAGMENTS:
        return False
    return True

def write_errata(note):
    """删除/缩水必须留勘误（反幻门自己也要过反幻门）"""
    try:
        path = os.path.join(os.path.dirname(SYN), '勘误-' + time.strftime('%Y-%m-%d') + '.md')
        with open(path, 'a', encoding='utf-8') as f:
            f.write('- %s %s\n' % (time.strftime('%H:%M:%S'), note))
    except Exception:
        pass

def check_shrink():
    """对比上次条数，缩水就记勘误"""
    try:
        cur = sum(1 for _ in open(SYN, encoding='utf-8'))
    except FileNotFoundError:
        cur = 0
    prev = None
    try:
        prev = json.load(open(STATE)).get('count')
    except Exception:
        pass
    if prev is not None and cur < prev:
        write_errata('突触减少 %d → %d（可能被脚本重建/清洗）' % (prev, cur))
    try:
        json.dump({'count': cur, 'at': time.strftime('%Y-%m-%d %H:%M:%S')}, open(STATE, 'w'))
    except Exception:
        pass

def load_whitelist():
    """白名单：发布清单项目名 + 项目目录名 + 记忆档案已知项目。"""
    names = set()
    try:
        txt = open(REG, encoding='utf-8').read()
        for m in re.finditer(r'\|\s*([\u4e00-\u9fa5A-Za-z0-9-]{2,20})\s*\|', txt):
            names.add(m.group(1))
    except Exception:
        pass
    try:
        for d in os.listdir(os.path.join(ARCHIVE, '项目')):
            if os.path.isdir(os.path.join(ARCHIVE, '项目', d)):
                names.add(d)
    except Exception:
        pass
    names.discard('说明')
    names.discard('项目真名')
    names = {n for n in names if not set(n) <= set('-—|')}
    return names

def scan_files():
    files = []
    for pat in [KNOW + '/*.md', ARCHIVE + '/项目/*/*/*.md', ARCHIVE + '/连续性/会话卡/*.md', ARCHIVE + '/连续性/未归档/*.md']:
        files += glob.glob(pat)
    return files

def keywords(text):
    # 中文 2-4 字词（粗粒度）+ 英文/数字标识符
    ws = set(re.findall(r'[\u4e00-\u9fa5]{2,4}', text))
    ws |= set(re.findall(r'[A-Za-z][A-Za-z0-9_-]{2,20}', text))
    stop = {'这个', '一个', '我们', '可以', '进行', '通过', '需要', '就是', '没有', '不是', '之后', '以后', 'the', 'and', 'this', 'that', 'with', 'for', 'from', 'json', 'bash', 'echo', 'true', 'false'}
    return {w for w in ws if w not in stop}

def main():
    whitelist = load_whitelist()
    files = scan_files()
    cooc = {}       # (entity, kw) -> {count, source}
    suspicious = {} # 清单外像项目名的名字 -> sources
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
        # 反幻门：清单外、像项目名（含 助手/项目/引擎/工具 且中文 3-6 字）
        for m in re.finditer(r'[\u4e00-\u9fa5]{3,6}(助手|项目|引擎|工具)', txt):
            nm = m.group(0)
            if nm in whitelist or '融合助手' in nm:
                continue
            if nm in ('思维碰撞引擎', '知识库子项目', '清单外疑似项目', '字幕提取工具', '智能体图记忆引擎', '及量化和推理引擎'):
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

    # ── 火花阶段：通点广播 + 随机突触随机连接（悟）────────────
    spark = run_spark(cands, top)
    check_shrink()
    print(json.dumps({
        '白名单实体': sorted(whitelist),
        '扫描文件': len(files),
        '候选突触': len(cands),
        '待核实': {k: sorted(v)[:3] for k, v in suspicious.items()},
        '输出': out,
        '火花': spark,
    }, ensure_ascii=False, indent=1))

# ── 火花：一个通点发给所有突触（模拟自我）+ 随机突触随机连接（一通百通）──
import random, subprocess, datetime, urllib.request

OLLAMA = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11436/v1/chat/completions')
BRAIN_MODEL = os.environ.get('BRAIN_MODEL', 'wo')

def ollama_free(prompt):
    """量子不确定性：温度拉满 2.0、熵源随机种子、3 个叠加样本并行生成后随机坍缩取一。"""
    import threading
    samples = []
    def _one():
        try:
            seed = int.from_bytes(os.urandom(4), 'big')
            body = {'model': BRAIN_MODEL,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 48, 'temperature': 2.0, 'top_p': 0.99,
                    'seed': seed, 'stream': False}
            req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=60) as r:
                samples.append((json.loads(r.read().decode())['choices'][0]['message'].get('content') or '').strip())
        except Exception:
            pass
    ts = [threading.Thread(target=_one) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return random.choice(samples) if samples else ''

def run_spark(cands, top_pairs, n_random=2):
    report = {'通点广播': 0, '随机连接': 0}
    os.makedirs(SYN.rstrip('synapses.jsonl'), exist_ok=True)
    try:
        # 1. 通点广播：新共通点发给所有突触
        common = {}
        cp = os.path.join(os.path.dirname(SYN), '..', '..', '连续性', '断点', 'common.json')
        for p in (os.path.expanduser('~/.dsh/brain/连续性/断点/common.json'),
                  '/root/workspace/记忆档案/连续性/断点/common.json', cp):
            if os.path.exists(p):
                try:
                    common = json.load(open(p, encoding='utf-8'))
                except Exception:
                    pass
                if common:
                    break
        nodes = [c['to'] for c in cands] + [c['from'] for c in cands]
        with open(SPARK, 'a', encoding='utf-8') as f:
            for h, val in list(common.items())[:5]:
                txt = str(val).strip()
                if len(txt) < 2:
                    continue  # 质量门：空共通点不发
                for node in list(dict.fromkeys(nodes))[:12]:
                    node = str(node).strip()
                    if len(node) < 2 or node in FRAGMENTS:
                        continue
                    rec = {'at': time.strftime('%Y-%m-%d %H:%M:%S'),
                           'from': '共通点:' + h, 'to': node,
                           'rel': 'spark_common', 'text': txt[:60]}
                    if is_quality(rec):
                        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                        report['通点广播'] += 1
        # 1.5 神经交流：调神经突触.py（可塑权重网络：赫布学习+衰减+不应期+胜者通吃）
        try:
            r = subprocess.run(['python3', os.path.join(os.path.dirname(os.path.abspath(__file__)), '神经突触.py')],
                               capture_output=True, text=True, timeout=300)
            if r.returncode == 0 and r.stdout.strip():
                j = json.loads(r.stdout)
                report['神经发放'] = '%d 节点 · 路径: %s' % (j.get('发放', 0), j.get('路径', '')[:60])
        except Exception:
            pass
        # 2. 悟：随机突触随机连接，本地模型自由联想
        pairs = [(a, b) for i, a in enumerate(nodes) for b in nodes[i + 1:]]
        random.shuffle(pairs)
        ins_file = os.path.join(os.path.dirname(SYN), '灵感-' + time.strftime('%Y-%m-%d') + '.md')
        lines = []
        for a, b in pairs[:n_random]:
            try:
                idea = ollama_free('自由联想，不要解释，只说一句 20 字以内的话：' + a + ' 与 ' + b + ' 之间可能有什么联系？')
            except Exception:
                idea = ''
            if idea:
                lines.append('- %s ↔ %s → %s' % (a, b, idea))
                with open(SYN, 'a', encoding='utf-8') as f:
                    f.write(json.dumps({'at': time.strftime('%Y-%m-%d %H:%M:%S'),
                                        'from': a, 'to': b, 'rel': 'spark_random',
                                        'text': idea}, ensure_ascii=False) + '\n')
                report['随机连接'] += 1
        with open(ins_file, 'w', encoding='utf-8') as f:
            f.write('# 灵感火花（%s）\n\n' % time.strftime('%Y-%m-%d'))
            f.write('\n'.join(lines) + '\n' if lines else '（本轮无火花：模型离线或无有效配对）\n')
    except Exception as ex:
        report['错误'] = str(ex)[:120]
    return report

if __name__ == '__main__':
    main()
