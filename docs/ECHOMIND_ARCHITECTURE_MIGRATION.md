# EchoMind 设计理念迁移与 StudyPilot 优化路线

| 字段 | 内容 |
|---|---|
| 记录日期 | 2026-08-26 |
| 目标 | 在保留 EchoMind 核心架构思想的基础上，将 StudyPilot 演进为面向学习场景的可评测多 Agent 系统 |
| 当前基线 | StudyPilot 已具备课程 RAG、练习生成、答案批改、学习进度和确定性意图路由 |

> 本路线图各阶段的**实际完成状态**记录在 [`PROGRESS.md`](./PROGRESS.md)，开工前请先查阅。

## 1. 核心结论

保留 EchoMind 的“识别—编排—执行—记忆—监控—评测”设计骨架，但不直接复制客服领域代码。StudyPilot 需要将 Agent、工具、状态和评测全部替换为学习场景语义。

当前 StudyPilot 的主应用使用 `app/agents/intent_router.py` 中的确定性 `LearningIntentRouter` 识别意图，并由 `TutorService` 通过条件分支调用不同业务工作流。它属于“意图路由 + 多工作流编排”，还不是完整的多 Agent 协同系统。

`core/intent_recognizer.py` 和 `agents/agent_orchestrator.py` 是从 EchoMind 保留的旧客服代码，当前未接入 `app/` 主链路，不能作为 StudyPilot 已实现能力进行描述。

## 2. EchoMind 能力映射

| EchoMind 设计 | StudyPilot 当前状态 | 学习场景改造方向 |
|---|---|---|
| LLM、Embedding、Pattern 混合意图识别 | 规则与正则驱动的 `LearningIntentRouter` | 规则优先，结构化 LLM 处理低置信度和复合意图 |
| 独立 `AgentOrchestrator` | `TutorService` 内条件分支 | 建立 `LearningAgentOrchestrator` |
| General、Technical、Billing Agent | Tutor、Practice、Grading 等 Service 工作流 | 封装 Tutor、Quiz、Evaluator、Planner Agent |
| 主 Agent 与辅助 Agent | 未实现 | 支持单 Agent 和有明确依赖关系的串行协作 |
| ToolManager | Service 直接组合 Repository 与 Retriever | 建立带权限和范围校验的教学工具层 |
| Redis 工作记忆 | 主要从 PostgreSQL 对话记录恢复 | 保存当前课程、资料范围、学习主题和任务状态 |
| 用户画像与情景记忆 | 已有 `TopicMastery` 雏形 | 扩展长期学习画像和个性化上下文 |
| SkillLoader | 仍保留旧客服 Skill | 替换为教学策略 Skills |
| Monitor 与 Evaluator | 已有 RAG、Quiz、Grading 离线评测 | 增加 Router、Agent 工作流和线上链路指标 |

## 3. 目标架构

```text
用户请求
  ↓
统一聊天入口
  ↓
Hybrid LearningIntentRouter
  ├─ 显式操作/高置信度请求：确定性规则路由
  └─ 低置信度/模糊/复合请求：结构化 LLM 路由
  ↓
RoutingDecision + QueryPlan
  ↓
LearningAgentOrchestrator
  ├─ TutorAgent
  ├─ QuizAgent
  ├─ EvaluatorAgent
  └─ PlannerAgent
  ↓
TeachingToolManager
  ├─ CourseRetriever
  ├─ Course/Document Repository
  ├─ Practice/Grading Service
  ├─ Progress Repository
  └─ StudyPlan Service
  ↓
AgentResult + Trace + Metrics
```

LLM 可以帮助理解意图，但不得覆盖用户显式选择的 `course_id`、`document_ids`、资料类型和页码范围。结构化数据库查询和文档检索必须通过受控工具完成，不能由模型猜测。

## 4. 分阶段实施计划

### P0：建立原生学习 Agent 架构

#### 4.1 混合意图路由

- 保留现有确定性规则，处理高频且边界清晰的请求。
- 仅对低置信度、模糊表达和复合任务调用 LLM Router。
- 输出结构化 `RoutingDecision`，至少包含：
  - `intent`
  - `primary_agent`
  - `supporting_agents`
  - `execution_mode`
  - `confidence`
  - `reason`
  - `query_plan`
- 用户显式范围拥有最高优先级，LLM 只能补全缺失字段。
- 低置信度且可能产生不同副作用时，应向用户澄清。

#### 4.2 `LearningAgentOrchestrator`

建立独立编排层，负责：

- 选择主要 Agent 和辅助 Agent；
- 判断单 Agent、串行或并行执行；
- 传递统一学习上下文；
- 管理超时、重试、降级和中断；
- 记录完整 Agent 与工具调用轨迹；
- 合并并验证结构化执行结果。

实施时不推倒现有稳定服务，优先用 Agent 适配器包装 `TutorService`、`PracticeService`、评分逻辑和学习计划逻辑。

#### 4.3 统一 Agent 协议

统一定义：

- `AgentTask`：任务类型、输入、约束和预期输出；
- `LearningContext`：用户、课程、资料范围、对话和学习状态；
- `AgentResult`：内容、证据、状态、下一步动作和错误信息；
- `AgentTrace`：路由、工具调用、模型调用、耗时和降级记录。

Agent 职责：

- `TutorAgent`：检索、概念讲解、追问和引用回答；
- `QuizAgent`：按学习范围、题型和难度生成练习；
- `EvaluatorAgent`：依据不可变 rubric 和证据批改；
- `PlannerAgent`：依据考试日期、掌握度和错题生成学习计划。

Planner 当前主要读取已有计划，需要补充真正的计划生成能力。

### P1：实现学习场景的跨 Agent 闭环

优先实现以下串行工作流：

1. 讲解后生成练习：`Tutor → Quiz`；
2. 提交答案并更新薄弱点：`Evaluator → ProgressUpdater → Planner`；
3. 根据近期学习情况制定复习计划：`ProgressAnalyzer → Planner`。

核心演示场景：

> 用户完成指定资料第一章学习后，请求生成 10 道中等难度选择题；提交答案后，系统完成批改、更新薄弱知识点，并生成针对性复习任务。

复杂学习任务优先使用有明确数据依赖的串行协作，不为了展示多 Agent 而强行并行。

### P1：教学工具层与状态管理

#### 4.4 `TeachingToolManager`

计划提供以下工具：

- `search_course_material`
- `list_course_documents`
- `get_learning_progress`
- `get_recent_learning_context`
- `create_practice_set`
- `grade_answer`
- `update_topic_mastery`
- `create_study_plan`

工具层统一实施用户、课程和资料范围校验，并记录成功、失败、耗时和降级原因。

#### 4.5 学习记忆

Redis 保存短期工作状态：

- 当前课程和指定资料；
- 当前章节及页码范围；
- 最近讲解主题；
- 当前练习集和待批改题目；
- 当前 Agent 工作流状态。

PostgreSQL 保存长期事实：

- 对话和练习历史；
- `TopicMastery` 与错误类型；
- 学习计划和用户偏好。

ChromaDB 继续负责课程资料检索，不混合保存全部业务状态。

### P1：教学 Skills 与学术诚信

清理旧客服 Skills，并建立：

- 苏格拉底式引导；
- 分层概念讲解；
- 数学公式讲解；
- 考试复习策略；
- 选择题生成规范；
- rubric 批改规范；
- 中英双语术语解释。

在 Tutor 和 Quiz 前实现学术诚信 Guard：

- `LEARNING_ALLOWED`
- `HINT_ONLY`
- `SUBMISSION_RISK`
- `LIVE_EXAM_PROHIBITED`

Guard 决定直接回答、仅给提示或拒绝实时考试作弊，同时提供合规的学习帮助。

### P2：可观测性、评测与产品闭环

增加以下线上指标：

- 全链路 `trace_id`；
- Router 意图准确率、置信度和选择理由；
- Agent 与工具调用耗时、成功率和失败原因；
- LLM 调用次数、Token 和成本；
- 重试、超时和降级次数；
- 串行工作流完成率。

新增评测：

1. Router：单意图、模糊意图、复合意图和上下文追问；
2. Orchestrator：Agent 选择、执行顺序、上下文传递和失败降级；
3. 端到端闭环：讲解、出题、批改、薄弱点更新和复习计划；
4. 完成 Grading v1 的 90 次完整基线和人工忠实度抽检。

同时补齐练习历史、rubric 与来源展示、错题重练、学习趋势和用户偏好等产品能力。

## 5. 不照搬的设计

- 不保留 General、Technical、Billing 等客服 Agent；
- 不让所有请求都经过 LLM Router；
- 不让多个 Agent 进行无目的自由讨论；
- 不允许模型修改用户显式选择的课程和资料范围；
- 不把 ChromaDB 同时作为课程知识库、聊天记忆和业务数据库；
- 不直接启用旧 `core/` 和 `agents/` 中的客服编排代码；
- 不在实现前对外宣称 StudyPilot 已是完整多 Agent 协同系统。

## 6. 推荐执行顺序

1. 混合 `LearningIntentRouter`；
2. `LearningAgentOrchestrator`；
3. 统一 `AgentTask`、`LearningContext`、`AgentResult` 和 Trace；
4. 封装 Tutor、Quiz、Evaluator、Planner；
5. 实现 `Tutor → Quiz` 与 `Evaluator → Planner` 串行工作流；
6. 接入 `TeachingToolManager`；
7. 加入 Redis 短期学习状态；
8. 实现教学 Skills 与学术诚信 Guard；
9. 建立 Router、Orchestrator 和端到端评测；
10. 增加链路、成本和降级监控；
11. 清理旧 EchoMind 客服代码；
12. 补齐前端学习闭环。

完成前五项后，才适合在简历中表述：

> 设计混合意图路由与多 Agent 编排架构，通过规则和 LLM 协同生成结构化 QueryPlan，并支持 Tutor、Quiz、Evaluator、Planner 在复杂学习任务中的串行协作。

## 7. 验收标准

- 规则路由与 LLM 路由具有清晰触发边界；
- 所有路由输出均通过结构化 Schema 校验；
- 用户显式课程和资料范围不会被模型覆盖；
- Tutor、Quiz、Evaluator、Planner 使用统一 Agent 协议；
- 至少两个跨 Agent 串行工作流可以端到端运行；
- 每次执行可查看 route、QueryPlan、Agent 顺序、工具调用和降级原因；
- Router、Orchestrator 和端到端闭环均有版本化评测集；
- 旧客服代码不再出现在 StudyPilot 主运行链路中。
