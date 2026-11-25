# dsh-ctxc

用本地 Ollama 小模型压缩上下文的 dsh-go 插件。两个功能：

1. **「压一下」胶囊**（输入框上方）：读剪贴板 → 本地模型压成中文要点 → 回贴输入框。短文本本地压（默认 ≤2600 字分块压缩），超出自动改为「云端压缩」：把指令+正文填入输入框，发送后由当前对话的云端模型压。
2. **每轮自动压缩**（回合钩子）：每轮对话结束后，后台把这一轮「用户 → 助手」的原话压成一条，滚动写入会话卡（默认 \`$DSH_HOME/ctxc-cards/<sid13>.md\`，保留 5 条）。同会话 2 分钟冷却、日志 >20MB 跳过、失败静默，不影响对话。

## 安装

仓库：本仓库（dsh-ctxc，随 dsh-autonomy 一并分发）

需要一台跑着 dsh-go 的主机和一个 Ollama 服务（本机或局域网，OpenAI 兼容端点）。

\`\`\`sh
dsh plugin --profile web add dsh-ctxc@0.2.0
# 或从 GitHub 目录安装：
dsh plugin --profile web add <本仓库目录>
\`\`\`

## 配置（环境变量，均可选）

| 变量 | 默认 | 说明 |
|---|---|---|
| \`CTXC_API\` | \`http://127.0.0.1:11436/v1/chat/completions\` | Ollama OpenAI 兼容端点 |
| \`CTXC_MODEL\` | \`qwen2.5:1.5b-instruct\` | 压缩用模型 |
| \`CTXC_CARD_DIR\` | \`$DSH_HOME/ctxc-cards\` | 会话卡目录 |
| \`CTXC_MAX_LOCAL\` | \`2600\` | 本地压缩的最大字符数（超出走云端路径） |
| \`CTXC_CHUNK\` | \`380\` | 单块上限（小模型长输入易崩，别调太大） |
| \`CTXC_MAX_TOKENS\` | \`45\` | 每块输出 token 上限 |

## 实测（手机 proot + Ollama 1.5B Q4_K_M）

- 短任务秒回；单工具 JSON 格式合规。
- 230 字以上的单次长输入会把手机小模型打挂 → 分块是硬约束。
- 分块压缩实测：3008 字 → 1133 字（62%），5 块全过。
- proot 环境 ~1.1-4 tok/s（冷/暖机差异大）。

## 模块索引与出处

| 模块 | 位置 | 出处 / 来源 |
|---|---|---|
| 「压一下」胶囊 | [lib/index.js](lib/index.js) | 手机 proot 实测版 local-ctxc 0.2.x，短文本地压、超长转当前对话云端压 |
| 每轮自动会话卡 | [lib/index.js](lib/index.js)（turn.note 段） | 连续性卡体系：每轮原话样本滚动，2 分钟冷却、20MB 日志上限 |
| 压缩 CLI | [scripts/ctxc.py](scripts/ctxc.py) | 本机 ctxc.py v3：断点续传 + 按功能/上下文分段（大段总结、小段原样）+ 本地 Ollama |
| 模型压缩方案 | [docs/compression-plan.md](docs/compression-plan.md) | 量化/蒸馏/剪枝/上下文压缩路线（实测口径见文内） |
| 上下文压缩方案 | [docs/context-compression.md](docs/context-compression.md) | 预筛原则、分块硬约束、失败回退、实测数据 |
| CI 检查 | [.github/workflows/ci.yml](.github/workflows/ci.yml) | 语法 + dshGo 清单校验（[validate.mjs](.github/scripts/validate.mjs)） |
| Issue 模板 | [.github/ISSUE_TEMPLATE/](.github/ISSUE_TEMPLATE/) | 中文问题反馈 / 功能建议表单 |
| Release 工作流 | [.github/workflows/release.yml](.github/workflows/release.yml) | 打 v* 标签自动打包 + 创建 Release |
| npm 发布 | [.github/workflows/npm-publish.yml](.github/workflows/npm-publish.yml) | 配置 NPM_TOKEN 后自动发布，未配自动跳过 |

## 方案文档

- [模型压缩方案](docs/compression-plan.md)：量化/蒸馏/混合并发压缩的完整路线
- [上下文压缩方案](docs/context-compression.md)：ctxc.py 用法、云端自动切换、失败回退
- 命令行全文压缩：`scripts/ctxc.py`（混合并发：本地 + 云端自动切换）

## 边界

- 本地小模型只做**预筛**：摘要会丢细节，关键信息请保留原文指针。
- 超过输入框容量的长文请用仓库配套的 \`ctxc.py\`（命令行全文压缩）或分次压缩。

## 致谢与出处

本项目的关键思路与参数来自以下来源（按贡献度）：

- **断点压缩**：断点下载/HTTP Range 续传思想（进度落盘 + 中断续传）。
- **记忆与连续性**：Anthropic《The components of agent memory》——四层记忆、原始记录不改、压缩后校准。
- **小模型量化实测**：ertas.ai《Q4、Q5 和 Q8 对比: GGUF 移动端量化》；mvpfactory.io《Embedding Local LLMs in Your Mobile App》（llama.cpp KMP + 4-bit 移动端工程）。
- **上下文压缩综述**：ACM《KV Cache Compression for Inference Efficiency in LLMs: A Review》；NeuralTrust《Prompt Compression Guide》。
- **剪枝 vs 量化取舍**：ACL Anthology《Revisiting Pruning vs Quantization for Small Language Models》(EMNLP 2025 Findings)。
- **工具与运行环境**：llama.cpp / GGUF / Ollama；dsh-go 插件体系；手机 proot + Ollama 1.5B Q4_K_M 实测环境。
- **云端自动切换**：dsh-our-free-model 的 chanGateway 网关（自动切换健康免费模型）。
- **测试支撑**：全部断点/分段/并发参数均为真机实测口径（见 docs 内实测数据）。

## 问题与修复

DSH 生态的 14 条常见问题、引路人的处理方案、以及已经落地的修复，全部收在 [docs/问题与修复-2026-11-25.md](docs/问题与修复-2026-11-25.md)。

配套脚本：

- `scripts/工具体检.py`：工具清单表 + 工具调用 id 一致性探测；`--fix` 修复悬空调用（备份 + 验证 + 幂等）
- `scripts/虚拟引擎.py`：只读热备 + 热重启（`--hot-restart`：预检 → 优雅停 → 立即拉起）
- `scripts/引擎保活.py`：引擎健康检查与拉起（只在探测不到时启动，不主动 kill）

## 修复类统一入口

**约定（2026-11-25，引路人定）：所有修复类工具与补丁统一并入 ctxc，不再散落。**

| 脚本 | 职责 |
|---|---|
| `scripts/state_guard.py` | **状态确认层**：写前备份→临时文件→读回 hash→业务校验→原子替换，失败回滚；内置配置/网关检查 |
| `scripts/工具体检.py` | 工具清单表 + 悬空/孤儿调用探测；`--fix` 修复（备份+验证+幂等） |
| `scripts/虚拟引擎.py` | 只读热备 + 热重启（`--hot-restart`）+ 本地模型守护 |
| `scripts/引擎保活.py` | 引擎健康检查与拉起（简化版） |

设计原则：**写了不算生效，读回来对上了才算。** 任何「成功」必须给判据。

## License

MIT
