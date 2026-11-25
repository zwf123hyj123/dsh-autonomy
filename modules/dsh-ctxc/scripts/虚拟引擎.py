#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""虚拟引擎 · 只读热备（对应痛点方案 2 的完整版，引路人 2026-11-25 定调：只读不干活，挂了换一下）

设计：
- **只读**：只读主引擎的配置文件与状态（cordis.patch.yml / settings.json），算 hash 记录变化；
  绝不写主引擎的任何文件、不接会话、不处理请求。
- **不干活**：默认只做预检 + 健康探测 + 配置同步记录，CPU 占用接近 0。
- **换一下**：探测到主引擎全挂（3080/18326 都不通）→ 用同一套启动命令拉起（切换）。

用法：
  python3 虚拟引擎.py --check     # 单次预检 + 探测 + 同步记录
  python3 虚拟引擎.py --watch     # 常驻热备（30 秒一轮）
  python3 虚拟引擎.py --dry       # 只看状态，不做任何动作
"""
import sys, os, json, time, hashlib, subprocess, urllib.request, urllib.error

HOME = os.path.expanduser('~')
DSH_HOME = os.environ.get('DSH_HOME') or os.path.join(HOME, '.dsh')
PROFILE = os.environ.get('DSH_PROFILE') or 'web'
CONFIG_FILES = [
    os.path.join(DSH_HOME, 'profiles', PROFILE, 'cordis.patch.yml'),
    os.path.join(DSH_HOME, 'our-free-model', 'settings.json'),
    os.path.join(DSH_HOME, '.credentials.yaml'),
]
PORTS = [
    ('dsh-web', 3080, '/'),
    ('gateway', 18326, '/v1/models'),
]
LAUNCH = [
    '/opt/node/bin/node', '--import=/opt/dsh-go/boot-cache.mjs',
    '/opt/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js', 'web',
    '--patch', '/etc/dsh-app/dsh-web.patch.yml',
    '--patch', '/opt/dsh-app/speech.patch.yml',
    '--patch', '/opt/dsh-app/auth/auth.patch.yml',
    '--patch', '/opt/dsh-app/search.patch.yml',
    '--patch', '/opt/dsh-app/phone/phone.patch.yml',
    '--host', '127.0.0.1', '--port', '3080', '--no-open',
]
STATE_DIR = os.path.join(DSH_HOME, 'engine-standby')
STATE_FILE = os.path.join(STATE_DIR, 'state.json')
LOG = '/tmp/engine-standby.log'
INTERVAL = 30

def log(msg):
    line = time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n'
    try:
        os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
        open(LOG, 'a').write(line)
    except Exception:
        pass

def sha(path):
    try:
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()[:16]
    except Exception:
        return None

def preflight():
    """只读预检：配置文件在不在、能不能解析"""
    problems = []
    for p in CONFIG_FILES:
        if not os.path.exists(p):
            problems.append('缺文件: ' + p); continue
        if p.endswith('.json'):
            try: json.load(open(p))
            except Exception as e: problems.append('JSON 解析失败: %s (%s)' % (p, str(e)[:60]))
        elif p.endswith('.yml') or p.endswith('.yaml'):
            r = subprocess.run(['python3','-c','import sys,yaml;yaml.safe_load(open(sys.argv[1]))', p],
                               capture_output=True, text=True, timeout=10)
            if r.returncode != 0:
                problems.append('YAML 解析失败: %s (%s)' % (p, (r.stderr or '').strip().split('\n')[-1][:60]))
    return problems

def sync_state():
    """只读同步：记录配置 hash，变化只记录"""
    try:
        old = json.load(open(STATE_FILE))
    except Exception:
        old = {}
    cur = {}
    changed = []
    for p in CONFIG_FILES:
        h = sha(p)
        cur[os.path.basename(p)] = h
        if h and old.get(os.path.basename(p)) not in (None, h):
            changed.append(os.path.basename(p))
    state = {'at': int(time.time()), 'files': cur, 'changes': old.get('changes', []) + changed}
    state['changes'] = state['changes'][-50:]
    try:
        os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
        tmp = STATE_FILE + '.tmp'
        json.dump(state, open(tmp, 'w'), ensure_ascii=False, indent=1)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        log('state 写入失败: ' + str(e)[:80])
    if changed:
        log('配置变化: ' + ', '.join(changed))
    return changed

def probe():
    out = []
    for name, port, path in PORTS:
        ok = False
        try:
            req = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path),
                                         headers={'Authorization': 'Bearer ofm-iVnqctXF-pb0Xf7jCUifSyjZtrrV9wtN'})
            with urllib.request.urlopen(req, timeout=4) as r:
                ok = r.status in (200, 401, 404, 405)
        except urllib.error.HTTPError as e:
            # 401/403 说明服务活着，只是要鉴权
            ok = e.code in (200, 401, 403, 404, 405)
        except Exception:
            ok = False
        out.append((name, port, ok))
    return out

def switch():
    """主引擎全挂 → 用同一套配置拉起（切换）"""
    log('主引擎全挂，虚拟引擎切换：拉起')
    try:
        os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
        out = open(os.path.join(STATE_DIR, 'launch.log'), 'ab')
        subprocess.Popen(LAUNCH, stdout=out, stderr=out, start_new_session=True, close_fds=True)
    except Exception as e:
        log('拉起失败: ' + str(e)[:100]); return False
    for _ in range(30):
        time.sleep(2)
        if any(ok for _, _, ok in probe()):
            log('切换成功，主引擎已恢复')
            return True
    log('切换失败（60 秒未就绪）')
    return False

def once(dry=False):
    problems = preflight()
    states = probe()
    changed = sync_state()
    alive = any(ok for _, _, ok in states)
    print('预检: ' + ('OK' if not problems else '; '.join(problems)))
    print('探测: ' + ', '.join('%s:%d%s' % (n, p, '✓' if ok else '✗') for n, p, ok in states))
    print('配置同步: ' + ('变化 %s' % ', '.join(changed) if changed else '无变化'))
    if alive:
        print('结论: 主引擎在跑，虚拟引擎待命（只读）')
        return True
    if dry:
        print('结论: 主引擎全挂（dry 模式不切换）')
        return False
    return switch()

def main():
    args = sys.argv[1:]
    if '--check' in args or not args:
        once(dry=False); return
    if '--dry' in args:
        once(dry=True); return
    if '--watch' in args:
        log('虚拟引擎启动（只读热备，%d 秒一轮）' % INTERVAL)
        while True:
            try:
                once(dry=False)
            except Exception as e:
                log('轮次异常: ' + str(e)[:120])
            time.sleep(INTERVAL)

if __name__ == '__main__':
    main()
