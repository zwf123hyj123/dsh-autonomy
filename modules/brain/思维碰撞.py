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
FRAGMENTS = {'每轮对话', '后自动滚', '原文已归', '压缩失败', '知识', '一句话', '以下是', '好的', '可以',
             '后自动追', '收件箱每', '收件箱会', '阶段一', '不改旧行', '只记要点', '与出处', '继续任务',
             '需求', '子代理', 'dev', 'tmp', 'job', 'item', '未知', '可能', '没有', '什么'}

# 2 字已知实体：这些是确认的实体，不是分词碎片（is_quality 与 entity_like 共用，读写一致）
KNOWN_2 = {'酒架', '突触', '海马体', '调酒器', '模拟大脑', '德缪哥矩阵', '知识', '记忆'}

def is_quality(rec):
    """质量门：text >= 2 字符、from/to >= 2 字符、to 不是碎片词"""
    text = str(rec.get('text', '')).strip()
    to = str(rec.get('to', '')).strip()
    frm = str(rec.get('from', '')).strip()
    if len(text) < 2:
        return False
    def good_entity(x):
        return x in KNOWN_2 or len(x) >= 3
    if not good_entity(to) or not good_entity(frm):
        return False  # 2 字非已知实体多为分词碎片
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
    # 会话卡/接续卡/清单/自动归档类文件含系统提示词与流水账，不参与共现
    META = ('采集与学习索引', '采集约定', '分区', '官方源日志', '巡查日志', '自治日志',
            '_一链导入', '连续性卡', '勘误', '任务清单',
            'EigenFlux-动态', 'QQ-对话记录', '感知-2026', '网络可达性', '判据体检报告')  # 2026-11-25 修：我的总结 重新纳入碰撞；日志/会话卡文件不是知识（判断 86）
    files = []
    # 会话卡不再参与共现（含系统提示词噪音）；只扫知识层与项目文档
    # 2026-11-25 修：补 项目/*.md（项目根目录一级文件：判断库副本/人工意识/通读报告）与 项目/*/*.md（README/CHANGELOG/计划）
    for pat in [KNOW + '/*.md', ARCHIVE + '/项目/*.md', ARCHIVE + '/项目/*/*.md', ARCHIVE + '/项目/*/*/*.md', ARCHIVE + '/连续性/未归档/*.md']:
        files += [f for f in glob.glob(pat) if not any(m in os.path.basename(f) for m in META)]
    return files

def entity_like(e):
    """实体判定：排除 hash / URL 后缀 / 常见脏词（cooccur 写入与词典共用）。"""
    if not e:
        return False
    if e in KNOWN_2:
        return True  # 2 字已知实体不是碎片
    if len(e) < 3:
        return False
    if str(e).startswith('---'):
        return False
    if re.fullmatch(r'[0-9a-f]{8,}', str(e)):
        return False
    if re.search(r'\.(html|php|shtml|htm|jsp)$', str(e), re.I):
        return False
    if str(e).lower() in {'http', 'https', 'www', 'com', 'cn', 'org', 'net', 'news', 'html', 'shtml'}:
        return False
    return True

def build_entities():
    """实体词典：硬编码常见名 + 从知识动态提取专名（dsh-xxx / 大写英文名）。

    2026-11-25 改进：原来只有 35 个硬编码实体，知识里有 266 个专名抓不到，
    突触永远长不出来。现在从知识库动态提取，词典随知识生长。
    """
    ents = {'Ollama', 'EigenFlux', 'DeepSeek', 'GLM', 'ChatAnywhere', 'SiliconFlow',
            'dsh-ctxc', 'dsh-autonomy', 'dsh-knowledge', 'dsh-go', 'local-ctxc',
            'local-load-ease', 'local-ops-tune', 'fusion-assistant', 'DSH', 'Claude', 'GPT',
            '海马体', '突触', '调酒器', '酒架', '模拟大脑', '德缪哥矩阵'}
    try:
        for f in glob.glob(KNOW + '/*.md'):
            try:
                txt = open(f, encoding='utf-8', errors='ignore').read()
            except Exception:
                continue
            ents |= set(re.findall(r'\bdsh-[a-z0-9-]{2,}\b', txt))
            ents |= set(re.findall(r'\b[A-Z][a-zA-Z]{4,}\b', txt))
            # 2026-11-25 补：带连字符的专名（MNN-Pocket）、全大写缩写（SAGE）
            ents |= set(re.findall(r'\b[A-Z][a-zA-Z]{1,}(?:[-_][a-zA-Z0-9]+)+\b', txt))
            ents |= set(re.findall(r'\b[A-Z]{2,6}\b', txt))
    except Exception:
        pass
    STOP = {'The', 'And', 'This', 'That', 'With', 'For', 'From', 'Action', 'Actions', 'Article',
            'Achieves', 'Agency', 'Advice', 'Amended', 'Anti', 'Apex', 'Agents', 'Agent',
            'Model', 'Models', 'Data', 'Time', 'Type', 'Text', 'File', 'Content', 'Name',
            'Path', 'Error', 'Status', 'Item', 'Job', 'User', 'True', 'False', 'None',
            'THE', 'AND', 'THIS', 'THAT', 'WITH', 'FOR', 'FROM', 'NOT', 'YOU', 'ALL', 'CAN', 'ARE', 'WAS', 'HAS', 'BUT', 'OUR', 'OUT', 'ONE', 'TWO',
            'http', 'https', 'shtml', 'html', 'www', 'com', 'org',
            'root', 'workspace', 'auto', 'home', 'tmp', 'usr', 'kepu', 'lives', 'news', 'shtml'}
    return {e for e in ents if e not in STOP and entity_like(e)}

def keywords(text, entities=None):
    """只提实体：词典里的专名 + 英文标识符。不再做中文 2-4 字通配（那是碎片之源）。"""
    ws = set()
    if entities:
        for e in entities:
            if e and e in text:
                ws.add(e)
    ws |= set(re.findall(r'[A-Za-z][A-Za-z0-9_-]{3,20}', text))
    stop = {'the', 'and', 'this', 'that', 'with', 'for', 'from', 'json', 'bash', 'echo', 'true', 'false',
            'path', 'type', 'text', 'file', 'content', 'name', 'data', 'time', 'item', 'job', 'user',
            'python3', 'python', 'node', 'scheduled', 'background', 'null', 'none', 'error', 'status',
            'auto', 'root', 'workspace', 'kepu', 'lives', 'news', 'shtml', 'xljk', 'home', 'tmp', 'usr',
            'This', 'this', 'message', 'REMINDER', 'SCHEDULE', 'reminder',
            # 2026-11-25 补：通用技术词/配置名不是实体（判断 86：扩展抓取必须同步扩展过滤）
            'JSON', 'API', 'token', 'scripts', 'CHUNK', 'request', 'response', 'config', 'default',
            'value', 'values', 'args', 'argv', 'stdin', 'stdout', 'stderr', 'exec', 'shell', 'code',
            'version', 'plugin', 'install', 'update', 'check', 'start', 'stop', 'run', 'test', 'debug',
            'log', 'logs', 'info', 'warn', 'failed', 'before', 'after', 'changed', 'were', 'current',
            'next', 'line', 'read', 'tool', 'call', 'calls', 'b-instruct'}
    def is_const(w):
        # 配置常量（MAX_LOCAL/Q4_K_M 这类）：全大写+下划线/数字，不是语义实体
        return bool(re.fullmatch(r'[A-Z0-9_]{2,}', w)) and ('_' in w or any(c.isdigit() for c in w))
    return {w for w in ws if w not in stop and len(w) >= 3 and not is_const(w)}

def main():
    whitelist = load_whitelist()
    entities = build_entities()
    files = scan_files()
    cooc = {}       # (entity, kw) -> {count, source}
    suspicious = {} # 清单外像项目名的名字 -> sources
    for f in files:
        try:
            txt = open(f, encoding='utf-8').read()[-8000:]
        except Exception:
            continue
        kws = keywords(txt, entities)
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

    # ── 真突触：有来源的共现（cooccur）才写 synapses ────────────
    try:
        confirmed = [c for c in cands if c.get('count', 0) >= 2 and c.get('source')]
        existing = set()
        try:
            for line in open(SYN, encoding='utf-8'):
                try:
                    d0 = json.loads(line)
                    existing.add((d0.get('from'), d0.get('to')))
                except Exception:
                    pass
        except FileNotFoundError:
            pass
        with open(SYN, 'a', encoding='utf-8') as f:
            for c in confirmed[:20]:
                if (c['from'], c['to']) in existing:
                    continue
                rec = {'at': time.strftime('%Y-%m-%d %H:%M:%S'),
                       'from': c['from'], 'to': c['to'], 'rel': 'cooccur',
                       'text': '共现 %d 次 | 来源：%s' % (c['count'], os.path.basename(c['source'])),
                       'count': c['count']}
                if is_quality(rec) and entity_like(c['to']) and entity_like(c['from']) and c['to'] not in FRAGMENTS:
                    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except Exception:
        pass

    # ── 火花阶段：通点广播 + 随机突触随机连接（悟）────────────
    # 三档模式（维护者 2026-11-25）：激烈=轻度疯狂 / 恍惚=中度 / 疯狂=重度
    _mode = pick_mode(sys.argv)
    if '--no-spark' not in sys.argv:
        _pool = list(entities) if _mode else None
        spark = run_spark(cands, top, mode=_mode, nodes_override=_pool)
    else:
        spark = {'跳过': 'no-spark'}
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
import random, subprocess, urllib.request

OLLAMA = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11436/v1/chat/completions')
BRAIN_MODEL = os.environ.get('BRAIN_MODEL', 'qwen2.5:1.5b-instruct')
# 2026-11-25：火花优先走云端（本地 1.5B 3 样本并发要 20-30 秒，云端 1-2 秒）
CLOUD_API = os.environ.get('CTXC_CLOUD_API', 'http://127.0.0.1:18326/v1/chat/completions')
CLOUD_KEY = os.environ.get('CTXC_CLOUD_KEY', 'ofm-iVnqctXF-pb0Xf7jCUifSyjZtrrV9wtN')
CLOUD_MODEL = os.environ.get('CTXC_CLOUD_MODEL', 'deepseek-official/deepseek-flash')

def ollama_free(prompt, temperature=None, max_tokens=80, timeout=20):
    """火花生成：先云端（1-2 秒），失败才本地量子不确定性（2 样本并发）。
    温度夹到供应商上限 [0, 2]（超了整批 400，2026-11-25 踩过）；timeout 按档位给。"""
    if temperature is not None:
        temperature = max(0.0, min(2.0, float(temperature)))
    try:
        cbody = {'model': CLOUD_MODEL, 'messages': [{'role': 'user', 'content': prompt}],
                 'max_tokens': max_tokens, 'stream': False, 'reasoning_effort': 'none'}
        if temperature is not None:
            cbody['temperature'] = temperature
        creq = urllib.request.Request(CLOUD_API, data=json.dumps(cbody).encode(),
                                      headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + CLOUD_KEY})
        with urllib.request.urlopen(creq, timeout=timeout) as r:
            out = (json.loads(r.read().decode())['choices'][0]['message'].get('content') or '').strip()
            if out:
                return out
    except Exception:
        pass
    import threading
    samples = []
    def _one():
        try:
            seed = int.from_bytes(os.urandom(4), 'big')
            body = {'model': BRAIN_MODEL,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': max(48, min(int(max_tokens), 96)), 'temperature': 2.0, 'top_p': 0.99,
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

BAD_IDEA = ('没有', '无关', '无法', '未知', '不清楚', '不相关', '奇怪', '不存在', '可能有关', '可能是',
            # 2026-11-25 补：脑补叙事也是幻觉（反幻门）——灵感要结构关联，不要编故事
            '神秘', '操控', '阴谋', '秘密', '暗中', '隐藏已久', '背后也许', '幕后',
            # meta 评论（模型评论指令而非给答案）
            '原则', '严格', '描述', '20个字', '20 字', '自由联想', '不妥', '不符', '不如下')

HESITANT = ('奇怪', '不相关', '可能有关', '可能是', '也许')  # 犹豫词：激烈模式起放过
META_WORDS = ('原则', '严格', '描述', '20个字', '20 字', '自由联想', '不妥', '不符', '不如下')  # 恍惚起放过
NARRATIVE_WORDS = ('神秘', '操控', '阴谋', '秘密', '暗中', '隐藏已久', '背后也许', '幕后')  # 反幻门：任何档都不放

# ── 三档碰撞模式（维护者 2026-11-25 分档）─────────────────────────
# 激烈：轻度疯狂——只为那一闪而逝的火花（多配对、高温、放过犹豫词，反幻门照拦）
# 恍惚：中度疯狂——只为那条通往答案的路（二跳链：一句关联接到第三个节点，看它通向哪）
# 疯狂：重度疯狂——为了一个答案（先大量发散，最后收敛：挑出最像同一个答案的两条）
MODES = {
    'intense': {'name': '激烈碰撞', 'temp': 1.6, 'pairs': 30, 'workers': 8, 'req_timeout': 15,
                'max_tokens': 80, 'allow_hesitant': True, 'allow_meta': False,
                'chain': 0, 'converge': False, 'prefix': '激烈碰撞-', 'budget': 120},
    'trance':  {'name': '恍惚', 'temp': 1.9, 'pairs': 60, 'workers': 12, 'req_timeout': 12,
                'max_tokens': 120, 'allow_hesitant': True, 'allow_meta': True,
                'chain': 8, 'converge': False, 'prefix': '恍惚-', 'budget': 180},
    # 2026-11-25 修：供应商温度上限是 [0,2]，2.2 会 400（100 组全空、59 组超时就是它）
    'crazy':   {'name': '疯狂', 'temp': 2.0, 'pairs': 100, 'workers': 16, 'req_timeout': 10,
                'max_tokens': 160, 'allow_hesitant': True, 'allow_meta': True,
                'chain': 12, 'converge': True, 'prefix': '疯狂-', 'budget': 240},
}

def pick_mode(argv):
    """CLI → 模式名：--crazy > --trance > --intense > None(常规)"""
    for flag, mode in (('--crazy', 'crazy'), ('--trance', 'trance'), ('--intense', 'intense')):
        if flag in argv:
            return mode
    return None

def idea_ok(a, b, idea, mode=None):
    """灵感质量门：不自己连自己；不写「没关系/无法判断」这种废话。
    分档放宽：激烈放犹豫词；恍惚/疯狂连 meta 评论也放；叙事脑补（反幻门）任何档都不放。"""
    if not idea or len(str(idea).strip()) < 10:
        return False
    if a == b:
        return False
    cfg = MODES.get(mode) or {}
    bad = list(BAD_IDEA)  # 先全拦；叙事词（反幻门）永远不从 bad 里移除
    if cfg.get('allow_hesitant'):
        bad = [w for w in bad if w not in HESITANT]
    if cfg.get('allow_meta'):
        bad = [w for w in bad if w not in META_WORDS]
    # NARRATIVE_WORDS（叙事脑补=幻觉）不在任何 allow 名单里，所以始终留在 bad 中
    if any(w in str(idea) for w in bad):
        return False
    return True

def run_spark(cands, top_pairs, mode=None, nodes_override=None):
    cfg = MODES.get(mode) or {}
    report = {'模式': cfg.get('name', '常规'), '通点广播': 0, '随机连接': 0}
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
        # 只取实体（白名单 from）；cands 的 to 是分词碎片，不能当突触节点
        nodes = list(dict.fromkeys(c['from'] for c in cands))
        if nodes_override:
            # 2026-11-25 修：激烈模式扩展节点池（全量实体），否则活跃白名单只有 3 个、配不出戏
            nodes = list(dict.fromkeys(nodes + list(nodes_override)))
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
        # 2. 悟：按档位配对（激烈=轻度疯狂 / 恍惚=中度 / 疯狂=重度）
        n_pairs = cfg.get('pairs') or 2
        pairs = [(a, b) for i, a in enumerate(nodes) for b in nodes[i + 1:]]
        random.shuffle(pairs)
        _pref = cfg.get('prefix', '灵感-')
        ins_file = os.path.join(os.path.dirname(SYN), _pref + time.strftime('%Y-%m-%d') + '.md')
        lines = []
        blocked = 0
        import concurrent.futures as _cf
        _temp = cfg.get('temp')
        _mt = cfg.get('max_tokens', 80)
        _workers = cfg.get('workers', 8)
        _rt = cfg.get('req_timeout', 15)
        _budget = cfg.get('budget', 120)

        def _one_pair(ab):
            a, b = ab
            try:
                idea = ollama_free('用一句话说出 %s 和 %s 的结构关联（共同机制/相似结构/因果关系），不超过20字。只给答案：不要评论这个问题，不要解释你的回答，不要用引号。' % (a, b), _temp, _mt, _rt)
            except Exception:
                idea = ''
            return a, b, idea

        _sample = pairs[:n_pairs]
        _results = []
        _ex = _cf.ThreadPoolExecutor(max_workers=_workers)
        try:
            _futs = [_ex.submit(_one_pair, ab) for ab in _sample]
            _done, _notdone = _cf.wait(_futs, timeout=_budget)
            for _f in _done:
                try:
                    _results.append(_f.result())
                except Exception:
                    pass
            if _notdone:
                report['超时未完成'] = len(_notdone)
        finally:
            _ex.shutdown(wait=False, cancel_futures=True)

        for a, b, idea in _results:
            if idea and idea_ok(a, b, idea, mode):
                lines.append('- %s ↔ %s → %s' % (a, b, idea))
                # 火花不是突触：spark_random 只进灵感文件，不写 synapses（2026-11-25 修正）
                with open(SPARK, 'a', encoding='utf-8') as f:
                    f.write(json.dumps({'at': time.strftime('%Y-%m-%d %H:%M:%S'),
                                        'from': a, 'to': b, 'rel': 'spark_random',
                                        'text': idea}, ensure_ascii=False) + '\n')
                report['随机连接'] += 1
            elif idea:
                blocked += 1

        # 2.5 恍惚档：二跳链——把一句关联接到第三个节点，看这条路通向哪
        if cfg.get('chain') and _results:
            _pool3 = [str(x).strip() for x in nodes if str(x).strip() and str(x).strip() not in FRAGMENTS]
            _chain = []
            for _i, (a, b, idea) in enumerate([r for r in _results if r[2]][:cfg['chain']]):
                if not _pool3:
                    break
                c = _pool3[(_i * 7 + 3) % len(_pool3)]
                if c in (a, b):
                    continue
                _p = ('已知 %s 和 %s 的关系是：%s。现在把它接到 %s 上——这条链通向什么？'
                      '（不超过40字，只给答案，不要解释）') % (a, b, str(idea).strip()[:40], c)
                _t = ollama_free(_p, _temp, _mt, _rt)
                if _t and len(_t.strip()) >= 8:
                    _chain.append('- [链] %s → %s → %s：%s' % (a, b, c, _t.strip()))
            if _chain:
                lines.extend(_chain)
                report['链'] = len(_chain)

        # 2.6 疯狂档：收敛——从一堆碎片里挑出最像同一个答案的两条
        _answer = ''
        if cfg.get('converge') and lines:
            _frag = '\n'.join(lines[-40:])[:3000]
            _p = ('下面是碎片联想：\n%s\n\n挑出最像同一个答案的两条，并写出一句话的答案。'
                  '输出格式：先说一句答案，再用 || 分隔，写出你挑的那两个名词（不超过40字，只给这一行）') % _frag
            _answer = (ollama_free(_p, 1.2, 120) or '').strip()
            report['收敛'] = (_answer[:80] or '无')

        with open(ins_file, 'w', encoding='utf-8') as f:
            _name = cfg.get('name')
            if _name:
                f.write('# %s（%s）\n\n> 档位：%s · 温度 %s · 配对 %d · 链 %s\n\n' % (
                    _name, time.strftime('%Y-%m-%d'), _name, cfg.get('temp'), n_pairs, cfg.get('chain', 0)))
                f.write('> 本档容忍灰：火花混在噪声里，挑是人的事——**不当事实用**。\n\n')
            else:
                f.write('# 灵感火花（%s）\n\n' % time.strftime('%Y-%m-%d'))
            if lines:
                f.write('\n'.join(lines) + '\n')
            elif blocked:
                f.write('（本轮 %d 条候选均未过质量门：模型在线，灵感暂缺。）\n' % blocked)
                report['质量门拦截'] = blocked
            else:
                f.write('（本轮无火花：模型离线或无有效配对）\n')
            if _answer:
                f.write('\n## 收敛答案\n\n%s\n' % _answer)
        report['火花文件'] = ins_file
    except Exception as ex:
        report['错误'] = str(ex)[:120]
    return report

if __name__ == '__main__':
    main()
