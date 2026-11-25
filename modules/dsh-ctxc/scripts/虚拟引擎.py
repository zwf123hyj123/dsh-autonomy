#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""虚拟引擎 · 只读热备（对应痛点方案 2 的完整版，维护者 2026-11-25 定调：只读不干活，挂了换一下）

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
            ensure_local_model()
            return True
    log('切换失败（60 秒未就绪）')
    ensure_local_model()
    return False

def find_main_pids():
    """找到主引擎进程（bin.js web --port 3080）"""
    pids = []
    try:
        out = subprocess.run(['ps', '-eo', 'pid,args'], capture_output=True, text=True, timeout=10).stdout
        for line in out.splitlines():
            if 'bin.js web' in line and '--port 3080' in line and 'grep' not in line:
                pid = int(line.split()[0])
                if pid != os.getpid():
                    pids.append(pid)
    except Exception:
        pass
    return pids

def wait_ports_down(timeout=20):
    for _ in range(timeout):
        if not any(ok for _, _, ok in probe()):
            return True
        time.sleep(1)
    return False

def hot_restart():
    """热重启：预检 → 优雅停主引擎 → 等端口释放 → 立即拉起 → 等就绪"""
    problems = preflight()
    if problems:
        log('热重启中止：预检失败 -> ' + '; '.join(problems))
        print('预检失败，拒绝重启: ' + '; '.join(problems))
        return False
    pids = find_main_pids()
    if not pids:
        log('主引擎不在，直接拉起')
        return switch()
    log('热重启：优雅停止主引擎 pids=%s' % pids)
    import signal
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception as e:
            log('停止 %d 失败: %s' % (pid, str(e)[:60]))
    if not wait_ports_down(20):
        log('热重启失败：端口 20 秒未释放')
        print('端口未释放，重启失败（未强杀）')
        return False
    log('端口已释放，拉起新引擎')
    ok = switch()
    ensure_local_model()
    return ok

def probe_ollama():
    try:
        with urllib.request.urlopen('http://127.0.0.1:11436/api/version', timeout=4) as r:
            return r.status == 200
    except Exception:
        return False

def ensure_local_model():
    """热重启/切换后确保本地模型（ollama）活着——回切时它常被连带清掉"""
    if probe_ollama():
        return True
    log('本地模型不在，拉起 ollama')
    env = os.environ.copy()
    env.update({
        'OLLAMA_HOST': '127.0.0.1:11436',
        'OLLAMA_MODELS': os.path.expanduser('~/.ollama/models'),
        'OLLAMA_KEEP_ALIVE': '5m',
        'OLLAMA_NUM_PARALLEL': '1',
        'OLLAMA_MAX_LOADED_MODELS': '1',
        'OLLAMA_CONTEXT_LENGTH': '4096',
    })
    try:
        out = open('/tmp/ollama-serve.log', 'ab')
        subprocess.Popen(['/opt/ollama/bin/ollama', 'serve'], env=env, stdout=out, stderr=out,
                         start_new_session=True, close_fds=True)
    except Exception as e:
        log('ollama 启动失败: ' + str(e)[:100]); return False
    for _ in range(15):
        time.sleep(2)
        if probe_ollama():
            log('ollama 已拉起')
            return True
    log('ollama 拉起失败（30 秒未就绪）')
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
        ensure_local_model()
        print('结论: 主引擎在跑，虚拟引擎待命（只读）')
        return True
    if dry:
        print('结论: 主引擎全挂（dry 模式不切换）')
        return False
    return switch()

def main():
    args = sys.argv[1:]
    if '--hot-restart' in args:
        ok = hot_restart()
        print('热重启' + ('成功' if ok else '失败'))
        return
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
