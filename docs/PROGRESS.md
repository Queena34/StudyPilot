# StudyPilot 开发进度台账

> **这是项目进度的唯一事实来源。** 任何 AI Agent（Claude Code / Codex / 其他）或人类开发者在开始工作前必须先读本文件，收工前必须更新本文件。
>
> 协作规则见 [`AGENTS.md`](../AGENTS.md)。
> 目标架构与阶段计划见 [`ECHOMIND_ARCHITECTURE_MIGRATION.md`](./ECHOMIND_ARCHITECTURE_MIGRATION.md)。
> PRD 功能差距见 [`IMPLEMENTATION_AUDIT.md`](./IMPLEMENTATION_AUDIT.md)。

| 字段 | 内容 |
|---|---|
| 台账建立日期 | 2026-08-26 |
| 当前基线 commit | `b54cb51` |
| 当前阶段 | 路线图第 1 步已完成；第 2 步（Orchestrator）未开始 |
| 参与过的执行者 | Codex（`5a2ac0a` → `47638f7`）、Claude Code（`b54cb51` 起） |

---

## 1. 路线图状态

对应 `ECHOMIND_ARCHITECTURE_MIGRATION.md` 第 6 节「推荐执行顺序」。

状态取值：`未开始` / `进行中` / `已完成` / `已阻塞`。

| # | 阶段 | 状态 | 关键文件 | 验证方式 | 备注 |
|---|---|---|---|---|---|
| 1 | 混合 `LearningIntentRouter` | 已完成 | `app/agents/routing.py`、`intent_router.py`、`llm_router.py` | `tests/evals/run_router_eval.py`（45 例，混合模式意图准确率 92.5%） | 规则优先 + 低置信度 LLM 兜底 + 澄清；范围保持 100% |
| 2 | `LearningAgentOrchestrator` | 未开始 | — | — | 编排逻辑仍在 `app/services/tutor_service.py` 条件分支中；**路由已能识别串行工作流但无人执行**，见 K-8 |
| 3 | 统一 Agent 协议（`AgentTask`/`LearningContext`/`AgentResult`/`AgentTrace`） | 进行中 | `app/agents/routing.py` | `tests/unit/test_intent_router.py` | `RoutingDecision` 已落地；`AgentTask`/`LearningContext`/`AgentResult`/`AgentTrace` 仍未定义 |
| 4 | 封装 Tutor / Quiz / Evaluator / Planner Agent | 未开始 | `app/services/*.py` | — | 以适配器包装现有 Service，不推倒重写 |
| 5 | 串行工作流 `Tutor→Quiz`、`Evaluator→Planner` | 未开始 | — | — | Planner 目前只读取计划，不具备生成能力 |
| 6 | `TeachingToolManager` | 未开始 | — | — | 8 个教学工具，统一做用户/课程/范围校验 |
| 7 | Redis 短期学习状态 | 未开始 | `app/infrastructure/` | — | Redis 当前在 compose 中已启动但主链路未使用 |
| 8 | 教学 Skills + 学术诚信 Guard | 未开始 | `skills/`（仍为旧客服 Skill） | 待建 Guard 评测集 | PRD 8.7 整块空白，四级判定未实现 |
| 9 | Router / Orchestrator / 端到端评测 | 进行中 | `tests/evals/run_router_eval.py`、`router_metrics.py` | `baselines/router_v1.json` | Router v1 已完成；Orchestrator 与端到端闭环评测未开始 |
| 10 | 链路、成本与降级监控 | 未开始 | `monitor/`、`config/prometheus.yml` | — | Prometheus 已配置，业务指标未接入 |
| 11 | 清理旧 EchoMind 客服代码 | 未开始 | `core/`、`agents/`、`mcp/`、`memory/`、`monitor/`、`evaluation/`、`skills/`、`README.md` | 全仓库无客服语义引用 | 这些顶层目录均未接入 `app/` 主链路 |
| 12 | 补齐前端学习闭环 | 未开始 | `app/web/` | — | 详见 `IMPLEMENTATION_AUDIT.md` 第 4 节 P1 |

---

## 2. 已完成的基线能力（路线图之前）

由 Codex 在 `5a2ac0a` → `47638f7` 期间完成，作为路线图工作的既有基础。**不要重复实现这些。**

- 课程 CRUD、考试倒计时
- PDF/MD/TXT 上传、安全校验、去重、后台 Worker 异步解析入 ChromaDB（Worker 轮询 PostgreSQL jobs，非 Redis 队列）
- 课程级 RAG：用户/课程隔离、资料类型/指定文档/页码范围过滤、引用验证、资料序号与文件名指代解析
- 多轮对话、三种讲解模式、引用片段展开、KaTeX 公式渲染、PDF 定位跳转
- 练习生成（三题型/难度/来源引用/rubric）、rubric 自动批改、Attempt 历史
- TopicMastery 掌握度、薄弱点、复习建议、学习计划勾选
- 响应式 Web 工作台（原生 HTML/CSS/JS，**非**技术设计文档中的 Vue 3 + Vite）
- 81 个单元测试；三套版本化离线评测：RAG（30 题）、Quiz v1（30 场景）、Grading v1（10 题，仅冒烟）

---

## 3. 已知问题清单

开工前请确认这些是否仍然存在；修复后在此标注并写入变更日志。

| ID | 问题 | 严重度 | 状态 |
|---|---|---|---|
| K-1 | PDF 页数统计存在异常样本，需单独校验 Parser 并对真实资料做页码/引用抽检 | 高 | 未修复 |
| K-2 | 引用校验失败时无修复重试；「未配置密钥」「Provider 失败」「引用校验失败」三种情形未区分暴露 | 高 | 未修复 |
| K-3 | 学术诚信 Guard 完全未实现（PRD 8.7） | 高 | 未修复 |
| K-4 | Grading v1 仅冒烟通过，缺 90 次完整基线与人工忠实度报告 | 中 | 未修复 |
| K-5 | `README.md` 约一半篇幅仍是 EchoMind 客服系统指南，损害仓库可信度 | 中 | 未修复 |
| K-6 | Redis 未承担设计中的缓存与任务队列职责 | 中 | 未修复 |
| K-7 | 无流式输出；无跨 Agent trace ID | 中 | 未修复 |
| K-8 | 路由已能输出 `supporting_agents` 与 `execution_mode=sequential`，但 `TutorService` 只执行 primary agent，串行工作流被识别却未执行 | 高 | 待路线图第 2/5 步解决 |
| K-9 | 复合意图的辅助 Agent 识别准确率仅 57.1%（4/7），模型常漏报 `supporting_agents` | 中 | 未修复 |
| K-10 | 澄清判定准确率 88.9%：`rt-ambig-004`「再来一点」被判为可执行意图而非请求澄清 | 低 | 未修复 |

---

## 4. 变更日志

> **格式约定**：最新的写在最上面。每次收工追加一条，五个字段一个都不能少。
> `commit` 填实际 hash；若尚未提交填 `未提交`。

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：完成路线图第 1 步「混合 `LearningIntentRouter`」。
  1. 新增 `app/agents/routing.py`，定义路线图 4.1 要求的结构化 `RoutingDecision`（`intent`、`primary_agent`、`supporting_agents`、`execution_mode`、`confidence`、`reason`、`query_plan`），并额外记录 `source`、`rule_confidence`、`clarification` 用于可观测性；`QueryPlan` 从 `intent_router.py` 迁入此处。
  2. 新增 `app/agents/llm_router.py`，结构化 LLM 兜底路由。输出经 Pydantic 校验，解析失败、网络异常或超时一律返回 `None` 而非抛错。
  3. 重写 `app/agents/intent_router.py` 为混合路由：规则先跑，置信度 ≥0.80 直接返回（不调模型）；低于阈值才调 LLM；LLM 置信度低于规则则拒绝其提议；最终置信度 <0.45 转为澄清。新增复合意图检测（同时命中多个规则族 → 降为 0.50 交给 LLM）和上下文追问降权（有历史且为指代式表达 → 降为 0.55）。
  4. 保留同步 `analyze()` 供无法 await 的调用方使用；`TutorService` 改调异步 `route()` 并处理新的 `clarify` 分支。
  5. `TutorMessageRead` 新增 `routing` 字段，向外暴露完整决策用于追踪与评测。
  6. 新增 Router v1 评测：45 条用例（单意图 23 / 模糊 8 / 复合 6 / 上下文追问 5 / 范围保持 3），进程内运行，无需启动 API。
- **为什么**：路线图第 6 节第 1 项，实现依据为第 4.1 节。规则优先是硬性设计约束（第 5 节「不让所有请求都经过 LLM Router」），因此没有把全部请求交给模型；实测 LLM 只在 44.4% 的用例上被调用，最常见的单意图请求全部由规则零延迟解决。
- **改了哪些文件**：
  - 新增：`app/agents/routing.py`、`app/agents/llm_router.py`、`tests/evals/router_metrics.py`、`tests/evals/run_router_eval.py`、`tests/evals/datasets/router_intents_v1.jsonl`、`tests/evals/baselines/router_v1.json`
  - 修改：`app/agents/intent_router.py`（重写）、`app/services/tutor_service.py`（改调 `route()`、新增 clarify 分支、透传 `routing`）、`app/schemas/tutor.py`（新增 `routing` 字段）、`tests/unit/test_intent_router.py`（+10 例）、`tests/evals/README.md`
- **怎么验证的**：
  - 单元测试 `102 passed`（改动前 92，新增 10）。**注意：`docker-compose.yml` 未挂载源码，必须先 `docker compose build api` 才能测到新代码。**
  - Router 规则层基线 `--rules-only`：意图准确率 70.0%、规则解决率 55.6%、范围保持 100%。
  - Router 完整混合基线：意图准确率 **92.5%**、执行模式准确率 93.3%、澄清准确率 88.9%、**范围保持 100%**、规则解决率 55.6%、LLM 调用率 44.4%、平均延迟 569ms。两种模式的结果都存入 `tests/evals/baselines/router_v1.json`（`modes.rules_only` 与 `modes.hybrid`），并在该文件的 `regression_rules` 中写明了合入门槛：`scope_preservation_rate` 必须恒为 1.0，`rules_only` 除延迟外须逐位复现，`hybrid` 意图准确率不得低于 0.90。
  - HTTP 端到端冒烟：目录查询走规则（0.99/rule）、概念讲解走规则（0.88/rule）、复合请求「先讲解残差，然后出3道选择题」正确触发 LLM 并产出 `primary=tutor, supporting=[quiz], mode=sequential`（rule_confidence 0.5 → llm 0.95）。
  - 3 条误判用例已逐条记录在基线文件中：均落在 `course_qa`/`concept_explanation` 与 `progress_review`/`planner` 两组边界上，二者路由到相同 target，对下游行为无实质影响。
- **下一步建议**：做路线图第 2 步 `LearningAgentOrchestrator`，并优先解决 **K-8** —— 路由现在已经能正确识别串行工作流，但 `TutorService` 只执行 primary agent，`supporting_agents` 被记录却从未执行。建议第 2 步与第 3 步（统一 Agent 协议）一起做：先定义 `AgentTask`/`LearningContext`/`AgentResult`/`AgentTrace`，再用适配器包装现有 `TutorService`/`PracticeService`，然后让 Orchestrator 按 `execution_mode` 分派。K-9 的辅助 Agent 识别准确率应在 Orchestrator 真正消费 `supporting_agents` 之后再调优 prompt，届时才有真实反馈信号。

---

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：建立跨 Agent 交接机制 —— 新增 `docs/PROGRESS.md`（本文件）、`AGENTS.md`、`CLAUDE.md`；如实盘点当前路线图状态、既有基线能力和 7 项已知问题。
- **为什么**：项目由 Codex 起手、Claude Code 接续，后续还会交回 Codex。此前没有任何进度台账或 agent 协作规则文件，接手方只能靠通读 commit 与源码推断进度，容易重复劳动或误判已完成范围。
- **改了哪些文件**：`docs/PROGRESS.md`（新增）、`AGENTS.md`（新增）、`CLAUDE.md`（新增）。未触碰任何运行代码。
- **怎么验证的**：无代码变更，无需测试。文档内容与 `git log`、`docs/IMPLEMENTATION_AUDIT.md`、`docs/ECHOMIND_ARCHITECTURE_MIGRATION.md` 逐条比对确认一致。
- **下一步建议**：由用户确认台账准确性后，开始路线图第 1 步「混合 `LearningIntentRouter`」——在保留现有确定性规则的前提下，新增 `RoutingDecision` 结构化 schema、低置信度 LLM 兜底路由，以及 `tests/evals/run_router_eval.py` 评测集（覆盖单意图、模糊意图、复合意图、上下文追问四类）。

---

<!-- 新条目插入在此行上方 -->
