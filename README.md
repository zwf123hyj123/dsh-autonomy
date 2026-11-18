# dsh-autonomy · 自主执行模块

把「防炸」「上下文压缩」「模拟大脑」打包为可自主执行的一套模块：定时跑、断点续、失败不丢内容、全程无隐私硬编码。

## 模块

| 模块 | 目录 | 职责 |
|---|---|---|
| 防炸 anti-blowup | [modules/anti-blowup](modules/anti-blowup) | 每日体检会话；爆掉的自动抢救导出；快爆导索引；抢救产出自动压缩；命名核对（反幻门）；触发思维碰撞；知识区 git 版控 |
| 上下文压缩 dsh-ctxc | [modules/dsh-ctxc](modules/dsh-ctxc) | dsh-go 插件：「压一下」胶囊 + 每轮自动会话卡；[ctxc.py](modules/dsh-ctxc/scripts/ctxc.py)：断点压缩 + 功能分段（大段总结、小段原样）+ 本地 Ollama 与云端并发 |
| 模拟大脑 brain | [modules/brain](modules/brain) | 记忆/知识/突触/思维碰撞架构；关联引擎（白名单+待核实反幻门）；收件箱自动归档；发布清单模板 |

## 设计原则

1. **断点续传**：压缩/归档/抢救全部按进度落盘，中断重跑只补未完成部分。
2. **失败不丢内容**：任何一步失败都保留原文与指针，绝不静默吞数据。
3. **反幻门**：项目名/实体名先过发布清单白名单；原始记录不改、勘误覆盖；自动化只标「待核实」不传播。
4. **无人值守**：三模块各挂宿主定时任务（每日监控 / 每 N 小时收件箱归档 / 每 5 分钟保活），知识区本地 git 版控。
5. **无隐私硬编码**：路径全部走环境变量（见下），会话 id、账号、密钥一律不写进代码。

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| BRAIN_ROOT | ~/.dsh/brain | 知识/突触/发布清单根目录 |
| DSH_HOME | ~/.dsh | 引擎家目录 |
| INBOX_SID | 空 | 收件箱归档会话 id（前 13 位） |
| CTXC_BIN / BRAIN_BIN | 空 | 监控要调用的 ctxc/思维碰撞脚本路径 |
| CTXC_API / CTXC_MODEL | 127.0.0.1:11436 / qwen2.5:1.5b-instruct | 本地压缩端点（见 dsh-ctxc README） |

## 部署（宿主为 DSH 时）

1. 装 dsh-ctxc 插件：\`dsh plugin --profile web add <modules/dsh-ctxc>\`
2. 建三个定时任务（宿主调度器）：
   - 每日 23:50：\`python3 modules/anti-blowup/monitor.py\`（环境变量带 CTXC_BIN、BRAIN_BIN）
   - 收件箱归档（错开心跳半小时）：\`python3 modules/brain/收件箱归档.py\`
   - Ollama 保活（每 5 分钟）：检查本地端口，不在就重启 serve
3. 首次运行前：按 [发布清单模板](modules/brain/发布清单模板.md) 建好自己的 BRAIN_ROOT/发布清单.md。

## 出处与致谢

- 记忆分层与 Dreaming 回查纠错思想：Anthropic《The components of agent memory》
- 断点/分段压缩参数：手机 proot + Ollama 1.5B Q4_K_M 实测口径（见 dsh-ctxc 文档）
- 会话抢救工具依赖宿主自带的 lazarus skills（rescue.mjs）

## License

MIT
