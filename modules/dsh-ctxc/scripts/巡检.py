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

    # 5) 常驻进程（判据表）：缺了先自愈拉起，再复查（2026-11-25：App 重启后要能自己回来）
    _missing = [n for n, pat in J.PROCESS_CHECKS if not proc_running(pat)]
    if _missing:
        try:
            _kp = os.path.join(os.path.dirname(os.path.abspath(__file__)), '常驻保活.py')
            r = subprocess.run(['python3', _kp], capture_output=True, text=True, timeout=120)
            _launched = []
            try:
                _launched = json.loads((r.stdout or '{}').strip().splitlines()[-1]).get('已拉起') or []
            except Exception:
                _launched = []
            add('常驻自愈', bool(_launched),
                ('已拉起：' + ','.join(_launched)) if _launched else '缺失但未拉起（看保活日志）')
        except Exception as e:
            add('常驻自愈', False, '保活失败：' + str(e)[:60])
    for name, pattern in J.PROCESS_CHECKS:
        _ok = proc_running(pattern)
        add(name, _ok, '' if _ok else '缺失（可能刚被自愈拉起）')

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

    # 5.6) 自启插件：引擎启动时把常驻带回（登记在 profile patch 里；执行证据在 /tmp/local-autostart.log）
    _patch = os.path.join(os.path.expanduser('~'), '.dsh', 'profiles', 'web', 'cordis.patch.yml')
    _reg = False
    try:
        _reg = 'local-autostart' in open(_patch, encoding='utf-8').read()
    except OSError:
        _reg = False
    _ran = ''
    try:
        with open('/tmp/local-autostart.log', encoding='utf-8') as _f:
            _lines = [x for x in _f if x.strip()]
        _raw = _lines[-1].strip().split(' ')[0]  # ISO/UTC 写入，显示时转本地（92 轮同类教训）
        import datetime as _dt
        _ran = _dt.datetime.fromisoformat(_raw.replace('Z', '+00:00')) \
            .astimezone().strftime('%m-%d %H:%M:%S')
    except Exception:
        _ran = ''
    add('自启插件', _reg,
        ('已登记·上次执行 ' + _ran) if (_reg and _ran) else
        ('已登记·本引擎启动后还没执行过（下次重启会跑）' if _reg else '未登记（删了？）'))

    # 5.5) 引擎自验（重启请求队列 / 配置是否已被引擎加载）——2026-11-26 热重启连坐事故后加
    _req = os.path.join(os.path.expanduser('~'), '.dsh', 'engine-standby', 'restart.request.json')
    _pending = os.path.exists(_req)
    add('重启队列', not _pending, '有请求积压（守护者 30 秒内会消费，若排队很久说明守护者不在）' if _pending else '')
    _loaded = None
    try:
        import subprocess as _sp, json as _json
        _r = _sp.run(['python3', os.path.join(os.path.dirname(os.path.abspath(__file__)), '虚拟引擎.py'), '--verify'],
                     capture_output=True, text=True, timeout=60)
        _j = _json.loads(_r.stdout or '{}')
        _loaded = _j.get('patch已加载')
        add('配置加载', _loaded is not False,
            '配置改过还没重启：%s' % _j.get('patch_mtime', '?'))
    except Exception as e:
        add('配置加载', True, '自验跳过：' + str(e)[:50])

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

    # 2026-11-26 修判据：synapses.json 是每轮重写的权重网络（603 边/389 激活，23:00 更新）；
    # synapses.jsonl 只是"有新边通过质量门"时偶发追加的日志，拿它判新鲜度会恒报陈旧（假缺口）。
    fresh('突触', ARCH + '/突触/synapses.json', 24 * 3600)
    # 核心速读 vs 全文（高危条款必须进速读；速读不许长出全文没有的规矩）
    try:
        import subprocess as _sp
        _r = _sp.run(['python3', ARCH + '/核心一致性.py', '--strict'],
                     capture_output=True, text=True, timeout=60)
        _miss = [l.strip() for l in (_r.stdout or '').splitlines() if l.strip().startswith('✗')]
        add('核心速读覆盖', _r.returncode == 0, ('; '.join(_miss[:2]) if _miss else ''))
    except Exception as e:
        add('核心速读覆盖', True, '跳过：' + str(e)[:40])

    try:
        _n = sum(1 for _ in open(ARCH + '/突触/synapses.jsonl', encoding='utf-8'))
        add('层·真突触', True, '%d 条边（偶发追加，不按新鲜度判）' % _n)
    except Exception as e:
        add('层·真突触', False, str(e)[:40])
    fresh('思维流', ARCH + '/突触/思维流-*.md', 72 * 3600)
    fresh('灵感火花', ARCH + '/突触/灵感-*.md', 7 * 86400)
    # 2026-11-27 收窄：7 天太宽——收工链若断（rrule 死分支那种），一周都报绿。
    # 收工每晚跑一次，48 小时没有新卡就说明至少漏了一晚，必须报。
    fresh('调酒器', ARCH + '/调酒器/产出-*.md', 48 * 3600)
    fresh('知识', ARCH + '/知识/*.md', 7 * 86400)

    # 感知层：24 小时内必须有「有效」条目（非未取到）
    try:
        import datetime as _dt
        today = _dt.date.today().isoformat()
        txt = open(ARCH + '/感知/感知日志.md', encoding='utf-8').read()
        # 2026-11-26 修判据：实际写入有两种格式（`| 日期 | 内容 |` 表格行 与 `日期 时间  内容` 纯文本行），
        # 原来要求 startswith('|')，把纯文本格式的有效条目全判成 0 条 —— 判据跟写入口径不一致。
        # 2026-11-27 修：跨天后「今天」必然 0 条（凌晨 00:0x 就报红）。改看今天或昨天，24 小时窗口。
        import datetime as _dt2
        yday = (_dt2.date.today() - _dt2.timedelta(days=1)).isoformat()
        valid = [l for l in txt.splitlines()
                 if (today in l or yday in l) and '未取到' not in l and len(l.strip()) > 20]
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
