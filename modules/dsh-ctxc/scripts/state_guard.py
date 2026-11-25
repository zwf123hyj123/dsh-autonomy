#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""state_guard · 状态确认层（DSH 缺的那一层）

原则：**写了不算生效，读回来对上了才算。**
所有写操作走这里：写前备份 → 临时文件 → 读回 hash 校验 → 业务校验 → 原子替换；失败自动回滚。

用法：
  # 安全写 JSON（自带读回校验）
  python3 state_guard.py write-json <path> <json-file>

  # 只读检查：字段等值
  python3 state_guard.py check-json <path> <点分字段> <期望JSON>

  # 检查内置配置：glm 免费模型 / siliconflow 关闭 / combo 顺序
  python3 state_guard.py check-config

  # 检查网关某模型能出字（会发一次 hi）
  python3 state_guard.py check-gateway <model-id>
"""
import sys, os, json, shutil, hashlib, tempfile, subprocess, urllib.request, time

DSH_HOME = os.path.expanduser(os.environ.get('DSH_HOME', '~/.dsh'))
SETTINGS = os.path.join(DSH_HOME, 'our-free-model', 'settings.json')
GW = 'http://127.0.0.1:18326/v1/chat/completions'
GW_KEY = 'ofm-iVnqctXF-pb0Xf7jCUifSyjZtrrV9wtN'


class GuardError(Exception):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data, backup=True):
    """写前备份 → 写临时文件 → 读回 hash → 原子替换。data 为 bytes 或 str。"""
    if isinstance(data, str):
        data = data.encode('utf-8')
    tmp = path + '.sg-tmp'
    bak = path + '.sg-bak'
    if backup and os.path.exists(path):
        shutil.copy2(path, bak)
    with open(tmp, 'wb') as f:
        f.write(data)
    got = open(tmp, 'rb').read()
    if sha(got) != sha(data):
        os.remove(tmp)
        raise GuardError('写后 hash 不一致：%s' % path)
    os.replace(tmp, path)
    return sha(data)


def write_json(path, obj, backup=True):
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    digest = atomic_write(path, text, backup=backup)
    # 业务校验：能重新解析且与对象相等
    back = json.load(open(path))
    if back != obj:
        if backup and os.path.exists(path + '.sg-bak'):
            shutil.copy2(path + '.sg-bak', path)
        raise GuardError('写后解析不一致：%s' % path)
    return digest


def get_field(obj, dotted):
    cur = obj
    for part in dotted.split('.'):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if cur is None:
            return None
    return cur


def check_json_field(path, dotted, expect):
    try:
        obj = json.load(open(path))
    except Exception as e:
        return False, '读取/解析失败: %s' % str(e)[:80]
    got = get_field(obj, dotted)
    if got == expect:
        return True, 'ok'
    return False, '实际=%r 期望=%r' % (got, expect)


def check_gateway(model, timeout=25):
    body = json.dumps({
        'model': model,
        'messages': [{'role': 'user', 'content': 'hi'}],
        'max_tokens': 4,
    }).encode()
    req = urllib.request.Request(GW, data=body, headers={
        'Authorization': 'Bearer ' + GW_KEY,
        'Content-Type': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        if data.get('choices'):
            return True, 'ok'
        return False, str(data.get('error', data))[:120]
    except Exception as e:
        return False, str(e)[:120]


BUILTIN_CHECKS = [
    ('glm-cn 免费模型列表', SETTINGS, 'aggregate.providers.glm-cn.models',
     ['glm-4-flash', 'glm-4.5-flash', 'glm-5.3-flash']),
    ('siliconflow 已关闭', SETTINGS, 'aggregate.providers.siliconflow.enabled', False),
    ('combo 首项为 glm-4-flash', SETTINGS, 'combos.0.models.0', 'glm-cn/glm-4-flash'),
]


def cmd_check_config():
    all_ok = True
    for name, path, field, expect in BUILTIN_CHECKS:
        ok, detail = check_json_field(path, field, expect)
        all_ok = all_ok and ok
        print(('✓ ' if ok else '✗ ') + name + ('' if ok else ' — ' + detail))
    print('结论：' + ('全部通过' if all_ok else '有未通过项'))
    return all_ok


def main():
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print(__doc__); return
    cmd = args[0]
    if cmd == 'write-json' and len(args) >= 3:
        obj = json.load(open(args[2]))
        print('已写并校验：' + write_json(args[1], obj)); return
    if cmd == 'check-json' and len(args) >= 4:
        expect = json.loads(args[3])
        ok, detail = check_json_field(args[1], args[2], expect)
        print(('✓ ' if ok else '✗ ') + detail); return
    if cmd == 'check-config':
        sys.exit(0 if cmd_check_config() else 1)
    if cmd == 'check-gateway' and len(args) >= 2:
        ok, detail = check_gateway(args[1])
        print(('✓ ' if ok else '✗ ') + detail)
        sys.exit(0 if ok else 1)
    print('未知命令或参数不足，见 --help'); sys.exit(2)


if __name__ == '__main__':
    main()
