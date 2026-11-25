#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引擎保活（对应处理方案 2 的退化版）。
想法：完整的「虚拟引擎进程 + 双实例热备」在手机上内存不够（dsh 约 760MB、加浏览器常驻就紧张）。
退化做法：只做「健康检查 + 挂了拉起」——不主动 kill，只在探测不到时重启引擎。

用法：
  python3 引擎保活.py          # 检查并按需拉起
  python3 引擎保活.py --dry    # 只检查不拉起
"""
import subprocess, sys, os, time, json, urllib.request

PORTS = [
    ('dsh-web', 3080, '/'),
    ('our-free-model-gateway', 18326, '/v1/models'),
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
LOG = '/tmp/engine-watchdog.log'

def probe(port, path):
    try:
        req = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path),
                                     headers={'Authorization': 'Bearer ofm-iVnqctXF-pb0Xf7jCUifSyjZtrrV9wtN'})
        with urllib.request.urlopen(req, timeout=4) as r:
            return r.status in (200, 401, 404, 405)
    except Exception:
        return False

def log(msg):
    line = time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n'
    try:
        open(LOG, 'a').write(line)
    except Exception:
        pass

def main():
    dry = '--dry' in sys.argv
    states = [(name, port, probe(port, path)) for name, port, path in PORTS]
    for name, port, ok in states:
        log('%s:%d %s' % (name, port, 'OK' if ok else 'DOWN'))
    if any(ok for _, _, ok in states):
        print('引擎在跑：' + ', '.join('%s%s' % (n, '✓' if ok else '✗') for n, _, ok in states))
        return
    if dry:
        print('引擎全挂（dry 模式不拉起）'); return
    log('全部端口不通，尝试拉起 dsh')
    with open('/tmp/engine-watchdog-launch.log', 'ab') as out:
        subprocess.Popen(LAUNCH, stdout=out, stderr=out, start_new_session=True, close_fds=True)
    # 等最多 60 秒
    for _ in range(30):
        time.sleep(2)
        if probe(3080, '/'):
            log('拉起成功')
            print('拉起成功'); return
    log('拉起失败（60 秒内 3080 未就绪）')
    print('拉起失败，请看 /tmp/engine-watchdog-launch.log')

if __name__ == '__main__':
    main()
