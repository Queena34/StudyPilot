# StudyPilot 开发进度台账

> **这是项目进度的唯一事实来源。** 任何 AI Agent（Claude Code / Codex / 其他）或人类开发者在开始工作前必须先读本文件，收工前必须更新本文件。
>
> 协作规则见 [`AGENTS.md`](../AGENTS.md)。
> 目标架构与阶段计划见 [`ECHOMIND_ARCHITECTURE_MIGRATION.md`](./ECHOMIND_ARCHITECTURE_MIGRATION.md)。
> PRD 功能差距见 [`IMPLEMENTATION_AUDIT.md`](./IMPLEMENTATION_AUDIT.md)。

| 字段 | 内容 |
|---|---|
| 台账建立日期 | 2026-08-26 |
| 当前基线 commit | `b60bfa1` |
| 当前阶段 | 路线图第 1–6、8、11 步已完成；剩 7（Redis）、9（评测集）、10（监控）、12（前端） |
| 参与过的执行者 | Codex（`5a2ac0a` → `47638f7`）、Claude Code（`b54cb51` 起） |

---

## 1. 路线图状态

对应 `ECHOMIND_ARCHITECTURE_MIGRATION.md` 第 6 节「推荐执行顺序」。

状态取值：`未开始` / `进行中` / `已完成` / `已阻塞`。

| # | 阶段 | 状态 | 关键文件 | 验证方式 | 备注 |
|---|---|---|---|---|---|
| 1 | 混合 `LearningIntentRouter` | 已完成 | `app/agents/routing.py`、`intent_router.py`、`llm_router.py` | `tests/evals/run_router_eval.py`（v2 共 57 例，混合模式意图准确率 90.4%） | 规则优先 + 低置信度 LLM 兜底 + 澄清；范围保持 100% |
| 2 | `LearningAgentOrchestrator` | 已完成 | `app/agents/orchestrator.py` | `tests/unit/test_orchestrator.py`（8 例） | 按 `execution_mode` 分派、传递上下文、失败降级、全程 Trace |
| 3 | 统一 Agent 协议（`AgentTask`/`LearningContext`/`AgentResult`/`AgentTrace`） | 已完成 | `app/agents/protocol.py`、`routing.py` | `tests/unit/test_orchestrator.py` | 四个契约 + `ToolCall`/`AgentStep`/`AgentStatus` 均已定义并被实际使用 |
| 4 | 封装 Tutor / Quiz / Evaluator / Planner Agent | 已完成 | `app/agents/learning_agents.py` | `tests/unit/test_evaluator_planner_agents.py`（16 例） | 八个适配器：Tutor/Quiz/Evaluator/Planner/Catalog/Progress/General/Clarify |
| 5 | 串行工作流 `Tutor→Quiz`、`Evaluator→Planner` | 已完成 | `app/agents/orchestrator.py` | HTTP 端到端均已验证 | 两个工作流都跑通；Planner 已具备真正的计划生成能力 |
| 6 | `TeachingToolManager` | 已完成 | `app/agents/tools.py` | `tests/unit/test_teaching_tools.py`（9 例） | 9 个教学工具；课程归属与资料范围统一校验，越权返回 403；调用结果、耗时、失败原因统一记录 |
| 7 | Redis 短期学习状态 | 未开始 | `app/infrastructure/` | — | Redis 当前在 compose 中已启动但主链路未使用 |
| 8 | 教学 Skills + 学术诚信 Guard | 已完成 | `app/agents/integrity.py`、`app/agents/skills.py`、`skills/*/SKILL.md` | `tests/unit/test_integrity_and_skills.py`（24 例） | 四级 Guard 已接入编排层；7 个教学 Skill 替换旧客服 Skill |
| 9 | Router / Orchestrator / 端到端评测 | 进行中 | `tests/evals/run_router_eval.py`、`router_metrics.py` | `baselines/router_v2.json` | Router v2（57 例）已完成；编排层、工具层与 Guard 由 57 个单元测试覆盖但**仍无版本化评测集** |
| 10 | 链路、成本与降级监控 | 未开始 | `monitor/`、`config/prometheus.yml` | — | Prometheus 已配置，业务指标未接入 |
| 11 | 清理旧 EchoMind 客服代码 | 已完成 | 已删除全部旧目录；`README.md`、`MIGRATION.md` 已重写 | 159 测试通过 + 应用冒烟 + 评测基线复现 | 约 4100 行 Python、3 个部署脚本、1 个旧 env 模板已移除 |
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
| K-5 | `README.md` 约一半篇幅仍是 EchoMind 客服系统指南，损害仓库可信度 | 中 | **已修复**（1438 行重写为 131 行 StudyPilot 文档） |
| K-6 | Redis 未承担设计中的缓存与任务队列职责 | 中 | 未修复 |
| K-7 | 无流式输出；无跨 Agent trace ID | 中 | 未修复 |
| K-8 | 路由已能输出 `supporting_agents` 与 `execution_mode=sequential`，但 `TutorService` 只执行 primary agent，串行工作流被识别却未执行 | 高 | **已修复**（Orchestrator 落地，`tutor→quiz` 端到端跑通） |
| K-9 | 复合意图的辅助 Agent 识别准确率仅 57.1%（4/7），模型常漏报 `supporting_agents` | 中 | 未修复 |
| K-10 | 澄清判定准确率 88.9%：`rt-ambig-004`「再来一点」被判为可执行意图而非请求澄清 | 低 | 未修复 |
| K-11 | 串行工作流中若引用校验失败，`_extractive_answer` 会整体替换答案，导致 Quiz 的提示文案丢失（练习集本身仍在 `practice_set` 字段中正常返回） | 低 | 未修复 |
| K-12 | `EvaluatorAgent` 尚未封装，批改仍只能走独立的 Attempt API，无法进入编排流程，因此 `Evaluator→Planner` 工作流暂时做不了 | 中 | **已修复** |
| K-16 | 旧入口 `api/main.py` 仍会读取 `skills/` 目录，第 8 步替换后它会把教学 Skill 注入客服 Agent | 低 | **已修复**（第 11 步删除该文件） |
| K-15 | Agent 通过工具层调用大模型网关（Tutor 生成回答）时不算工具调用，因此 `AgentTrace` 里不再出现 `generate_tutor_answer` 记录；模型名与降级原因仍在 `AgentStep` 上可见 | 低 | 未修复 |
| K-13 | 高置信度显式规则（如答案提交 0.96）会直接返回、跳过复合意图检测，导致 `rt-comp-008`「我的答案是…帮我改一下并安排后续复习」的 planner 辅助 Agent 被漏掉 | 中 | 未修复 |
| K-14 | `_practice_configuration` 的主题抽取会把「关于残差的简答题」整体当成主题，导致题目支持性判断失败并返回 `INSUFFICIENT_EVIDENCE`（既有问题，非本轮引入） | 中 | 未修复 |

---

## 4. 变更日志

> **格式约定**：最新的写在最上面。每次收工追加一条，五个字段一个都不能少。
> `commit` 填实际 hash；若尚未提交填 `未提交`。

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：完成路线图第 11 步，移除全部 EchoMind 客服遗留。
  1. 删除 7 个顶层目录共约 4100 行 Python：`core/`（意图识别、LLM 工具、Skill 加载器）、`agents/`（客服编排）、`mcp/`（工具管理器、客服知识库）、`memory/`（Redis 对话记忆）、`monitor/`（客服性能监控）、`evaluation/`（客服端到端评测）、`api/main.py`（旧 EchoMind 入口）。
  2. 删除 EchoMind 时代的部署脚本 `docker-deploy.sh`、`run-image.sh`、`build-image.sh` 和旧环境变量模板 `.env.example.env`。
  3. `README.md` 从 1438 行重写为 131 行：快速开始、能力清单、架构图与关键约束、项目结构、测试与评测、开发状态。原本约 1390 行的客服系统指南全部移除。
  4. `MIGRATION.md` 重写，记录设计思想的实际去向和本次清理的具体内容。
  5. 同步更新指向已删文件的文档：`skills/README.md`、`docs/ECHOMIND_ARCHITECTURE_MIGRATION.md`、`docs/TECHNICAL_DESIGN.md`（历史对照表加注说明）、`AGENTS.md`、`CLAUDE.md`（约束从"不要接入"改为"不要从 Git 历史恢复"）。
- **为什么**：路线图第 6 节第 11 项。这些目录从项目建立起就未接入 `app/` 主链路，但任何人打开仓库第一眼看到的仍是一个客服系统，直接损害项目可信度（K-5）。同时旧入口 `api/main.py` 在第 8 步替换 Skill 后会把教学 Skill 注入客服 Agent（K-16）。
- **改了哪些文件**：
  - 删除：`core/`、`agents/`、`mcp/`、`memory/`、`monitor/`、`evaluation/`、`api/`、`docker-deploy.sh`、`run-image.sh`、`build-image.sh`、`.env.example.env`
  - 重写：`README.md`、`MIGRATION.md`
  - 修改：`skills/README.md`、`docs/ECHOMIND_ARCHITECTURE_MIGRATION.md`、`docs/TECHNICAL_DESIGN.md`、`AGENTS.md`、`CLAUDE.md`
- **怎么验证的**：
  - **删除前**确认三点：`app/` 与 `tests/` 对这些模块**零引用**（grep 导入语句无结果）；`docker-compose.yml`、`Dockerfile`、`.dockerignore` **不引用**被删的脚本；`run-image.sh` 操作的是 `echomind` / `echomind-app` 这组根本不存在的容器（当前运行的是 `studypilot-*`）。
  - 删除后重建镜像，单元测试 `159 passed`，`/health/ready` 返回 `postgresql: up`，目录查询走完整链路正常。
  - Router 基线复现（v2 意图准确率 73.1%、范围保持 100%）。
  - 全仓库客服语义检查：`README.md` 中仅剩说明项目由来的一句；`docs/TECHNICAL_DESIGN.md` 的历史对照表已加注说明为何保留。
- **下一步建议**：补 `integrity-v1` 评测集（第 8 步遗留），Guard 是安全相关判定且误判代价不对称，目前只有单元测试。之后建议第 12 步前端学习闭环 —— 后端能力已远超前端可操作范围，练习历史、错题重练、学习趋势和用户设置都还没有界面。

---

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：完成路线图第 8 步，学术诚信 Guard 与教学 Skills。
  1. 新增 `app/agents/integrity.py`，实现 PRD 8.7 要求的四级判定：`LEARNING_ALLOWED`、`HINT_ONLY`、`SUBMISSION_RISK`、`LIVE_EXAM_PROHIBITED`。判定完全确定性 —— 决定学生能得到何种帮助的规则必须可检查、可测试，不能每次运行结果不同。
  2. Guard 在任何 Agent 之前运行。只有实时考试会短路整轮（由 `IntegrityGuardAgent` 单独作答），另外三档**仍然给出完整帮助**，只是改变帮助的形式：`HINT_ONLY` 讲方法不给答案，`SUBMISSION_RISK` 给结构、检查清单和复核邀请。
  3. 约束通过 `answer_constraint` 注入讲解网关的 system prompt，排在学生措辞之上；简短提示按 PRD 要求以引用块形式前置，不替代帮助本身。
  4. 删除三个旧客服 Skill，新增 7 个教学 Skill：苏格拉底式引导、分层概念讲解、数学公式讲解、考试复习策略、选择题生成规范、rubric 批改规范、中英双语术语解释。
  5. 新增 `app/agents/skills.py` 作为 StudyPilot 自己的加载器（旧 `core/skill_loader.py` 按规约不接入），按 Agent 与关键词选择，每轮最多注入 2 个以免稀释 prompt。
- **为什么**：路线图第 6 节第 8 项。学术诚信是 PRD 中**唯一整块空白**的模块（8.7），也是审计文档里唯一标注「未实现」的功能。路线图同时要求清理旧客服 Skills。
- **改了哪些文件**：
  - 新增：`app/agents/integrity.py`、`app/agents/skills.py`、`tests/unit/test_integrity_and_skills.py`、`skills/{socratic_guidance,layered_explanation,mathematical_notation,exam_revision,question_authoring,rubric_grading,bilingual_terminology}/SKILL.md`
  - 删除：`skills/{general_customer_service,technical_support,billing_support}/SKILL.md`
  - 修改：`app/agents/orchestrator.py`（Guard 前置与受限时的回退）、`app/agents/learning_agents.py`（Tutor 接收约束与 Skill）、`app/agents/presenters.py`、`app/agents/protocol.py`、`app/agents/intent_router.py`（修正误判）、`app/llm/gateway.py`、`app/services/tutor_service.py`、`app/schemas/tutor.py`（新增 `integrity` 字段）、`skills/README.md`
- **怎么验证的**：
  - 单元测试 `159 passed`（改动前 135，新增 24）。
  - 四档端到端逐一验证：`解释残差` → `learning_allowed`/tutor 正常讲解；`这道作业题直接给我答案` → `hint_only`/tutor 讲方法并明确不给答案；`帮我写一篇课程论文` → `submission_risk`/tutor 给出写作框架、必备要素清单和引用；`我正在考试…` → `live_exam_prohibited`，短路为拒绝加课后帮助邀请。
  - Router 两套基线均逐位复现（v2: 73.1%/63.2%，v1: 70.0%/55.6%，范围保持 100%），确认收紧后的答案提交正则未改变任何既有用例。
  - Skill 选择验证：五种典型请求分别命中对应 Agent 的正确 Skill，且 quiz 的命题规范不会被注入 tutor。
  - **端到端验证抓到两个真 bug**：
    - `_is_answer_submission` 的 `我答` 会命中「给**我答**案」，导致索要作业答案被误判为交卷。已收紧为要求 `我答`/`我选` 出现在句首或标点后且其后有内容。
    - `帮我写一篇课程论文` 原本被路由到 `general`，只回了功能介绍 —— 违反 PRD 8.7「提示应简短，并继续提供合适的学习帮助」。现在诚信约束生效且路由非显式规则决定时，一律回退到课程讲解。
- **下一步建议**：第 8 步的 Guard 目前只有单元测试，**没有版本化评测集**。考虑到它是安全相关判定，误判代价不对称（把正常提问判成作弊比漏判更伤用户），建议优先补 `integrity-v1` 评测集，重点覆盖假阳性。之后再做第 7 步 Redis 或第 11 步清理旧客服代码。

---

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：完成路线图第 6 步 `TeachingToolManager`。
  1. 新增 `app/agents/tools.py`，提供 9 个教学工具：`search_course_material`、`list_course_documents`、`get_learning_progress`、`get_recent_learning_context`、`list_study_plans`、`create_study_plan`、`create_practice_set`、`find_pending_question`、`grade_answer`（`update_topic_mastery` 由 `AttemptService` 在批改内部完成，未单独暴露）。
  2. 统一权限与范围校验：`authorize()` 确认课程归属调用者，`assert_documents_in_course()` 确认请求的资料确实属于该课程，越权抛 `ToolPermissionError`（HTTP 403）。两项检查结果按 manager 缓存，避免重复查询。
  3. 统一调用记录：`ToolSession._invoke()` 包裹每次调用，成功与失败都写入 `ToolCall`（名称、成败、耗时、失败原因），失败后再抛出。每个 Agent 步骤持有独立 session，互不污染。
  4. 七个 Agent 全部改为只经工具层访问数据，**不再持有任何 Repository 或 Service**。`TutorAgent` 只保留 LLM 网关，`QuizAgent`/`CatalogAgent`/`ProgressAgent`/`PlannerAgent`/`EvaluatorAgent` 构造函数已无参数。
- **为什么**：路线图第 6 节第 6 项，实现依据为 4.4 节。上一轮虽然已有 `AgentTrace.tool_calls`，但记录由各 Agent 手写、**没有任何统一的权限与范围校验层** —— 这正是本步要补的缺口。路线图第 5 节也明确要求「结构化数据库查询和文档检索必须通过受控工具完成」。
- **改了哪些文件**：
  - 新增：`app/agents/tools.py`、`tests/unit/test_teaching_tools.py`
  - 修改：`app/agents/learning_agents.py`（七个 Agent 改为经工具层访问）、`app/agents/protocol.py`（`LearningContext` 新增 `tools`）、`app/services/tutor_service.py`（构造并注入 `TeachingToolManager`）、`tests/unit/test_tutor.py`、`tests/unit/test_evaluator_planner_agents.py`（改为经工具层构造）
- **怎么验证的**：
  - 单元测试 `135 passed`（改动前 126，新增 9 个工具层测试，覆盖越权拒绝、授权缓存、成功/失败记录、session 隔离、未配置工具的拒绝）。
  - **越权拦截端到端验证**：携带不属于该课程的 `document_ids` 请求，返回 `HTTP 403 TOOL_SCOPE_DENIED`，且单元测试确认检索器在校验失败后**根本没有被调用**。
  - Router 两套基线均逐位复现：v2 rules-only 意图准确率 73.1%、规则解决率 63.2%；v1 历史基线 70.0%、55.6%；范围保持均为 100%。
  - 端到端回归：目录查询 `list_course_documents (2 documents)`、概念讲解 `search_course_material (8 chunks)`、`Evaluator→Planner` 串行工作流的三次工具调用全部正常记录。
- **下一步建议**：路线图第 7 步 Redis 短期学习状态。当前每轮对话都要从 PostgreSQL 重建上下文，当前课程、资料范围、最近讲解主题和待批改练习集都没有短期缓存。另外第 9 步的 Orchestrator/端到端版本化评测集仍然缺失，是目前唯一一处「有实现但无可比较基线」的地方。

---

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：完成路线图第 4 步和第 5 步，两个跨 Agent 串行工作流全部跑通。
  1. 新增 `EvaluatorAgent`，包装 `AttemptService`。题目由新增的 `PracticeRepository.latest_pending_question()` 从最新练习集中定位，学习者无需报题号即可在对话里直接作答。
  2. `PlannerAgent` 补上真正的计划生成能力。`StudyPlanService.create` 本就会按掌握度排序主题，因此这里只是接上调用，没有重复实现排程逻辑；`_requests_new_plan()` 区分「制定计划」与「查看计划」。
  3. 新增 `RouteTarget.EVALUATE` 与 `_is_answer_submission()` 规则，只匹配显式交卷表达，避免把普通提问误判为交卷。
  4. Orchestrator 增加 `_SUPPORTING_CREATES`，使 Planner 作为辅助 Agent 时执行「生成」而非「读取」。
  5. Router 评测扩展为 v2（57 例），新增 6 条答案提交、2 条误判防护、2 条 `Evaluator→Planner` 复合、2 条计划生成用例。
- **为什么**：路线图第 6 节第 4、5 项。直接动机是 **K-12** —— Evaluator 未封装导致 `Evaluator→Planner` 无法实现，而路线图第 7 节验收标准要求「至少两个跨 Agent 串行工作流可以端到端运行」。
- **改了哪些文件**：
  - 新增：`tests/unit/test_evaluator_planner_agents.py`、`tests/evals/datasets/router_intents_v2.jsonl`、`tests/evals/baselines/router_v2.json`
  - 修改：`app/agents/learning_agents.py`（新增 Evaluator、重写 Planner）、`app/agents/presenters.py`（新增 6 个展示/解析函数）、`app/agents/orchestrator.py`、`app/agents/routing.py`、`app/agents/intent_router.py`、`app/infrastructure/repositories/practice_repository.py`、`app/api/v1/routes/tutor.py`、`app/services/tutor_service.py`、`tests/evals/run_router_eval.py`（新增 `--dataset-version`）、`tests/evals/README.md`
- **怎么验证的**：
  - 单元测试 `126 passed`（改动前 110，新增 16）。
  - **v1 历史基线逐位复现**（意图准确率 70.0%、规则解决率 55.6%、范围保持 100%），证明新增的答案提交规则没有在既有 45 条用例上产生误判。
  - Router v2 基线：rules-only 意图准确率 73.1%、规则解决率 63.2%；hybrid 意图准确率 **90.4%**、执行模式准确率 94.7%、复合辅助 Agent 准确率 **66.7%**（v1 为 57.1%）、范围保持 **100%**。
  - HTTP 端到端验证 `Evaluator→Planner`：「我选 B。批改完之后，请根据我的薄弱点制定一份7天复习计划」实际执行 `agent_sequence: ['evaluator', 'planner']`，批改产出得分与逐项反馈，随后依据薄弱主题生成 10 项任务的 5 天计划。
  - 优雅降级验证：待批改题为选择题而学习者提交了文字答案时，返回「请回复选项编号（A、B、C、D）」而非 422 错误。
  - 单元测试抓到一个真 bug：`我的答案是：X` 的框架剥离正则会残留冒号，会把 `：` 一起送去批改，已修复。
  - 薄弱主题传递修正：原先把 `knowledge_errors`（错误描述）当成薄弱主题，导致计划显示「重点针对：选择了不受课程资料支持的选项」，改为优先取 `recommended_topics`。
- **下一步建议**：路线图第 6 步 `TeachingToolManager`。当前 Agent 直接持有 Repository 和 Service，工具调用虽已记录在 `AgentTrace.tool_calls` 中，但**没有统一的权限与范围校验层**，这正是第 6 步要解决的。另可优先处理 **K-13**（高置信度规则跳过复合检测）——它现在是复合辅助 Agent 准确率上不去的主要原因之一。

---

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
