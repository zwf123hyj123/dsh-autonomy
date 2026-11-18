# Changelog

## 0.2.3

- README 增加「致谢与出处」（断点下载思想、Anthropic 记忆架构、量化/压缩综述与真机口径）

## 0.2.2

- ctxc.py v3：断点压缩（进度落盘、中断续传）+ 按功能/上下文分段（大段总结、小段原样保留）


## 0.2.1

- 新增 scripts/ctxc.py：混合并发压缩（本地 Ollama + 云端自动切换，支持 dsh-our-free-model 网关与任意 OpenAI 兼容端点）
- 新增 docs/：模型压缩方案、上下文压缩方案（通用版）

## 0.2.0

- 「压一下」胶囊：本地分块压缩，超容量自动转云端（当前对话）
- 每轮自动会话卡：对话原话样本滚动（turn.note）
- CI：push/PR 自动检查
- Issue 模板、Release 工作流、npm 发布工作流
