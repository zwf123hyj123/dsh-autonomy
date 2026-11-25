#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日常巡检：一次查完关键状态，给判据不给感觉。

用法：python3 巡检.py [--quiet]
  --quiet 时只在有异常时输出（给定时任务用）
"""
import sys, os, json, subprocess, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import state_guard as sg

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

    # 1) 引擎
    ok, code = probe(3080, '/')
    add('引擎 3080', ok, 'HTTP %s' % code)
    ok, code = probe(18326, '/v1/models', {'Authorization': 'Bearer ' + sg.GW_KEY})
    add('网关 18326', ok, 'HTTP %s' % code)

    # 2) 本地模型
    ok, code = probe(11436, '/api/version')
    add('Ollama 11436', ok, 'HTTP %s' % code)

    # 3) 配置（state_guard 内置三项）
    for name, path, field, expect in sg.BUILTIN_CHECKS:
        ok, detail = sg.check_json_field(path, field, expect)
        add('配置·' + name, ok, detail if not ok else '')

    # 4) 网关模型真实出字
    for model in ['our-free-model/glm-cn/glm-4-flash', 'chatanywhere/deepseek-chat', 'deepseek-official/deepseek-flash']:
        ok, detail = sg.check_gateway(model)
        add('模型·' + model.split('/')[-1], ok, detail if not ok else '')

    # 5) 虚拟引擎
    add('虚拟引擎常驻', proc_running('虚拟引擎.py --watch'), '')

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
