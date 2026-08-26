# StudyPilot

面向国际研究生的双语 AI 学习教练。上传课程资料后，StudyPilot 基于这些资料带引用地讲解概念、生成可批改的练习、依据 rubric 评分，并根据实际掌握度安排复习计划。

所有回答都锚定在用户自己上传的资料上，不使用通识知识补齐资料未覆盖的内容。

## 文档

- [产品需求文档](docs/PRD.md)
- [技术设计文档](docs/TECHNICAL_DESIGN.md)
- [Agent 架构演进路线](docs/ECHOMIND_ARCHITECTURE_MIGRATION.md)
- [开发进度台账](docs/PROGRESS.md) —— 跨 AI Agent 交接的唯一事实来源
- [AI Agent 协作规约](AGENTS.md)
- [PRD 实现差距审计](docs/IMPLEMENTATION_AUDIT.md)

## 快速开始

```bash
cp .env.example .env        # 按需填写模型密钥
docker compose up -d --build
```

- Web 工作台：<http://localhost:8000/>
- Swagger：<http://localhost:8000/docs>

不配置模型密钥也能完成上传、检索和引用链路验证 —— 此时返回可验证的检索结果而非生成式回答。配置后可获得带 `[c1]` 引用的完整讲解：

```env
STUDYPILOT_ANTHROPIC_API_KEY=your_api_key
STUDYPILOT_ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

## 能做什么

- 创建课程、设置考试日期，上传 PDF / Markdown / TXT 资料。
- 后台 Worker 异步解析、分段并写入 ChromaDB，可查看处理状态。
- 按课程、资料类型、指定文档和页码范围隔离检索，支持"资料1""第二份 PDF"这类指代。
- 多轮对话讲解，带文件名与页码引用，引用可展开原文并跳转到 PDF 对应页。
- 生成带来源和 rubric 的单选题、简答题、概念解释题。
- 依据不可变 rubric 自动批改，给出逐项得分、错误定位和改进建议。
- 汇总作答记录形成掌握度与薄弱知识点，据此生成可勾选的学习计划。
- 学术诚信判定：作业代写与实时考试作弊不提供答案，但继续提供合规的学习帮助。

## 架构

```text
统一聊天入口
  ↓
混合 LearningIntentRouter          规则优先；仅低置信度、模糊和复合请求调用 LLM
  ↓  RoutingDecision + QueryPlan
学术诚信 Guard                     四级判定，在任何 Agent 之前运行
  ↓
LearningAgentOrchestrator          按 execution_mode 分派，串行时传递上下文
  ├─ TutorAgent      课程问答与概念讲解
  ├─ QuizAgent       练习生成
  ├─ EvaluatorAgent  rubric 批改
  ├─ PlannerAgent    学习计划读取与生成
  └─ Progress / Catalog / General
  ↓
TeachingToolManager                9 个教学工具，统一做课程归属与资料范围校验
  ↓
AgentResult + AgentTrace
```

关键约束：

- **用户显式选择的课程、资料、类型和页码范围永远不会被模型覆盖。** 这些字段不进入模型输入，工具层还会校验资料确实属于该课程，越权返回 403。
- **规则优先。** 最常见的明确请求由确定性规则零延迟解决，实测 LLM 只在约 37% 的路由用例上被调用。
- **不推倒稳定服务。** Agent 是现有 Service 的薄适配器，检索、生成、批改逻辑保持不变。

技术栈：FastAPI + PostgreSQL + ChromaDB + Redis + Docker。后端入口 `app.main:app`，API 统一 `/api/v1` 前缀。前端为 FastAPI 托管的原生 HTML/CSS/JS 工作台。

## 项目结构

```text
app/
├── main.py                     FastAPI 入口
├── api/v1/routes/              课程、资料、导师、练习、批改、进度、计划
├── agents/
│   ├── routing.py              RoutingDecision 等路由协议
│   ├── intent_router.py        混合意图路由（规则 + LLM 兜底）
│   ├── llm_router.py           结构化 LLM 路由
│   ├── protocol.py             AgentTask / LearningContext / AgentResult / AgentTrace
│   ├── orchestrator.py         多 Agent 编排
│   ├── learning_agents.py      八个 Agent 适配器
│   ├── tools.py                教学工具层与权限校验
│   ├── integrity.py            学术诚信四级 Guard
│   └── skills.py               教学 Skill 加载器
├── services/                   课程、文档、导师、练习、批改、进度、计划
├── rag/                        解析、分段、嵌入、检索
├── infrastructure/             数据库、向量库、文件存储、仓储
└── web/                        学习者工作台

skills/                         七个教学 Skill（讲解、命题、批改、复习策略等）
tests/unit/                     159 个单元测试
tests/evals/                    RAG / Quiz / Grading / Router 离线评测
docs/                           PRD、技术设计、架构路线、进度台账
```

## 测试与评测

单元测试检查代码是否正确；`tests/evals/` 下的离线评测检查模型行为是否忠于资料。

```bash
docker compose exec api python -m pytest tests/unit -q
```

七套版本化评测集，各自记录了可比较的基线和合入门槛，详见 [tests/evals/README.md](tests/evals/README.md)：

| 评测集 | 规模 | 当前基线 | 需要模型 |
|---|---|---|---|
| Router v2 | 57 例 | 混合模式意图准确率 90.4%，范围保持 100% | 部分 |
| Integrity v1 | 61 例 | 全指标满分，假阳性率 0% | 否 |
| Orchestrator v1 | 30 例 | 全指标 100% | 否 |
| Loop v1 | 5 阶段 | 闭环成立，总延迟 22.5s | 是 |
| RAG v1 | 30 题 | 引用有效率、跨资料泄漏、关键词覆盖 | 是 |
| Quiz v1 | 30 场景 | 生成成功率 96.7%，引用有效性 100% | 是 |
| Grading v1 | 10 题 × 三档 × 3 次 | 排序与重复稳定性 100%，分数区间 90% | 是 |

其中三套完全不调用模型，免费、秒级、逐位可复现，适合进 CI：

```bash
docker compose exec api python -m tests.evals.run_router_eval --rules-only
docker compose exec api python -m tests.evals.run_integrity_eval
docker compose exec api python -m tests.evals.run_orchestrator_eval
```

## 开发状态

这是一个仍在建设中的项目。当前完成度、已知问题和下一步计划以 [docs/PROGRESS.md](docs/PROGRESS.md) 为准 —— 该文件是唯一事实来源，任何参与开发的人或 AI Agent 都应先阅读它。

尚未完成的主要部分：Redis 短期学习状态、编排层版本化评测、全链路 trace 与成本监控、前端学习闭环（练习历史、错题重练、学习趋势、用户设置）。

## 项目由来

StudyPilot 由 EchoMind（一个企业级智能客服框架）迁移而来，保留了「识别—编排—执行—记忆—监控—评测」的架构骨架，但业务语义全部重建为学习场景。原客服代码已于 2026-08-26 全部移除，迁移过程见 [MIGRATION.md](MIGRATION.md)。
