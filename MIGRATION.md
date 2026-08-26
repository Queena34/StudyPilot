# StudyPilot 迁移说明

StudyPilot 由 EchoMind（一个企业级智能客服框架）迁移而来，目标是构建面向国际研究生的双语 AI 学习教练。

## 迁移策略

保留 EchoMind「识别—编排—执行—记忆—监控—评测」的架构骨架，但**不复用任何客服领域代码**。Agent、工具、状态和评测全部按学习场景重建。

| EchoMind 设计 | StudyPilot 实现 |
|---|---|
| 混合意图识别 | `app/agents/intent_router.py` 规则优先 + 低置信度 LLM 兜底 |
| AgentOrchestrator | `app/agents/orchestrator.py` |
| General / Technical / Billing Agent | Tutor / Quiz / Evaluator / Planner 等八个 Agent |
| ToolManager | `app/agents/tools.py`，带课程归属与资料范围校验 |
| SkillLoader | `app/agents/skills.py` + `skills/` 下七个教学 Skill |
| ChromaDB RAG | `app/rag/`，元数据改为用户、课程、资料类型、页码 |
| Evaluator | `tests/evals/` 下四套版本化评测集 |
| Docker Compose 部署 | 沿用，入口改为 `app.main:app` |

## 旧代码清理

2026-08-26（路线图第 11 步）删除了全部 EchoMind 客服代码，共约 4100 行 Python：

```text
core/          意图识别、LLM 工具、Skill 加载器
agents/        客服 Agent 编排
mcp/           工具管理器、客服知识库
memory/        Redis 对话记忆
monitor/       客服性能监控
evaluation/    客服端到端评测
api/main.py    旧 EchoMind 入口
```

同时删除了 EchoMind 时代的部署脚本（`docker-deploy.sh`、`run-image.sh`、`build-image.sh`）和旧环境变量模板（`.env.example.env`），并把三个客服 Skill 替换为七个教学 Skill。

删除前已确认：`app/` 与 `tests/` 不引用任何上述模块，`docker-compose.yml` 与 `Dockerfile` 也不引用被删的脚本。删除后 159 个单元测试全部通过，应用与四套评测均正常。

这些代码仍可从 Git 历史中取回，但**不应重新启用** —— 它们是客服语义，与 StudyPilot 的学习场景不兼容。

## 未复制的内容

- 原项目 Git 历史
- 真实 `.env` 配置和密钥
- Python 虚拟环境与 ChromaDB 本地数据
- 日志、缓存和 IDE 配置

## 当前状态

迁移已完成，后续演进以 [Agent 架构路线图](docs/ECHOMIND_ARCHITECTURE_MIGRATION.md) 为准，实际进度见 [开发进度台账](docs/PROGRESS.md)。
