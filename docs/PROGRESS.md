# StudyPilot 开发进度台账

> **这是项目进度的唯一事实来源。** 任何 AI Agent（Claude Code / Codex / 其他）或人类开发者在开始工作前必须先读本文件，收工前必须更新本文件。
>
> 协作规则见 [`AGENTS.md`](../AGENTS.md)。
> 目标架构与阶段计划见 [`ECHOMIND_ARCHITECTURE_MIGRATION.md`](./ECHOMIND_ARCHITECTURE_MIGRATION.md)。
> PRD 功能差距见 [`IMPLEMENTATION_AUDIT.md`](./IMPLEMENTATION_AUDIT.md)。

| 字段 | 内容 |
|---|---|
| 台账建立日期 | 2026-08-26 |
| 当前基线 commit | `664839e` |
| 当前阶段 | 路线图第 1、2、3 步已完成；第 4、5 步部分完成（Evaluator 未封装，见 K-12） |
| 参与过的执行者 | Codex（`5a2ac0a` → `47638f7`）、Claude Code（`b54cb51` 起） |

---

## 1. 路线图状态

对应 `ECHOMIND_ARCHITECTURE_MIGRATION.md` 第 6 节「推荐执行顺序」。

状态取值：`未开始` / `进行中` / `已完成` / `已阻塞`。

| # | 阶段 | 状态 | 关键文件 | 验证方式 | 备注 |
|---|---|---|---|---|---|
| 1 | 混合 `LearningIntentRouter` | 已完成 | `app/agents/routing.py`、`intent_router.py`、`llm_router.py` | `tests/evals/run_router_eval.py`（45 例，混合模式意图准确率 92.5%） | 规则优先 + 低置信度 LLM 兜底 + 澄清；范围保持 100% |
| 2 | `LearningAgentOrchestrator` | 已完成 | `app/agents/orchestrator.py` | `tests/unit/test_orchestrator.py`（8 例） | 按 `execution_mode` 分派、传递上下文、失败降级、全程 Trace |
| 3 | 统一 Agent 协议（`AgentTask`/`LearningContext`/`AgentResult`/`AgentTrace`） | 已完成 | `app/agents/protocol.py`、`routing.py` | `tests/unit/test_orchestrator.py` | 四个契约 + `ToolCall`/`AgentStep`/`AgentStatus` 均已定义并被实际使用 |
| 4 | 封装 Tutor / Quiz / Evaluator / Planner Agent | 进行中 | `app/agents/learning_agents.py` | `tests/unit/test_orchestrator.py` | Tutor/Quiz/Catalog/Progress/Planner/General/Clarify 七个适配器；**Evaluator 尚未封装**，批改仍走独立 Attempt API |
| 5 | 串行工作流 `Tutor→Quiz`、`Evaluator→Planner` | 进行中 | `app/agents/orchestrator.py` | HTTP 端到端已验证 `tutor→quiz` | `Tutor→Quiz` 已跑通；`Evaluator→Planner` 未做，Planner 仍只读取计划不会生成 |
| 6 | `TeachingToolManager` | 未开始 | — | — | 8 个教学工具，统一做用户/课程/范围校验 |
| 7 | Redis 短期学习状态 | 未开始 | `app/infrastructure/` | — | Redis 当前在 compose 中已启动但主链路未使用 |
| 8 | 教学 Skills + 学术诚信 Guard | 未开始 | `skills/`（仍为旧客服 Skill） | 待建 Guard 评测集 | PRD 8.7 整块空白，四级判定未实现 |
| 9 | Router / Orchestrator / 端到端评测 | 进行中 | `tests/evals/run_router_eval.py`、`router_metrics.py` | `baselines/router_v1.json` | Router v1 已完成；Orchestrator 的四项要求由 8 个单元测试覆盖，**尚无版本化评测集**；端到端闭环评测未开始 |
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
| K-8 | 路由已能输出 `supporting_agents` 与 `execution_mode=sequential`，但 `TutorService` 只执行 primary agent，串行工作流被识别却未执行 | 高 | **已修复**（Orchestrator 落地，`tutor→quiz` 端到端跑通） |
| K-9 | 复合意图的辅助 Agent 识别准确率仅 57.1%（4/7），模型常漏报 `supporting_agents` | 中 | 未修复 |
| K-10 | 澄清判定准确率 88.9%：`rt-ambig-004`「再来一点」被判为可执行意图而非请求澄清 | 低 | 未修复 |
| K-11 | 串行工作流中若引用校验失败，`_extractive_answer` 会整体替换答案，导致 Quiz 的提示文案丢失（练习集本身仍在 `practice_set` 字段中正常返回） | 低 | 未修复 |
| K-12 | `EvaluatorAgent` 尚未封装，批改仍只能走独立的 Attempt API，无法进入编排流程，因此 `Evaluator→Planner` 工作流暂时做不了 | 中 | 未修复 |

---

## 4. 变更日志

> **格式约定**：最新的写在最上面。每次收工追加一条，五个字段一个都不能少。
> `commit` 填实际 hash；若尚未提交填 `未提交`。

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：完成路线图第 2 步（Orchestrator）和第 3 步（统一 Agent 协议），第 4 步封装了 7 个 Agent 中的 6 类（Evaluator 除外，见 K-12），并跑通第 5 步的第一个串行工作流 `Tutor→Quiz`。
  1. 新增 `app/agents/protocol.py`，定义路线图 4.3 要求的四个契约：`AgentTask`、`LearningContext`、`AgentResult`、`AgentTrace`，并补充 `ToolCall`、`AgentStep`、`AgentStatus` 和 `LearningAgent` Protocol。
  2. 新增 `app/agents/presenters.py`，把 9 个纯展示/配置函数从 `TutorService` 抽出，使 Agent 层不必反向依赖 Service，避免循环导入。
  3. 新增 `app/agents/learning_agents.py`，七个 Agent 全部是现有 Service 的**薄适配器**（Tutor/Quiz/Catalog/Progress/Planner/General/Clarify），检索、生成、出题逻辑一行未改。
  4. 新增 `app/agents/orchestrator.py`：按 `execution_mode` 分派，串行时把主 Agent 的产出经 `shared` 传给辅助 Agent，辅助 Agent 缺少依赖则跳过、抛异常则降级，全过程写入 `AgentTrace`。
  5. `TutorService.answer()` 的 6 分支 `if/elif` 派发（约 60 行）替换为构造 `LearningContext` + `orchestrator.run()`；`TutorMessageRead` 新增 `trace` 字段。
- **为什么**：路线图第 6 节第 2–4 项，实现依据为 4.2 与 4.3 节。第 2、3、4 步合并做是因为三者互为前提：没有统一协议就无法定义 Agent 接口，没有 Agent 就没有东西可编排。**直接动机是解决 K-8** —— 上一轮路由已能正确识别串行工作流，但没有任何组件会去执行它。
- **改了哪些文件**：
  - 新增：`app/agents/protocol.py`、`app/agents/presenters.py`、`app/agents/learning_agents.py`、`app/agents/orchestrator.py`、`tests/unit/test_orchestrator.py`
  - 修改：`app/services/tutor_service.py`（派发逻辑替换为编排调用，9 个函数迁出）、`app/schemas/tutor.py`（新增 `trace` 字段）、`tests/unit/test_tutor.py`（改从 `presenters` 导入迁移后的函数）
- **怎么验证的**：
  - 单元测试 `110 passed`（改动前 102，新增 8 个 Orchestrator 测试，覆盖路线图第 9 节对编排层的四项要求：Agent 选择、执行顺序、上下文传递、失败降级）。
  - Router 规则层基线**逐位复现**（意图准确率 70.0%、规则解决率 55.6%、范围保持 100%），符合 `baselines/router_v1.json` 中的回归门槛，确认路由层未被本次重构影响。
  - HTTP 端到端验证 **K-8 已修复**：「先讲解一下残差，然后给我出3道选择题」实际执行 `agent_sequence: ['tutor', 'quiz']`，主 Agent 8.0s（检索 8 个片段 + 生成），辅助 Agent 16.1s（真实创建 3 道题），总计 24.1s，`practice_set` 正常返回「残差的定义和解释练习」。
  - 单 Agent 路径回归验证：目录查询 7ms、进度查询 20ms、问候 0ms，`agent_sequence` 分别为 `['catalog']`、`['progress']`、`['general']`，均未产生多余的 Agent 调用。
- **下一步建议**：优先做 **K-12**（封装 `EvaluatorAgent`），它是 `Evaluator→Planner` 工作流的前置条件，也是路线图第 5 步剩下的一半。同时 Planner 目前只会读取计划、不会生成，需要补上真正的计划生成能力（路线图 4.2 明确点名了这一点）。另外第 9 步的 Orchestrator 版本化评测集仍然缺失 —— 当前只有单元测试，没有像 Router v1 那样可比较、可记录基线的评测。

---

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
