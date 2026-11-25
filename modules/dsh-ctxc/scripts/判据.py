#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判据表 · 所有「什么算正常」的唯一来源。

对应模拟大脑的「突触层」：判据是节点，引用是连接。
state_guard / 巡检 / 虚拟引擎 全部从这里取判据——改一处，全处生效，不再各写一遍。

新判据只加在这里，不要在别的脚本里硬编码。
"""
import os

DSH_HOME = os.path.expanduser(os.environ.get('DSH_HOME', '~/.dsh'))
SETTINGS = os.path.join(DSH_HOME, 'our-free-model', 'settings.json')
CREDENTIALS = os.path.join(DSH_HOME, '.credentials.yaml')
CORDIS_PATCH = os.path.join(DSH_HOME, 'profiles', os.environ.get('DSH_PROFILE', 'web'), 'cordis.patch.yml')

# ---------- 配置判据：(名称, 文件, 点分字段, 期望值) ----------
CONFIG_CHECKS = [
    ('glm-cn 免费模型列表', SETTINGS, 'aggregate.providers.glm-cn.models',
     ['glm-4-flash', 'glm-4.5-flash', 'glm-5.3-flash']),
    ('siliconflow 已关闭', SETTINGS, 'aggregate.providers.siliconflow.enabled', False),
    ('combo 首项为 glm-4-flash', SETTINGS, 'combos.0.models.0', 'glm-cn/glm-4-flash'),
]

# ---------- 端口判据：(名称, 端口, 路径, 需要鉴权?) ----------
PORT_CHECKS = [
    ('引擎 3080', 3080, '/', True),
    ('网关 18326', 18326, '/v1/models', True),
    ('Ollama 11436', 11436, '/api/version', False),
]

# ---------- 网关模型判据：必须真实出字的模型 ----------
GATEWAY_MODELS = [
    'our-free-model/glm-cn/glm-4-flash',
    'chatanywhere/deepseek-chat',
    'deepseek-official/deepseek-flash',
]

# ---------- 进程判据：必须在跑的常驻进程（pattern 用于 ps 匹配） ----------
PROCESS_CHECKS = [
    ('虚拟引擎常驻', '虚拟引擎.py --watch'),
    ('Ollama 服务', 'ollama serve'),
]

# ---------- 网关鉴权 ----------
GW_KEY = 'ofm-iVnqctXF-pb0Xf7jCUifSyjZtrrV9wtN'
GW_URL = 'http://127.0.0.1:18326/v1/chat/completions'
