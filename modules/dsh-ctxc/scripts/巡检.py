#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日常巡检：一次查完关键状态，给判据不给感觉。

用法：python3 巡检.py [--quiet]
  --quiet 时只在有异常时输出（给定时任务用）
"""
import sys, os, json, subprocess, urllib.request, urllib.error, glob, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import state_guard as sg
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('判据', os.path.join(HERE, '判据.py'))
_m = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_m)
J = _m

DSH_HOME = os.path.expanduser(os.environ.get('DSH_HOME', '~/.dsh'))
SETTINGS = os.path.join(DSH_HOME, 'our-free-model', 'settings.json')


def probe(port, path, headers=None):
    try:
        req = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), headers=headers or {})
        with urllib.request.urlopen(req, timeout=5) as r:
            return True, r.status
    except urllib.error.HTTPError as e:
        return e.code in (401, 403, 404, 405), e.code
    except Exception as e:
        return False, str(e)[:60]


def proc_running(pattern):
    try:
        out = subprocess.run(['ps', '-eo', 'args'], capture_output=True, text=True, timeout=10).stdout
        return any(pattern in line and 'grep' not in line and 'ps -eo' not in line for line in out.splitlines())
    except Exception:
        return False


def main():
    quiet = '--quiet' in sys.argv
    rows = []

    def add(name, ok, detail=''):
        rows.append((name, ok, detail))

    # 1) 端口（判据表）
    for name, port, path, need_auth in J.PORT_CHECKS:
        headers = {'Authorization': 'Bearer ' + sg.GW_KEY} if need_auth else None
        ok, code = probe(port, path, headers)
        add(name, ok, 'HTTP %s' % code)

    # 3) 配置（判据表）
    for name, path, field, expect in J.CONFIG_CHECKS:
        ok, detail = sg.check_json_field(path, field, expect)
        add('配置·' + name, ok, detail if not ok else '')

    # 4) 网关模型真实出字
    for model in J.GATEWAY_MODELS:
        ok, detail = sg.check_gateway(model)
        add('模型·' + model.split('/')[-1], ok, detail if not ok else '')

    # 5) 常驻进程（判据表）
    for name, pattern in J.PROCESS_CHECKS:
        add(name, proc_running(pattern), '')

    # 5.5) 浏览器与 keepalive（闲鱼值守依赖；keepalive 死了自动拉起）
    ok, code = probe(9333, '/json/version')
    add('CDP 9333', ok, 'HTTP %s' % code)
    keep = proc_running('keepalive.sh')
    if not keep:
        try:
            subprocess.Popen(['setsid', 'sh', '/root/workspace/tools/browser/daemon/keepalive.sh'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True, close_fds=True)
            add('keepalive', False, '刚发现缺失，已尝试拉起')
        except Exception as e:
            add('keepalive', False, '拉起失败：' + str(e)[:40])
    else:
        add('keepalive', True, '')

    # 6) 模拟大脑层健康（八层里能自动判的几层）
    ARCH = '/root/workspace/记忆档案'

    def newest(pattern):
        fs = glob.glob(pattern)
        return max((os.path.getmtime(f) for f in fs), default=None)

    def fresh(name, pattern, max_age_s):
        m = newest(pattern)
        if m is None:
            add('层·%s' % name, False, '无文件')
        else:
            age_h = (time.time() - m) / 3600
            add('层·%s' % name, age_h <= max_age_s / 3600, '%.1f 小时前' % age_h)

    fresh('突触', ARCH + '/突触/synapses.jsonl', 24 * 3600)
    fresh('思维流', ARCH + '/突触/思维流-*.md', 72 * 3600)
    fresh('灵感火花', ARCH + '/突触/灵感-*.md', 7 * 86400)
    fresh('调酒器', ARCH + '/调酒器/产出-*.md', 7 * 86400)
    fresh('知识', ARCH + '/知识/*.md', 7 * 86400)

    # 感知层：24 小时内必须有「有效」条目（非未取到）
    try:
        import datetime as _dt
        today = _dt.date.today().isoformat()
        txt = open(ARCH + '/感知/感知日志.md', encoding='utf-8').read()
        valid = [l for l in txt.splitlines() if today in l and '未取到' not in l and l.startswith('|')]
        add('层·感知(今日有效条目)', len(valid) > 0, '%d 条' % len(valid))
    except Exception as e:
        add('层·感知(今日有效条目)', False, str(e)[:60])

    # 6) 输出
    bad = [r for r in rows if not r[1]]
    if quiet and not bad:
        return
    print('# 巡检报告')
    for name, ok, detail in rows:
        print(('✓ ' if ok else '✗ ') + name + ('' if ok else ' — ' + detail))
    print('')
    print('结论：' + ('全部正常' if not bad else '%d 项异常' % len(bad)))
    sys.exit(0 if not bad else 1)


if __name__ == '__main__':
    main()
