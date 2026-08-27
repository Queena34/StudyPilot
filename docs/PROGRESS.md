# StudyPilot 开发进度台账

> **这是项目进度的唯一事实来源。** 任何 AI Agent（Claude Code / Codex / 其他）或人类开发者在开始工作前必须先读本文件，收工前必须更新本文件。
>
> 协作规则见 [`AGENTS.md`](../AGENTS.md)。
> 当前实现见 [`ARCHITECTURE.md`](./ARCHITECTURE.md)。
> 目标架构与阶段计划见 [`ECHOMIND_ARCHITECTURE_MIGRATION.md`](./ECHOMIND_ARCHITECTURE_MIGRATION.md)。
> PRD 功能差距见 [`IMPLEMENTATION_AUDIT.md`](./IMPLEMENTATION_AUDIT.md)。

| 字段 | 内容 |
|---|---|
| 台账建立日期 | 2026-08-26 |
| 当前基线 commit | `b0b6255` |
| 当前阶段 | 路线图第 1–6、8、9、11、12 步全部完成；剩 7（Redis）、10（监控） |
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
| 8 | 教学 Skills + 学术诚信 Guard | 已完成 | `app/agents/integrity.py`、`app/agents/skills.py`、`skills/*/SKILL.md` | `tests/evals/run_integrity_eval.py`（61 例，假阳性率 0%）+ 32 个单元测试 | 四级 Guard 已接入编排层；7 个教学 Skill 替换旧客服 Skill |
| 9 | Router / Orchestrator / 端到端评测 | 已完成 | `run_router_eval.py`、`run_integrity_eval.py`、`run_orchestrator_eval.py`、`run_loop_eval.py`、`run_grading_eval.py` | 七套版本化基线全部记录 | Router v2（57）、Integrity v1（61）、Orchestrator v1（30）、Loop v1（5 阶段）、Grading v1（90 次） |
| 10 | 链路、成本与降级监控 | 未开始 | `monitor/`、`config/prometheus.yml` | — | Prometheus 已配置，业务指标未接入 |
| 11 | 清理旧 EchoMind 客服代码 | 已完成 | 已删除全部旧目录；`README.md`、`MIGRATION.md` 已重写 | 159 测试通过 + 应用冒烟 + 评测基线复现 | 约 4100 行 Python、3 个部署脚本、1 个旧 env 模板已移除 |
| 12 | 补齐前端学习闭环 | 已完成 | `app/web/`、`app/api/v1/routes/{practice,documents,preferences,progress}.py` | `tests/unit/test_web.py`、`test_practice_history.py`、`test_preferences.py`（33 例） | 练习历史/错题重练/rubric 与来源、历史对话、课程与资料增删改、学习趋势与常见错误、用户偏好设置、单个薄弱点删除 |

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
| K-1 | PDF 页数统计存在异常样本，需单独校验 Parser 并对真实资料做页码/引用抽检 | 高 | **非缺陷**（PDF 实际就是 104/69 页，文件名的「6page」指每页 6 张幻灯片；23 条引用页码抽检 100% 命中） |
| K-2 | 引用校验失败时无修复重试；「未配置密钥」「Provider 失败」「引用校验失败」三种情形未区分暴露 | 高 | 未修复 |
| K-3 | 学术诚信 Guard 完全未实现（PRD 8.7） | 高 | **已修复**（第 8 步四级 Guard 落地，Integrity v1 评测 61 例全通过） |
| K-4 | Grading v1 仅冒烟通过，缺 90 次完整基线与人工忠实度报告 | 中 | **已修复**（90 次基线已记录；人工忠实度报告仍缺，另记为 K-18） |
| K-17 | 批改器偏保守：对答案已明确表述但措辞简短的 rubric 条目只给 0.5，导致 partial 答案绝对分数偏低。三个样本不足以支撑放宽评分标准，需更多样本 | 中 | 未修复 |
| K-18 | Grading v1 数据集的 partial 答案含"但我没有说明…"这类元评论，是真实学生不会写的人为杂质，会压低已覆盖条目的得分。应在 grading-v2 中移除 | 低 | 未修复 |
| K-20 | 讲解语言偏好原本不可靠：学生用中文提问但要求英文回答时，模型跟随提问语言而非设定 | 中 | **已修复**（语言指令改为显式压过提问语言） |
| K-19 | 全部评测集仍缺人工忠实度抽检，当前指标都是可自动判定的代理指标 | 中 | **已完成**（Queena 评审 12 条，全项满分；样本量局限已在基线中注明） |
| K-22 | Citation 的 `snippet` 只有 300 字符 | 中 | **已修复**（上限 3200；分块降到 1200 后引用恒为完整片段） |
| K-21 | 不指定资料时，「根据资料第一章…」这类问题会跨两份资料检索并返回「证据不足」 | 中 | **已修复**（章节进入 QueryPlan；章节过滤不再要求指定资料；「资料第一章」不再被误读为「第 1 份资料」） |
| K-5 | `README.md` 约一半篇幅仍是 EchoMind 客服系统指南，损害仓库可信度 | 中 | **已修复**（1438 行重写为 131 行 StudyPilot 文档） |
| K-23 | 聊天生成的练习沿用对话的讲解语言，导致中文提问时出英文考试的学生拿到中文题目 | 中 | **已修复**（新增独立的出题语言，可在偏好中设默认、在两处界面临时覆盖） |
| K-24 | 选择题渲染了单选按钮，但它们在表单之外、从不被读取，学习者必须另外手动输入字母才能提交 | 高 | **已修复**（选项即答案，文本框已移除） |
| K-25 | 章节识别的宽松规则会把「2 Pints」这类以数字开头的幻灯片标题误判为「第 2 章」 | 低 | 未修复 |
| K-26 | 当指定资料确实没有所问章节时，只回「证据不足」，未说明是该资料没有这一章 | 低 | 未修复 |
| K-27 | **跨语言检索失效** | 高 | **已修复**（英文检索模型 + 查询翻译；跨语言持平率由 0 升至 100%） |
| K-28 | **引用校验只查编号不查支撑** | 高 | **已缓解**（检索接地后 `ungrounded_claim_rate` 为 0；校验逻辑本身仍只查编号，见 K-2） |
| K-29 | 八套评测都没能抓住 K-27/K-28 | 高 | **已修复**（新增 Cross-lingual v1，关键词对着被引片段而非答案校验） |
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
| K-14 | `_practice_configuration` 的主题抽取会把「关于残差的简答题」整体当成主题，导致题目支持性判断失败并返回 `INSUFFICIENT_EVIDENCE` | 中 | **已修复**（剥离题型/题量等请求措辞，只保留学科主题） |

---

## 4. 变更日志

> **格式约定**：最新的写在最上面。每次收工追加一条，五个字段一个都不能少。
> `commit` 填实际 hash；若尚未提交填 `未提交`。

### 2026-08-27 · Claude Code · commit `未提交`

- **做了什么**：修复两个用户实际使用中发现的问题。第二个的第一版实现方式被用户否决，已按正确架构重做。
  1. **K-24 选择题交互**：选项的单选按钮渲染在 `<form>` **外面**，提交时读的是那个文本框 —— 也就是说勾选完全无效，学习者必须再手输一次字母。改为选项即答案：单选按钮进入表单、移除文本框、提交读取选中项，未作答时给出提示。历史回顾视图共用同一个表单构造函数。
  2. **K-21 / 章节范围**：「根据第一章出练习题」出的题超出第一章。
- **第一版做错了，已回滚**：我最初直接在 `app/agents/presenters.py` 里加正则去刮 `context.message` 提取章节。**用户指出这绕过了整个路由层** —— 项目专门建了混合意图路由把消息解析成结构化 `QueryPlan`，而我的做法会让章节解析散落到第三处（检索器里已有一份），既重复又无法被 Router 评测覆盖。这个反馈是对的，已回滚重做。
- **正确的实现**：章节是一个**范围维度**，与 `page_from`/`document_ids` 并列。
  1. `TutorScope` 与 `QueryPlan` 新增 `chapter` 字段。
  2. 章节**只在路由层解析一次**（`_resolve_chapter`，复用检索器自己的 `_chapter_number`，两边不可能对"第一章"产生分歧）；学习者显式选择的章节永远优先于消息解析。
  3. `CourseRetriever.retrieve()` 接收显式 `chapter` 参数，**不再从查询字符串里嗅探**。
  4. `TutorAgent` 传 `plan.chapter`；`QuizAgent` 把 `plan.chapter` 并入 scope 后交给出题，不再重读消息。
  5. 章节过滤不再要求 `document_ids` 非空 —— where 过滤本就限定在该学习者的这门课内，忽略已命名的章节等于悄悄用课程全部内容作答。
- **顺带修好的根因**：`_mentions_document_reference` 的正则把「资料第一**章**」读成了「资料第一」= 第 1 份资料，于是范围被错误地锁到一份不含该章的资料上。已加否定前瞻：数字后跟「章/节/页」时不算资料序号。
- **怎么验证的**：
  - 单元测试 `241 passed`（改动前 224，新增 17）。
  - 端到端：「根据第一章内容出3道练习题」三道题的来源**全部**为 `Chapter 1. The Simple Regression`（此前不受限）；不提章节时 `chapter=None`、不受限。
  - 「根据资料第一章，最小二乘法的目标是什么？」由 `insufficient/0 引用` 变为 `sufficient/2 引用`，且引用全部来自第一章。
  - 指代判断抽查 7 例全部正确（「资料第一章」不指代资料，「资料1」「第二份资料」「notes.pdf」指代资料）。
  - 全部评测回归：Router v2 73.1%/范围保持 100%、Integrity 100%、Orchestrator 100%、端到端 `loop_closed: true`。
- **确认为正确行为、未改动**：「资料1的第一章」返回证据不足 —— ANOVA 那份资料确实没有第一章标记，如实告知比强行作答诚实。另记 K-26（可提示得更具体）。
- **新记录 K-25**：章节识别的宽松规则把「2 Pints」这类以数字开头的幻灯片标题误判为「第 2 章」。
- **下一步建议**：扩大忠实度样本量、K-17（批改保守）、K-2（引用校验失败无重试）。路线图只剩第 7 步 Redis 与第 10 步监控。

---

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：清理三个用户可见的问题，并修复出题语言。
  1. **K-1 判定为非缺陷**：PDF 实际就是 104 页和 69 页，文件名里的「6page」指每页 6 张幻灯片的讲义版式。进一步用 PyMuPDF 抽检 23 条引用的页码，**100% 命中目标页**。审计中「页数统计异常」的判断来自文件名，不是数据。
  2. **K-22 已修复**：Citation 的 `snippet` 上限由 300 提到 3200（分块上限），引用现在携带模型实际看到的完整片段。人工评审第一轮的教训正是 300 字符不足以核实一条论断 —— 学习者在 Web 端面对的是同一个问题。
  3. **K-14 已修复**：主题抽取新增 `_clean_topic()`，剥离「的简答题」「3道选择题」`short-answer questions` 等请求措辞。此前「给我出1道关于残差的简答题」会把「残差的简答题」当主题、支持性判断失败并返回 `INSUFFICIENT_EVIDENCE`；现在正常出题。
  4. **K-23 出题语言（用户提出）**：聊天生成的练习此前沿用对话的**讲解语言**，导致用中文提问的学生拿到中文题目 —— 但目标是英文考试。新增 `TutorPracticeOptions.language`，出题语言与讲解语言分离：偏好中可设默认（`answer_language`），聊天练习设置和练习页各有一个下拉可临时覆盖。
- **为什么**：这四项都是学习者直接可见的问题，其中 K-22 和 K-23 由用户在实际使用中提出。
- **改了哪些文件**：
  - 新增：`tests/unit/test_practice_topic_and_language.py`
  - 修改：`app/agents/presenters.py`（`_clean_topic`、练习语言、`CITATION_SNIPPET_LIMIT`）、`app/schemas/tutor.py`、`app/services/tutor_service.py`、`app/services/practice_service.py`、`app/web/index.html`、`app/web/static/app.js`、`tests/unit/test_web.py`、`docs/PROGRESS.md`
- **怎么验证的**：
  - 单元测试 `224 passed`（改动前 209，新增 15）。
  - K-1：`fitz` 直读两份 PDF 得 104/69 页且每页都有文字；23 条引用页码抽检全部命中。
  - K-22：同一问题的引用片段长度由 `[300,300,300]` 变为 `[3200,3200,3200]`。
  - K-14：「给我出1道关于残差的简答题」由失败变为正常出题，练习集标题为「残差练习」。
  - K-23：同一请求 `language=zh` 得中文题、`language=en` 得英文题。
  - 全部评测回归：Router v2 73.1%/范围保持 100%、Integrity 100%、Orchestrator 100%、端到端 `loop_closed: true`。
- **过程中的一次自伤**：把 `CITATION_SNIPPET_LIMIT` 放进 `tutor_service` 造成 `practice_service ↔ tutor_service` 循环导入，容器进入重启循环。常量属于展示层，已移入 `app/agents/presenters.py`（两个 Service 本就单向依赖它）。
- **下一步建议**：剩余可做项按价值排序 —— 扩大忠实度样本量（当前 12 条检出力不足）、K-21（章节歧义不反问）、K-17（批改保守）、K-2（引用校验失败无重试）。路线图只剩第 7 步 Redis 与第 10 步监控，两者都不影响功能可用性。

---

### 2026-08-27 · Claude Code · commit `未提交`

- **做了什么**：修复 K-27/K-28/K-29 —— 产品核心承诺失效的那组问题。方案由用户提出：**资料在自己的语言里被检索，提问先译成资料语言**，而不是换多语言嵌入。
  1. **嵌入** `HashEmbedding` → `BAAI/bge-small-en-v1.5`（384 维、67MB、ONNX 无需 torch），模型烘进镜像，运行时不下载。加载失败降级为散列并告警，服务仍可启动。
  2. **分块** 3200 → 1200 字符。嵌入模型截断在 512 token ≈ 1600 字符，此前 **65% 的片段尾部出现在引用里却不在索引中**。重新入库后片段数由 216 增至 544。
  3. **语言** 新增 `app/rag/language.py`，按 CJK 占比判定；整份资料按文本量加权取主导语言，一页中文批注不会翻转整份英文讲义。迁移 `0009` 给 `documents` 加 `language`，向量元数据同步携带。
  4. **翻译** 新增 `QueryTranslationGateway`，**接在路由层**，译文写入 `QueryPlan.retrieval_query`，学习者看到的 `standalone_query` 不变。仅在提问语言 ≠ 资料语言时调用模型；任何失败都返回原查询。
  5. **重新入库** 新增 `python -m app.tasks.reindex`，走与上传完全相同的那一条入库路径。集合升到 `course_materials_v2`。
  6. **评测** 新增 Cross-lingual v1（14 题 × 中英 = 28 次，**不指定资料**）。关键差别：关键词在**被引用的片段**中查找，不在答案中 —— 这正是 RAG v1 漏掉 K-28 的原因。
- **为什么**：实测中文问「什么是残差」top-5 分数 0.045→0.000（噪声水平），取回 beer-goggles、酒精摄入等无关幻灯片，而答案看起来完全正确 —— 模型用先验知识作答，把引用挂在只是恰好含 "residual" 一词的片段上。这直接违反「答案锚定在你自己的资料上」。
- **改了哪些文件**：
  - 新增：`app/rag/language.py`、`app/agents/query_translation.py`、`app/tasks/reindex.py`、`migrations/versions/0009_document_language.py`、`tests/evals/{retrieval_metrics.py,run_retrieval_eval.py}`、`tests/evals/datasets/retrieval_crosslingual_v1.jsonl`、`tests/evals/baselines/retrieval_crosslingual_v1.json`、`tests/unit/test_language_and_translation.py`
  - 修改：`app/rag/{embeddings,chunking,retrieval}.py`、`app/infrastructure/vector_store.py`、`app/agents/{routing,intent_router,learning_agents}.py`、`app/services/tutor_service.py`、`app/tasks/ingestion.py`、`app/domain/models.py`、`app/schemas/document.py`、`app/core/config.py`、`Dockerfile`、`docker-compose.yml`、`requirements.txt`、`.env.example`、`docs/{ARCHITECTURE.md,architecture.html}`、`tests/evals/README.md`、`README.md`
- **怎么验证的**：
  - 单元测试 `252 passed`（改动前 241，新增 11）。
  - **修复前后同一问题对照**：「解释一下什么是残差」由 `partial`、引用指向啤酒实验，变为 `sufficient`、译作 `Explain what residuals are.`、**8 条引用全部含 residual**。
  - Cross-lingual v1 基线：`citation_support_rate` 100%、**`cross_language_parity` 100%**、`ungrounded_claim_rate` 0%、中文翻译触发率 91.7%。
  - 全部既有评测回归：Router v2 73.1%/范围保持 100%、Integrity 100%、Orchestrator 100%、端到端 `loop_closed: true`。
- **过程中的三次自伤**：把 `document.language` 插进了 `vector_cleanup` 分支中间导致缩进错误、Worker 重启循环；`docker-compose.yml` 里 worker 的集合名默认值写死 v1 覆盖了代码默认，导致第一次重新入库写错集合；速度基准用了 `docs[:16]` 这个偏短样本，把 MiniLM 报成 0.22s/段（实际 1.19s），已在给用户的结论中更正。
- **代价，如实记录**：镜像 348MB → api 744MB / worker 1.01GB；跨语言提问每次多一次翻译调用（约 0.5–1.5 秒）；入库速度约 1.3 秒/段，104 页 PDF 约 3 分钟（后台进行，不阻塞上传）。
- **下一步建议**：P1 的头两分钟体验 —— 可访问的线上 demo、演示数据、流式输出、CI。另 K-2（引用校验仍只查编号）值得做成真正的论断—来源对齐校验。

---

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：完成 K-19 —— 第二轮人工忠实度评审已由 Queena 完成并记录为基线。
- **结果**（12 条，评审者 Queena，种子 20260826，工具版本 `rendered-2`）：
  - `grounding_rate` 100%、`citation_accuracy_rate` 100%、**`fabrication_rate` 0%**、`declined_when_unsupported_rate` 100%。
  - 12 个分层各 1 条，全部通过。
- **一处需要评审者确认的判断**：`linear-015`（唯一的资料外问题）的 `admits_gap` 被勾为否，但该回答两次明确指出「资料中未涉及贝叶斯方法」。这一条会让 `declined_when_unsupported_rate` 归零、触发硬性门槛失败 —— 等于记录一个不存在的缺陷，正好是第一轮错误的镜像。**因此没有自行更正，而是向评审者确认后才改**；评审者确认为漏勾。更正过程与理由已写入基线的 `rounds` 字段。
- **如实标注了样本量局限**：基线中写明「12 条全对不能读作系统忠实度 100%」—— 12 次全对时真实失败率的 95% 置信上界约为 22%。该基线的价值在于它是**第一份由人判定、而非机器代理指标给出的结论**，以及流程本身可重复。
- **两轮记录都保留**：第一轮标为 `void` 并写明作废原因（评审页只显示 300 字符导致 10/12 引用被误判），第二轮标为 `recorded`。基线中另记 `instrument_lesson`：评审工具必须让评审者看到判断所需的全部依据，否则它制造的缺陷比它发现的更多。
- **改了哪些文件**：`tests/evals/baselines/faithfulness_v1.json`（从模板变为完整基线）、`docs/PROGRESS.md`。新增 `artifacts/evals/faithfulness_verdicts_round2.json`（未跟踪）。**未改动任何 `app/` 代码。**
- **怎么验证的**：单元测试 `209 passed`；评分脚本按契约拒绝半份评审的行为此前已验证。
- **下一步建议**：路线图只剩第 7 步 Redis 与第 10 步监控，两者都不影响功能可用性。若要继续提升可信度，扩大忠实度样本量（如 30 条、换种子）比做这两步更有价值 —— 当前 12 条对低频失败几乎没有检出力。另有 K-17（批改保守）、K-21（章节歧义未反问）、K-22（Web 端引用仅 300 字符）待处理。

---

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：首轮人工忠实度评审完成，但**结果作废** —— 评审工具本身有缺陷。修复后重新抽样，等待第二轮。
- **发生了什么**：评审者判定 12/12 依据充分、0 编造，但 **10/12 引用被判为「指错了地方」**，备注多为「回答是对的，但引用的原文跟回答对不上」和「看不懂引用内容」。
- **复核结论：引用其实是对的，是评审页误导了评审者。** 评审页显示的是 API 返回的 `snippet`，只有 **300 字符**；而实际片段中位长度约 **2000 字符**，评审者只看到了证据的约 15%。以 `linear-004` 的 `[c3]` 为例，完整片段 1715 字符，其中 `least squares` 在第 403 字符、`as close as possible` 在第 612 字符、`minimiz` 在第 1388 字符 —— **支撑句全部落在被截断的部分**。
- **为什么作废而不是记录**：一个让正确行为看起来是错的评审工具，比没有评审更糟。把 10/12 引用失败写进基线，会凭空制造一个不存在的严重缺陷，并可能引出针对幻觉问题的「修复」。
- **改了什么**：
  1. 抽样器改为按 `chunk_id` 直接从检索器取回**完整片段**，不再依赖 API 的 300 字符预览；取不到完整内容时明确标注「仅预览」，绝不让评审者在不知情的情况下判断一个截断。
  2. 片段头部标注字符数，正文可滚动，并在页面说明中提示「支撑句常常不在开头」。
  3. 新增 `INSTRUMENT_REVISION`，并写入 localStorage 存储键。**这是必须的** —— 种子相同则存储键相同，第二轮会静默恢复第一轮那些被误导的判断。
  4. 首轮结果保留为 `artifacts/evals/faithfulness_verdicts_round1_invalid.json`，文件名标明作废。
- **顺带记录 K-22**：学习者在 Web 端展开引用时看到的也是同一个 300 字符预览。对核实一条论断可能同样不够，只是可以点击跳转 PDF 页作为补偿。是否加长需要权衡响应体积，未擅自改动。
- **怎么验证的**：
  - 重新抽样后 45 条引用**全部取到完整片段**，长度 1415–3200 字符、中位 1985，`truncated` 计数为 0。
  - `linear-004` 的 `[c3]` 现在包含全部三处支撑表述。
  - 存储键已变为 `studypilot-faithfulness-full-chunk-1-20260826`，与第一轮不同。
  - 单元测试 `209 passed`。
- **评审者随后指出第二个问题**：回答和引用都是纯文本，而回答含 LaTeX 公式，纯文本下根本无法判读。已再次修复：
  1. 评审页**复用主应用自己的渲染函数** —— 从 `app/web/static/app.js` 按名字抽取五个函数内联进页面，并随页面拷贝 KaTeX。评审者看到的与学习者看到的一致，且不会随时间漂移。
  2. 引用片段保持原始抽取文本不渲染（那正是模型看到的内容），但标注了「PDF 抽取会破坏数学符号」，并为每条引用提供指向原文 PDF 对应页的链接。
  3. `INSTRUMENT_REVISION` 提升为 `rendered-2`，存储键随之改变，第二轮从空白开始。
- **下一步**：**需要第二轮人工评审**。题目与第一轮相同（种子未变），这次能看到完整的引用原文、渲染后的公式，以及可跳转的 PDF 原页。

---

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：为 K-19 建立人工忠实度抽检流程。这是唯一一处结论必须由人给出的评测，因此交付的是**工具和门槛**，不是数字。
  1. `run_faithfulness_sample.py`：按问题类型分层抽样（概念、公式、方法、示例、解释、资料外问题等），真实提问并抓回答案与**被引用的原文片段**，生成自包含的本地评审页。随机种子固定，可复现同一批样本。
  2. 评审页是单文件 HTML，四项判断各自独立记录，进度自动存 localStorage 可分次填写，填完导出 JSON。**只留在本机** —— 它逐字引用了学习者自己的课程资料。
  3. `faithfulness_metrics.py` 把两类错误分开报告：`fabrication_rate`（编造）、`grounding_rate`（依据充分）、`citation_wrong_rate`（引用指错）、`declined_when_unsupported_rate`（资料外问题是否被指出）。
  4. `run_faithfulness_eval.py` **拒绝给未填完的评审表打分** —— 半份评审报出的满分比没有评审更有害。
  5. `baselines/faithfulness_v1.json` 写明五条门槛，其中两条硬性：`fabrication_rate` 必须为 0，`declined_when_unsupported_rate` 必须为 1.0。
- **为什么**：此前七套评测衡量的全是机器可判定的代理指标 —— 引用能否解析、是否落在指定文档内、关键词是否出现。**没有一项能回答产品真正立足的那个问题：这个回答对它引用的原文忠实吗。**
- **改了哪些文件**：
  - 新增：`tests/evals/faithfulness_metrics.py`、`tests/evals/run_faithfulness_sample.py`、`tests/evals/run_faithfulness_eval.py`、`tests/evals/baselines/faithfulness_v1.json`、`tests/unit/test_faithfulness_metrics.py`
  - 修改：`tests/evals/README.md`
  - **未改动任何 `app/` 代码。**
- **怎么验证的**：
  - 单元测试 `209 passed`（改动前 200，新增 9），覆盖判断取值校验、分层聚合、以及「半份评审必须被拒绝」。
  - 首批抽样成功：12 条覆盖 12 个不同层，含 1 条资料外问题，共 48 条引用，evidence 分布 5 sufficient / 7 partial。
  - 抽查资料外问题 `linear-015`：回答明确指出「资料中没有给出贝叶斯先验选择方法」，并列举了资料实际涵盖的内容，行为正确。
  - 用合成评审数据端到端演练了评分链路，确认打通后**已清除合成结果**，避免被误当成真实基线。
- **建立过程中发现的两件事**：
  - **抽样器初版缺陷（已修）**：未固定到题目指定的资料，导致 12 条中有 4 条「根据资料第一章…」的问题跨两份资料检索失败、返回「证据不足」。若不修，会让评审者把抽样瑕疵误判为产品缺陷。已改为与 RAG 运行器一致地固定文档，修复后无引用样本降为 0。
  - **产品观察（记为 K-21）**：同一个问题，指定资料时返回 4 条引用的完整回答，不指定时直接「证据不足」。系统具备章节解析能力，但两份资料都有「第一章」时的歧义没有被处理。理想行为是反问指哪一份，而不是放弃。
- **下一步建议**：**这一步需要你来完成** —— 打开 `artifacts/evals/faithfulness_review.html` 评审 12 条，导出后运行评分脚本填入基线。之后路线图只剩第 7 步 Redis 与第 10 步监控，两者都不影响功能可用性。

---

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：完成路线图第 12 步收尾 —— 用户偏好设置与单个薄弱点删除。
  1. **后端偏好**：`User` 模型原本就有 `explanation_language`、`answer_language`、`explanation_style`，但从未暴露。迁移 `0008` 补上 `default_question_type`、`default_difficulty`、`default_question_count`、`include_language_feedback`，新增 `GET/PATCH /api/v1/preferences`。部分更新只改学习者实际提交的字段，不会静默重置其余设置。
  2. **删除单个薄弱点**：`DELETE /api/v1/courses/{id}/topics/{topic}`，对应 PRD 8.6「用户可以删除某项薄弱点」。此前只能整体清空进度。
  3. **设置界面**：新增偏好对话框，覆盖 PRD 8.6 列出的语言、讲解风格和练习默认值，并把语言反馈开关接入批改请求（审计记为「语言反馈开关未接入 Web」）。
  4. 偏好作为默认值注入对话与练习表单，单次操作仍可临时覆盖。
  5. 知识点行新增「移除」按钮，带二次确认。
- **为什么**：路线图第 6 节第 12 项的最后一块，对应 PRD 8.6「用户控制」与审计文档「无用户偏好设置 API/UI；无删除单个薄弱点」。
- **改了哪些文件**：
  - 新增：`migrations/versions/0008_user_preferences.py`、`app/schemas/preferences.py`、`app/infrastructure/repositories/user_repository.py`、`app/services/preferences_service.py`、`app/api/v1/routes/preferences.py`、`tests/unit/test_preferences.py`
  - 修改：`app/domain/models.py`、`app/api/v1/router.py`、`app/api/v1/routes/progress.py`、`app/infrastructure/repositories/progress_repository.py`、`app/llm/gateway.py`、`app/web/index.html`、`app/web/static/app.js`、`app/web/static/styles.css`、`tests/unit/test_web.py`、`tests/unit/test_tutor.py`
- **怎么验证的**：
  - 单元测试 `200 passed`（改动前 180，新增 20）。
  - 迁移 `0007 → 0008` 在运行中的数据库上正常执行。
  - 接口行为：部分更新 `{"default_question_count":3,"include_language_feedback":true}` 只改这两项，其余六项保持不变；删除薄弱点首次 204、再次 404。
  - 全部评测回归：Router v2 意图准确率 73.1%、范围保持 100%；Integrity v1 100%；Orchestrator v1 100%；端到端闭环 `loop_closed: true`。
- **端到端验证抓到一个真缺陷（K-20）**：偏好确实传到了 `query_plan.requested_language`，但**模型没有照做** —— 用中文提问、要求英文回答时，模型跟随了提问语言。四组语言×提问语言组合中失败一组。偏好设不上去就等于没有这个功能，因此把讲解网关的语言指令从 `Requested language: en` 改为显式声明「即使学生用其他语言提问也必须遵守」，并保留公式、符号和原文引用不变。修复后四组组合全部正确。
- **下一步建议**：只剩第 7 步 Redis 短期学习状态和第 10 步链路与成本监控。两者都不影响功能可用性 —— 第 7 步是性能优化（当前每轮从 PostgreSQL 重建上下文），第 10 步在单用户 MVP 下收益有限。若目标是作品完整度，更值得做的是 K-19（人工忠实度抽检，需要人工判断）和 K-17（批改保守倾向，需要更多样本）。

---

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：路线图第 12 步的主体部分 —— 让前端能操作后端已经具备的能力。
  1. **补两个缺失接口**：`GET /courses/{id}/practice-sets`（练习历史，含题量、已作答数、待加强题数、平均分）和 `POST /documents/{id}/reprocess`（失败资料重试）。
  2. **练习历史与错题重练**：历史列表可展开某组练习，显示每题的来源、最佳得分和批改后的 rubric 逐条得分；「重练错题」只列出最佳得分 ≤60 的题目。
  3. **历史对话选择**：对话下拉框可切回任意历史会话并还原完整消息与引用。
  4. **课程与资料的增删改**：课程编辑/删除、资料删除、失败资料重试，三项不可逆操作都有二次确认并写明后果。
  5. **学习趋势与常见错误**：进度页新增得分趋势条形图、跨主题聚合的常见错误排行、最近练习列表，以及清空进度入口。
- **为什么**：路线图第 6 节第 12 项，对应审计文档第 4 节 P1 的前四项。后端能力此前已远超前端可操作范围 —— 练习历史、错题重练、学习趋势都只能通过 API 访问。
- **改了哪些文件**：
  - 新增：`tests/unit/test_practice_history.py`
  - 修改（后端）：`app/schemas/practice.py`（`PracticeSetSummary`/`PracticeSetList`）、`app/infrastructure/repositories/practice_repository.py`（`list_for_course`、`best_scores_for_questions`）、`app/services/practice_service.py`、`app/api/v1/routes/practice.py`、`app/infrastructure/repositories/document_repository.py`（`requeue`）、`app/services/document_service.py`（`reprocess`）、`app/api/v1/routes/documents.py`
  - 修改（前端）：`app/web/index.html`、`app/web/static/app.js`、`app/web/static/styles.css`
  - 修改（测试）：`tests/unit/test_web.py`、`tests/unit/test_grading_eval_metrics.py`
- **怎么验证的**：
  - 单元测试 `180 passed`（改动前 167，新增 13）。
  - 全部确定性评测回归：Router v2 意图准确率 73.1%、范围保持 100%；Integrity v1 100%；Orchestrator v1 100%。
  - 端到端闭环重跑：五阶段全通过，`loop_closed: true`。
  - 逐一核对前端依赖的数据形状与实际接口返回一致（对话消息、Attempt 的 `criterion_results`、题目 `sources`、主题的 `common_errors`/`recent_score`/`last_practiced_at`）。
  - 接口行为验证：对已成功的资料调用重试，正确返回 `409 DOCUMENT_NOT_RETRYABLE`（重新处理健康资料会产生重复知识片段）。
  - 练习历史摘要**不暴露参考答案和 rubric** —— 该列表在作答前可见，专门加了测试守住这条。
- **修正了上一轮的一个疏漏**：K-4 提交时 `test_grading_eval_metrics.py` 仍在断言基线为 `not_run`，但当时跑测试**没有重建镜像**，测的是镜像里的旧基线文件，因此「167 passed」是对着过期数据得出的。这正是 `AGENTS.md` 里写明的那个坑，我自己踩了。该测试已改为校验已记录基线的契约（90 次、全部成功、排序与重复稳定性满分、越界数量与 `score_band_accuracy` 一致、诊断与门槛齐备）。
- **下一步建议**：第 12 步剩用户偏好设置页，需要先建后端偏好模型（语言、默认讲解模式、默认题型难度、语言反馈开关），审计文档记为「无用户偏好设置 API/UI」。之后剩第 7 步 Redis 与第 10 步监控。

---

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：完成 K-4，记录 Grading v1 的 90 次完整基线，并诊断了其中 9 次越界的成因。
  1. 跑完 10 题 × 三档 × 3 次重复共 90 次真实模型调用，耗时 3 分 37 秒。
  2. `score_band_accuracy` 为 90%，其余全部指标满分。**诊断了这 10% 的确切成因**，而不是记个数字了事。
  3. 9 次越界全部集中在 `grade-003/004/005` 的 partial 档，且三次重复精确一致（均为 25.0）—— 这说明是确定性行为，不是模型抖动。这三题都是 2 条 rubric、各 0.5 权重，partial 答案各自完整覆盖其中一条，理论应得 50。
  4. 做了受控实验区分成因：把答案里"但我没有说明…"这类元评论去掉后重新批改。`grade-003` 由 25 升至 50（**数据集人为杂质**，真实学生不会自述缺了什么，这句话把已覆盖条目的得分也拉了下去）；`grade-004`、`grade-005` 去杂后仍为 25（**批改器偏保守**，对措辞简短但表述明确的条目只给 0.5）。
- **为什么**：K-4 是路线图第 9 步的唯一遗留项，也是审计文档中「有实现但无完整基线」的最后一处。
- **改了哪些文件**：
  - 修改：`tests/evals/baselines/grading_v1.json`（从 `status: not_run` 变为完整基线 + 诊断 + 六条合入门槛）、`tests/evals/README.md`、`README.md`、`docs/PROGRESS.md`
  - **未改动任何 `app/` 代码，也未修改评测数据集。**
- **怎么验证的**：
  - 90/90 次调用全部成功，`fallback_rate` 0%。
  - `ordering_accuracy` 100%：正确答案得分始终高于部分正确，部分正确始终高于错误。这是批改可用性的底线。
  - `repeatability_within_10_points` 100%：同一答案三次批改分差不超过 10 分。
  - `criterion_completeness`、`evidence_validity`、`feedback_completeness` 均 100%，`average_latency_ms` 2394。
  - 三档平均分 100 / 47.6 / 0，区分度清晰。
- **重要判断**：基线**如实记录 90%，没有通过修改数据集把数字抬到 100%**。理由是基线的职责是记录现实 —— 一个诊断清楚的 90% 比一个靠改数据集得来的 100% 更有价值。偏差性质也已判明：排序和稳定性满分说明批改稳定可预期，问题是绝对分数偏低而非判断混乱，对学习者的影响是**被低估而非被误导**。
- **下一步建议**：路线图第 12 步前端。后端能力已远超前端可操作范围 —— 练习历史、错题重练、学习趋势、用户设置都还没有界面。K-17（批改保守）需要更多样本才能判断是否调 prompt，不宜凭三个样本动评分标准；K-19（人工忠实度抽检）需要人来做，不是代码任务。

---

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：完成路线图第 9 步剩余部分 —— 编排层评测与端到端闭环评测。
  1. **Orchestrator v1**（30 例，确定性）：Agent 被替换为脚本化替身，只考察编排本身。用例数按路线图第 9 节的四项要求分配：Agent 选择 9、执行顺序 4、上下文传递 3、失败降级 7，另加澄清 1、学术诚信 4、Trace 2。不调用模型也不碰数据库。
  2. **Loop v1**（5 阶段，真实 API）：唯一打真实链路的编排类评测，按学习者实际路径走完讲解→出题→批改→掌握度更新→复习计划，每一步对照**真实状态**校验后置条件而非 mock。
  3. 指标分开报告而非合并成单一通过率：一个「选对了 Agent 但在辅助步骤失败时丢了答案」的编排层不是部分正确，而是在最要紧的地方坏了。
- **为什么**：路线图第 6 节第 9 项。编排层此前有 33 个单元测试但没有版本化基线，无法回答「换了模型或改了 prompt 之后，讲解→出题→批改→更新薄弱点→生成计划这条链路还成立吗」。
- **改了哪些文件**：
  - 新增：`tests/evals/datasets/orchestrator_flows_v1.jsonl`、`tests/evals/orchestrator_metrics.py`、`tests/evals/run_orchestrator_eval.py`、`tests/evals/run_loop_eval.py`、`tests/evals/baselines/orchestrator_v1.json`、`tests/evals/baselines/loop_v1.json`
  - 修改：`tests/evals/README.md`
  - **未改动任何 `app/` 代码** —— 两套评测都是对现有实现的观测。
- **怎么验证的**：
  - Orchestrator v1 基线：30 例全通过，`agent_selection_accuracy`、`execution_order_accuracy`、`isolation_rate`、`context_passing_accuracy`、`answer_preservation_rate`、`skip_correctness`、`failure_containment`、`trace_completeness` 均为 100%。
  - Loop v1 基线：五阶段全通过，`loop_closed: true`，总延迟 22.5 秒（讲解 14.6s、出题 3.7s、批改 2.7s、计划 1.6s）。实测一轮产生 4 条引用、2 道题、1 次真实批改、掌握度累计 9 次作答 23 个主题、6 份计划。
  - 全套确定性评测同时回归：Router v2 意图准确率 73.1%、Integrity v1 100%、Orchestrator v1 100%，单元测试 167 passed。
  - 建立过程中修正了两处**评测自身**的错误（不是实现的错误）：运行器按 `status` 判断 Agent 是否执行，导致返回 `SKIPPED` 的诚信 Guard 被误判为没跑，改为按 `role` 判断；诚信重定向用例没有设置 `source`，不符合「显式规则匹配仍然优先」的实际设计，已补 `source` 字段并新增一条反向用例把该规则钉死。
- **下一步建议**：第 9 步唯一遗留是 **K-4**（Grading v1 的 90 次完整基线），需要约 90 次真实模型调用，属于成本决策而非技术难点。之后建议做第 12 步前端 —— 后端能力已远超前端可操作范围，练习历史、错题重练、学习趋势和用户设置都还没有界面。第 7 步 Redis 和第 10 步监控优先级更低，前者是性能优化，后者在单用户 MVP 下收益有限。

---

### 2026-08-26 · Claude Code · commit `未提交`

- **做了什么**：建立 `integrity-v1` 评测集，并修复它抓到的一个真实缺陷。
  1. 新增 61 条学术诚信判定用例，覆盖四个级别与十个类别。
  2. 新增 `integrity_metrics.py`：把两类错误**分开报告**，不合并成单一准确率。核心指标是 `false_positive_rate`（正当请求被限制）、`blocking_precision`（只有实时考试才允许拒答）、`help_retention_rate`（非阻断轮次仍提供帮助）、`notice_brevity_rate`。
  3. 新增 `run_integrity_eval.py`，进程内运行、不调用模型、逐位可复现。
  4. **修复评测抓到的缺陷**：「我作业做完了，帮我检查思路对不对」原本被判为 `hint_only` —— 学生做完作业请人复核反而被限制。原因是 `_is_graded_work_request` 里「作业」+「做完」同时命中，但「做完了」描述的是学生已完成，不是要求助手代做。新增 `_is_own_work_review()` 豁免，置于实时考试检查之后、其余检查之前。
  5. 为新豁免补 4 条对抗性用例（`review_exemption_abuse`）和 8 个单元测试，验证它不能被反过来用于让助手代做作业。
- **为什么**：第 8 步只有单元测试，没有可比较基线。Guard 是安全相关判定，且**两类错误代价不对称** —— 拒绝帮助一个正当提问的学生直接损害产品核心用途，漏判一次作弊则不然。因此数据集刻意向假阳性倾斜：36 条正当请求中有 24 条刻意包含「作业」「考试」「论文」「答案」等敏感措辞。
- **改了哪些文件**：
  - 新增：`tests/evals/datasets/integrity_requests_v1.jsonl`、`tests/evals/integrity_metrics.py`、`tests/evals/run_integrity_eval.py`、`tests/evals/baselines/integrity_v1.json`
  - 修改：`app/agents/integrity.py`（新增自有成果复核豁免）、`tests/unit/test_integrity_and_skills.py`（+8 例）、`tests/evals/README.md`
- **怎么验证的**：
  - 单元测试 `167 passed`（改动前 159，新增 8）。
  - Integrity v1 基线：`level_accuracy 100%`、**`false_positive_rate 0%`**、`false_negative_rate 0%`、`wrong_severity_rate 0%`、`blocking_precision 100%`、`blocking_recall 100%`、`help_retention_rate 100%`、`notice_brevity_rate 100%`。
  - 修复前的实测是 `level_accuracy 98.1%`、`false_positive_rate 3.1%`（1/32）—— 缺陷是评测集建立后立刻暴露的，不是事后补测。
  - 4 条对抗性用例确认豁免无法被滥用：「我正在考试，我做完了帮我检查」仍判实时考试（考试检查在最前）；「帮我写完这篇论文然后检查」仍判 `submission_risk`；「帮我把作业做完，然后看看对不对」仍判 `hint_only`。
- **下一步建议**：第 9 步现在只剩 **Orchestrator 与端到端闭环评测**。编排层有 33 个单元测试但没有版本化基线，无法回答「换了模型或改了 prompt 之后，讲解→出题→批改→更新薄弱点→生成计划这条链路还成立吗」。另一条路是第 12 步前端 —— 后端能力已远超前端可操作范围。

---

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
