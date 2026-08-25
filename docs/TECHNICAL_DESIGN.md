# StudyPilot 技术设计文档

| 项目 | 内容 |
|---|---|
| 文档版本 | v0.1 |
| 对应 PRD | v0.1 |
| 状态 | MVP 技术方案 |
| 后端语言 | Python 3.11+ |
| Web 框架 | FastAPI |
| 架构形态 | 模块化单体 + 异步任务 |

## 1. 文档目的

本文档将 StudyPilot PRD 转换为可实施的技术方案，定义系统边界、模块结构、数据模型、API、RAG、Agent 工作流、后台任务、可观测性、安全、测试和部署方式。

本文档是开发实现的技术基线。开发中若改变核心数据模型、公开 API 或 RAG/Agent 主链路，应同步更新本文档。

## 2. 设计目标

MVP 必须满足以下技术目标：

1. 不同用户、课程和资料之间严格隔离。
2. PDF、Markdown、TXT 能异步解析并建立可检索索引。
3. 课程问答能够返回真实、可验证的文件与页码引用。
4. 题目、参考答案、rubric 和来源以结构化形式保存。
5. 批改结果可解释、可复查，并能更新知识点掌握度。
6. Agent 负责决策和生成，确定性业务规则由普通代码执行。
7. LLM、Redis 或向量库异常时具有明确错误或安全降级。
8. 核心能力可测试、可监控，并支持本地 Docker 部署。

## 3. 关键技术决策

### 3.1 采用模块化单体

MVP 不拆分微服务。所有业务模块运行在同一个 FastAPI 应用中，文档解析通过独立 Worker 进程执行。

原因：

- 项目处于单人开发和产品验证阶段。
- 课程、问答、练习和画像之间存在较多事务关联。
- 单体更容易调试、测试和部署。
- 模块边界保留，未来可单独拆分文档处理或评测服务。

### 3.2 三类存储各负其责

| 存储 | 用途 | 不应保存 |
|---|---|---|
| PostgreSQL | 用户、课程、文档元数据、题目、作答、掌握度、任务状态 | 大量向量和短期缓存 |
| ChromaDB | 文档片段、Embedding、检索元数据 | 权威业务状态和事务数据 |
| Redis | 会话缓存、限流、短期状态、任务队列 | 唯一持久化业务数据 |

原 EchoMind 只使用 Redis 和 ChromaDB。StudyPilot 新增 PostgreSQL，因为课程、题目、rubric、作答记录和掌握度需要可靠的结构化关联与事务一致性。

### 3.3 LLM Provider 抽象

业务代码不直接依赖 Anthropic SDK。统一通过 `LLMGateway` 调用：

```python
class LLMGateway(Protocol):
    async def generate_text(self, request: LLMRequest) -> LLMResponse: ...
    async def generate_structured(
        self,
        request: LLMRequest,
        schema: type[BaseModel],
    ) -> BaseModel: ...
```

首个实现可继续使用 Anthropic 兼容接口，后续能够替换为其他 Provider。所有结构化输出必须经过 Pydantic 校验和有限次数重试。

### 3.4 Agent 与工作流分离

Agent 只负责需要语言理解或生成的部分，例如问题分类、讲解、出题和评价。以下逻辑由确定性代码负责：

- 用户和课程权限检查
- 文档状态判断
- 检索元数据过滤
- 分数加权和掌握度计算
- 任务状态转换
- 删除与数据清理
- 超时、重试、缓存和熔断

### 3.5 MVP 先采用单用户模式，但保留用户边界

首个本地版本可以使用固定开发用户，不实现完整注册登录。所有数据表、API 上下文和 Chroma 元数据仍必须包含 `user_id`，禁止以后再补数据隔离。

生产化阶段再增加 JWT/OAuth 登录。

## 4. 系统上下文

```text
┌──────────────┐
│ Vue Web App  │
└──────┬───────┘
       │ HTTPS / JSON / multipart
┌──────▼──────────────────────────────────────────────┐
│                 StudyPilot API                      │
│ Course │ Document │ Tutor │ Quiz │ Evaluation      │
│ Planner│ Profile  │ Admin │ Observability          │
└───┬────────┬───────────┬───────────┬────────────────┘
    │        │           │           │
┌───▼───┐ ┌──▼─────┐ ┌───▼─────┐ ┌──▼──────────────┐
│Postgres│ │ Redis  │ │ChromaDB │ │ LLM Provider    │
│业务数据│ │缓存/队列│ │向量索引 │ │生成/结构化输出  │
└───────┘ └────┬────┘ └─────────┘ └─────────────────┘
               │
        ┌──────▼────────┐
        │ Document Worker│
        │解析/分块/索引  │
        └───────────────┘
```

## 5. 运行时组件

| 组件 | 职责 | MVP 方案 |
|---|---|---|
| Web Frontend | 用户界面 | Vue 3 + Vite，后续从现有前端改造 |
| API | REST API、鉴权、业务编排 | FastAPI + Uvicorn |
| Worker | 文档解析与索引 | Python Worker + Redis 队列 |
| PostgreSQL | 结构化业务数据 | PostgreSQL 16 |
| Redis | 缓存、限流、任务队列 | Redis 7 |
| ChromaDB | 课程资料向量检索 | ChromaDB 0.5.x；升级需单独验证 |
| LLM | 问答、出题、评价 | `LLMGateway` Provider 实现 |
| Prometheus | 指标采集 | 复用现有监控模块 |
| Nginx | 反向代理和上传限制 | 复用并改名现有配置 |

## 6. 目标代码结构

```text
StudyPilot/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── dependencies.py
│   │   └── v1/
│   │       ├── courses.py
│   │       ├── documents.py
│   │       ├── conversations.py
│   │       ├── practice.py
│   │       ├── progress.py
│   │       └── system.py
│   ├── core/
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   ├── logging.py
│   │   └── security.py
│   ├── domain/
│   │   ├── course.py
│   │   ├── document.py
│   │   ├── conversation.py
│   │   ├── question.py
│   │   └── mastery.py
│   ├── schemas/
│   │   ├── course.py
│   │   ├── document.py
│   │   ├── tutor.py
│   │   ├── practice.py
│   │   └── common.py
│   ├── services/
│   │   ├── course_service.py
│   │   ├── document_service.py
│   │   ├── tutor_service.py
│   │   ├── practice_service.py
│   │   ├── mastery_service.py
│   │   └── planner_service.py
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── tutor_agent.py
│   │   ├── quiz_agent.py
│   │   ├── evaluator_agent.py
│   │   └── planner_agent.py
│   ├── rag/
│   │   ├── ingestion.py
│   │   ├── parsers.py
│   │   ├── chunking.py
│   │   ├── embeddings.py
│   │   ├── retriever.py
│   │   ├── reranker.py
│   │   └── citations.py
│   ├── infrastructure/
│   │   ├── database.py
│   │   ├── repositories/
│   │   ├── redis.py
│   │   ├── vector_store.py
│   │   ├── file_storage.py
│   │   └── llm/
│   ├── skills/
│   ├── tasks/
│   │   ├── queue.py
│   │   └── document_tasks.py
│   └── observability/
│       ├── metrics.py
│       └── tracing.py
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── evals/
├── data/
│   ├── uploads/
│   └── eval/
├── docs/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

迁移期间允许旧目录和 `app/` 并存，但新功能只写入新结构。完成垂直切片后删除旧客服入口，避免长期维护两套路由。

## 7. 模块职责

### 7.1 API 层

负责：

- 请求解析与 Pydantic 校验
- 获取当前用户
- 调用 Service
- 将领域异常映射为 HTTP 错误
- 返回统一响应

API 层不得直接访问 ChromaDB、Redis 或 LLM。

### 7.2 Service 层

负责业务用例和事务边界，例如：

- 创建课程
- 接收文档并创建解析任务
- 执行课程问答
- 创建练习集
- 提交答案并更新掌握度

### 7.3 Domain 层

保存不依赖 Web 和数据库的业务规则，例如：

- 文档状态转换是否合法
- rubric 总权重校验
- 分数范围校验
- TopicMastery 状态计算
- 学术诚信请求分类

### 7.4 Repository 层

封装 PostgreSQL 读写。Service 依赖 Repository 接口，不依赖 ORM 查询细节。

### 7.5 RAG 层

负责文档解析、分块、索引、检索、重排、证据判断和引用装配，不负责生成最终教学回答。

### 7.6 Agent 层

负责构造提示词、调用 LLM、解析结构化结果。Agent 通过工具接口访问 RAG 和业务数据，不直接连接数据库。

## 8. 数据模型

数据库建议使用 UUID 主键和 UTC 时间。所有用户私有主表包含 `user_id`。表名使用复数 snake_case。

### 8.1 users

| 字段 | 类型 | 约束 |
|---|---|---|
| id | UUID | PK |
| email | VARCHAR(320) | 可空，正式登录后唯一 |
| display_name | VARCHAR(100) | 非空 |
| explanation_language | VARCHAR(16) | 默认 `zh` |
| answer_language | VARCHAR(16) | 默认 `en` |
| explanation_style | VARCHAR(32) | 默认 `deep` |
| created_at | TIMESTAMPTZ | 非空 |
| updated_at | TIMESTAMPTZ | 非空 |

### 8.2 courses

| 字段 | 类型 | 约束 |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK users，索引 |
| name | VARCHAR(200) | 非空 |
| course_code | VARCHAR(80) | 可空 |
| institution | VARCHAR(200) | 可空 |
| semester | VARCHAR(80) | 可空 |
| exam_date | DATE | 可空 |
| target_grade | VARCHAR(40) | 可空 |
| description | TEXT | 可空 |
| created_at | TIMESTAMPTZ | 非空 |
| updated_at | TIMESTAMPTZ | 非空 |
| deleted_at | TIMESTAMPTZ | 软删除，可空 |

索引：`(user_id, updated_at DESC)`。

### 8.3 documents

| 字段 | 类型 | 约束 |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK users，索引 |
| course_id | UUID | FK courses，索引 |
| filename | VARCHAR(500) | 非空 |
| storage_key | VARCHAR(800) | 非空，唯一 |
| checksum_sha256 | CHAR(64) | 非空 |
| mime_type | VARCHAR(100) | 非空 |
| document_type | VARCHAR(32) | 非空 |
| status | VARCHAR(32) | 非空 |
| page_count | INTEGER | 可空 |
| chunk_count | INTEGER | 默认 0 |
| error_code | VARCHAR(80) | 可空 |
| error_message | TEXT | 可空，必须脱敏 |
| created_at | TIMESTAMPTZ | 非空 |
| processed_at | TIMESTAMPTZ | 可空 |
| deleted_at | TIMESTAMPTZ | 可空 |

文档状态机：

```text
UPLOADED → QUEUED → PROCESSING → READY
                         └──────→ FAILED
FAILED → QUEUED
READY / FAILED → DELETING → DELETED
```

唯一约束建议：活跃文档范围内 `(user_id, course_id, checksum_sha256)` 唯一。

### 8.4 conversations 与 messages

`conversations` 保存会话元数据，`messages` 保存持久化消息。Redis 只缓存最近若干轮。

消息字段包括：`role`、`content`、`agent_type`、`citations_json`、`model_name`、`latency_ms`、`created_at`。

### 8.5 practice_sets

保存一次练习的配置：课程、资料范围、题型、难度、数量、语言、是否针对薄弱点及生成状态。

### 8.6 questions

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID | PK |
| practice_set_id | UUID | FK |
| course_id | UUID | 数据隔离 |
| question_type | VARCHAR(32) | single_choice / short_answer / concept |
| difficulty | VARCHAR(16) | basic / medium / advanced |
| content | TEXT | 题目正文 |
| options_json | JSONB | 选择题选项，可空 |
| knowledge_points_json | JSONB | 知识点列表 |
| reference_answer | TEXT | 不在答题前返回 |
| rubric_json | JSONB | 结构化评分标准 |
| source_refs_json | JSONB | 生成依据 |
| generation_metadata_json | JSONB | 模型、提示词版本等 |

### 8.7 attempts

每次提交都创建新 Attempt，不覆盖历史答案。保存原始答案、总分、各维度分数、反馈、来源、模型和 rubric 版本。

### 8.8 topic_mastery

主键建议为 `(user_id, course_id, normalized_topic)`。保存：

- `display_topic`
- `status`
- `average_score`
- `recent_score`
- `attempt_count`
- `common_errors_json`
- `last_practiced_at`
- `updated_at`

MVP 掌握度分数：

```text
mastery = 0.6 × 最近三次加权平均 + 0.3 × 历史平均 + 0.1 × 练习覆盖度
```

状态阈值暂定：

- 未练习：`attempt_count = 0`
- 薄弱：`mastery < 0.50`
- 学习中：`0.50 ≤ mastery < 0.80`
- 已掌握：`mastery ≥ 0.80` 且至少完成 2 次有效练习

阈值必须通过配置管理，后续根据评测调整。

### 8.9 jobs

后台任务记录：`id`、`job_type`、`status`、`resource_id`、`attempts`、`progress`、`error_code`、`created_at`、`started_at`、`finished_at`。

数据库是任务状态的权威来源，Redis 消息仅用于触发执行。

## 9. ChromaDB 设计

### 9.1 Collection

MVP 使用单一 `course_materials_v1` collection，通过元数据隔离，避免每门课程创建 collection 导致管理复杂。

必需元数据：

```json
{
  "user_id": "uuid",
  "course_id": "uuid",
  "document_id": "uuid",
  "document_type": "lecture",
  "source_file": "lecture_04.pdf",
  "page_number": 18,
  "section_title": "Regularization",
  "language": "en",
  "chunk_index": 42,
  "content_hash": "sha256",
  "schema_version": 1
}
```

Chunk ID 使用稳定格式：`{document_id}:{chunk_index}:{content_hash_prefix}`。

### 9.2 一致性规则

- PostgreSQL 中 `documents.status = READY` 前，所有 Chunk 必须写入成功。
- 任务失败时清理本次写入的 Chunk，再标记 FAILED。
- 删除文档时先标记 DELETING，再按 `document_id` 删除向量，最后标记 DELETED。
- Chroma 不是文档清单的权威来源。
- 索引格式变化时增加 `schema_version`，通过重建任务迁移。

## 10. 文件存储

MVP 使用本地目录 `data/uploads/{user_id}/{course_id}/{document_id}/original`。数据库只保存 `storage_key`，不保存绝对路径。

文件名用于展示，实际存储路径使用 UUID，防止路径穿越和重名覆盖。

生产环境可实现相同接口的 S3/对象存储适配器：

```python
class FileStorage(Protocol):
    async def save(self, stream, storage_key: str) -> StoredFile: ...
    async def open(self, storage_key: str): ...
    async def delete(self, storage_key: str) -> None: ...
```

## 11. 文档摄取流程

### 11.1 上传请求

```text
校验当前用户与课程
→ 校验扩展名、MIME、大小
→ 流式计算 SHA-256 并保存文件
→ 检查重复文档
→ 创建 Document(UPLOADED)
→ 创建 Job(QUEUED)
→ 投递任务
→ 返回 202 Accepted
```

上传接口不等待解析完成。

### 11.2 Worker 处理

```text
领取任务
→ 原子更新为 PROCESSING
→ 按文件类型解析
→ 文本清洗与语言识别
→ 提取页码和章节
→ 分块
→ 生成 Embedding
→ 批量写入 ChromaDB
→ 更新 chunk_count/page_count
→ Document 标记 READY
→ Job 标记 SUCCEEDED
```

### 11.3 Parser 接口

```python
class DocumentParser(Protocol):
    def supports(self, mime_type: str, suffix: str) -> bool: ...
    async def parse(self, file_path: Path) -> ParsedDocument: ...
```

`ParsedDocument` 由 `ParsedPage` 组成，每页包含页码、文本和可选章节标题。

PDF MVP 建议使用 PyMuPDF。MD/TXT 使用 Python 标准库并进行编码检测。扫描型 PDF 若提取文本过少，返回 `OCR_REQUIRED`，不在 MVP 中静默生成空索引。

### 11.4 分块策略

MVP 默认：

- 优先按标题和段落分块。
- 单 Chunk 目标约 500–800 tokens。
- 相邻 Chunk 重叠约 80–120 tokens。
- 不跨越文档页时优先保留准确页码。
- 表格、公式上下文和标题尽量保存在同一 Chunk。
- 保存清洗后的检索文本与原始展示文本。

参数进入配置并记录在索引版本中，不能散落在代码中。

## 12. RAG 查询设计

### 12.1 QueryPlan

每次课程问答先生成或规则构建 QueryPlan：

```json
{
  "standalone_query": "Explain the difference between L1 and L2 regularization",
  "course_id": "uuid",
  "document_types": ["lecture"],
  "document_ids": [],
  "page_range": null,
  "requested_language": "zh-en",
  "top_k": 8
}
```

用户显式选择的课程与范围不可被 LLM 覆盖。

### 12.2 检索流程

1. 校验课程归属。
2. 将多轮追问改写为独立问题；清晰问题跳过 LLM 改写。
3. 强制添加 `user_id`、`course_id` 和用户选择的元数据过滤。
4. 执行向量召回。
5. MVP 可复用现有关键词/查询改写能力；第二阶段补充正式 BM25。
6. 合并、去重并重排。
7. 执行证据充分性检查。
8. 返回 `RetrievedEvidence[]` 给 Tutor Agent。

### 12.3 重排

首版优先采用轻量方案：向量分数、关键词覆盖、标题匹配和范围优先级加权。LLM rerank 作为可配置增强，失败时回退到融合分。

### 12.4 证据充分性

不得只依赖固定相似度阈值。综合考虑：

- Top 结果得分
- 多个结果是否一致
- 关键实体和术语覆盖
- 是否满足指定文档/章节范围
- 问题是否要求资料中不存在的事实

输出：`SUFFICIENT`、`PARTIAL` 或 `INSUFFICIENT`。

### 12.5 Citation

```json
{
  "citation_id": "c1",
  "document_id": "uuid",
  "filename": "lecture_04.pdf",
  "page_number": 18,
  "section_title": "Regularization",
  "snippet": "...",
  "chunk_id": "..."
}
```

Tutor 输出正文使用稳定引用标记，如 `[c1]`。服务端验证所有引用 ID 都存在于本次 evidence 中，再转换为前端结构。模型生成但不存在的引用必须丢弃并触发一次修复；仍失败则返回无行内引用的安全降级答案和实际来源列表。

## 13. Agent 与工作流

### 13.1 意图类型

```python
class LearningIntent(str, Enum):
    COURSE_QA = "course_qa"
    CONCEPT_EXPLANATION = "concept_explanation"
    PRACTICE_GENERATION = "practice_generation"
    ANSWER_EVALUATION = "answer_evaluation"
    STUDY_PLANNING = "study_planning"
    PROGRESS_REVIEW = "progress_review"
    DOCUMENT_MANAGEMENT = "document_management"
    GENERAL = "general"
```

API 路径已经明确的请求不需要再做意图识别。例如 `/practice-sets` 直接进入 Quiz 工作流。统一聊天入口才需要 Orchestrator。

MVP 统一聊天入口使用 `LearningIntentRouter` 执行高精度确定性路由，输出 `IntentDecision` 和不可覆盖用户显式范围的 `QueryPlan`。路由目标包括：

| RouteTarget | 数据源/工作流 | 是否执行 RAG |
|---|---|---|
| `course_catalog` | PostgreSQL documents | 否 |
| `progress` | ProgressRepository | 否 |
| `study_plan` | StudyPlanRepository | 否 |
| `practice` | Practice 工作流入口 | 否 |
| `general` | 产品能力回答 | 否 |
| `rag` | CourseRetriever + Tutor Agent | 是 |

规则路由无法高置信度匹配时，默认进入无副作用的 `COURSE_QA` RAG 路径。后续可增加结构化 LLM 分类作为低置信度补充，但不允许模型覆盖 `course_id`、`document_ids`或页码范围。

### 13.2 Tutor Agent

输入：用户问题、语言和讲解模式、对话摘要、检索证据。

输出：

```json
{
  "answer": "... [c1]",
  "citation_ids": ["c1"],
  "key_terms": [{"term": "regularization", "translation": "正则化"}],
  "evidence_status": "sufficient",
  "suggested_followups": ["..."]
}
```

约束：不得生成未提供的课程引用；证据不足时必须降低断言强度。

### 13.3 Quiz Agent

输入：课程范围、题型、难度、语言、知识点、检索证据。

输出为结构化 `GeneratedQuestion[]`。rubric 每项包含 `criterion`、`weight`、`required_concepts` 和 `evidence_ids`，总权重必须等于 1。

生成后执行确定性校验：

- 数量和题型是否符合请求
- 所有引用是否存在
- rubric 权重是否合法
- 选择题是否存在且仅存在一个正确选项
- 题面是否意外包含答案

### 13.4 Evaluator Agent

输入：不可变题目快照、不可变 rubric、用户答案和原始证据。

输出：

```json
{
  "criterion_results": [
    {
      "criterion_id": "r1",
      "earned_ratio": 0.8,
      "reason": "...",
      "evidence_ids": ["c2"]
    }
  ],
  "knowledge_errors": [],
  "language_feedback": [],
  "summary": "...",
  "recommended_topics": []
}
```

总分由服务端依据 rubric 权重计算，LLM 不直接决定最终总分。语言反馈默认不影响知识分，除非题目明确将语言计入 rubric。

### 13.5 Planner Agent

MVP 只输出主题优先级和下一步学习任务，不实现复杂日历调度。

输入：考试日期、可用时间、课程主题、TopicMastery、最近活动。

确定性代码先计算紧迫度和薄弱度，Planner 负责将结果组织成可执行计划。

### 13.6 学术诚信 Guard

在 Tutor/Quiz 前执行请求风险分类：

- `LEARNING_ALLOWED`
- `HINT_ONLY`
- `SUBMISSION_RISK`
- `LIVE_EXAM_PROHIBITED`

分类结果决定允许的工作流。风险判断、采取的策略和用户可获得的替代帮助写入日志，但不保存不必要的敏感内容。

## 14. Skills 设计

目标 Skills：

```text
skills/
├── bilingual_tutoring/SKILL.md
├── quiz_generation/SKILL.md
├── answer_evaluation/SKILL.md
├── study_planning/SKILL.md
└── academic_integrity/SKILL.md
```

每个 Skill 的 Front Matter 至少包含：`name`、`description`、`keywords`、`agents`、`enabled`、`version`。

Skill 只保存稳定业务规则，不保存运行时用户数据、密钥或课程全文。加载失败时保留上一个有效版本，并暴露错误状态。

## 15. API 设计

API 前缀：`/api/v1`。响应 JSON 使用 snake_case。时间使用 ISO 8601 UTC。列表采用 cursor 或 page/size 分页；MVP 可先 page/size。

### 15.1 统一响应与错误

成功响应直接返回资源或：

```json
{"data": {}, "meta": {}}
```

错误响应：

```json
{
  "error": {
    "code": "DOCUMENT_NOT_READY",
    "message": "课程资料仍在处理中",
    "request_id": "uuid",
    "details": {}
  }
}
```

主要状态码：400 参数语义错误，401 未认证，403 无权访问，404 不存在，409 状态冲突，413 文件过大，422 校验失败，429 限流，502 Provider 失败，503 依赖不可用。

### 15.2 课程

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/courses` | 创建课程 |
| GET | `/courses` | 课程列表 |
| GET | `/courses/{course_id}` | 课程详情 |
| PATCH | `/courses/{course_id}` | 更新课程 |
| DELETE | `/courses/{course_id}` | 删除课程及关联数据 |

### 15.3 文档

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/courses/{course_id}/documents` | 上传文档，返回 202 |
| GET | `/courses/{course_id}/documents` | 文档列表 |
| GET | `/documents/{document_id}` | 文档状态 |
| POST | `/documents/{document_id}/retry` | 重试失败任务 |
| DELETE | `/documents/{document_id}` | 删除文档与索引 |

### 15.4 AI 导师

`POST /courses/{course_id}/tutor/messages`

请求：

```json
{
  "conversation_id": null,
  "message": "用中文解释 L1 和 L2 regularization",
  "response_language": "zh-en",
  "mode": "deep",
  "scope": {
    "document_types": ["lecture"],
    "document_ids": [],
    "page_from": null,
    "page_to": null
  }
}
```

响应包含 `message_id`、`conversation_id`、`answer`、`citations`、`evidence_status`、`suggested_followups` 和 `usage`。

### 15.5 练习

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/courses/{course_id}/practice-sets` | 创建并生成练习 |
| GET | `/practice-sets/{id}` | 获取练习及生成状态 |
| POST | `/questions/{id}/attempts` | 提交答案并批改 |
| GET | `/questions/{id}/attempts` | 历史作答 |
| POST | `/attempts/{id}/reevaluate` | 重新评估 |

练习生成可能耗时，接口返回 202 和 `job_id`；前端轮询状态。流式任务状态或 WebSocket 延后实现。

### 15.6 学习进度

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/courses/{course_id}/progress` | 掌握度总览 |
| GET | `/courses/{course_id}/topics` | 知识点列表 |
| GET | `/courses/{course_id}/recommendations` | 下一步建议 |
| DELETE | `/courses/{course_id}/progress` | 清除学习记录 |

### 15.7 系统接口

- `GET /health/live`：进程存活，不检查外部依赖。
- `GET /health/ready`：检查 PostgreSQL、Redis、Chroma 和必要配置。
- `GET /metrics`：Prometheus 指标。
- `GET /api/v1/skills`：Skill 状态。
- `POST /api/v1/skills/reload`：仅开发或管理员可调用。

## 16. 缓存设计

可缓存：

- 相同课程、范围和规范化问题的检索结果，短 TTL。
- 文档与课程基本信息，短 TTL。
- 最近会话上下文。
- LLM 生成结果仅在请求完全一致且不包含动态画像时谨慎缓存。

缓存 Key 必须包含 `user_id` 和 `course_id`。文档新增、删除或重建索引后，通过 `course_index_version` 使旧检索缓存自动失效。

## 17. 并发、幂等与事务

- 上传请求支持 `Idempotency-Key`，防止网络重试创建重复文档。
- 文档任务使用数据库状态更新抢占，避免两个 Worker 同时处理。
- 题目生成完成后一次事务写入练习与题目。
- Attempt 创建后不得覆盖；重新评价产生新 evaluation revision。
- 删除课程使用软删除启动清理任务，完成后再清除文件和向量。
- LLM 请求设置连接超时、总超时和有限重试；只对安全的瞬时错误重试。

## 18. 配置与依赖

建议新增主要依赖：

- `sqlalchemy` 2.x：ORM/数据访问
- `asyncpg`：PostgreSQL 异步驱动
- `alembic`：数据库迁移
- `pymupdf`：文本型 PDF 解析
- `pydantic-settings`：集中配置
- `structlog`：结构化日志
- `tenacity`：受控重试
- `pytest`、`pytest-asyncio`：测试
- `ruff`、`mypy`：质量检查

后台队列可选择：

- MVP 推荐 Dramatiq + Redis，概念简单；或
- 若希望减少新依赖，先实现单独 Worker 轮询 `jobs` 表。

不建议依赖 FastAPI `BackgroundTasks` 完成长时间文档索引，因为进程重启会丢失任务。

环境变量按 `STUDYPILOT_` 前缀统一，例如：

```text
STUDYPILOT_ENV
STUDYPILOT_DATABASE_URL
STUDYPILOT_REDIS_URL
STUDYPILOT_CHROMA_HOST
STUDYPILOT_CHROMA_PORT
STUDYPILOT_UPLOAD_DIR
STUDYPILOT_MAX_UPLOAD_MB
STUDYPILOT_LLM_PROVIDER
STUDYPILOT_LLM_MODEL
STUDYPILOT_LLM_API_KEY
STUDYPILOT_SKILLS_DIR
```

启动时校验生产环境禁止默认密码、占位 API Key 和弱 SECRET。

## 19. 安全设计

### 19.1 访问控制

- Repository 查询默认要求 `user_id`。
- 不能仅通过资源 UUID 查询私有数据。
- Chroma 查询强制注入 `user_id` 和 `course_id`，不接受模型生成这两个值。
- 管理接口独立权限控制。

### 19.2 文件安全

- 仅允许白名单扩展名和 MIME。
- 文件按二进制流处理，不执行宏、脚本或嵌入内容。
- 展示文件名时转义 HTML。
- 限制文件大小、页数、解压后大小和解析时间。
- 原始文件不放在可直接公开访问的静态目录。

### 19.3 Prompt Injection 防护

课程文档是不可信数据。提示词中明确文档内容只作为学习资料，不是系统指令。检索片段与系统指令使用结构化边界分隔。

文档中的“忽略此前指令”“发送密钥”等内容不得执行。工具权限由服务端工作流决定，不能由检索文本授予。

### 19.4 隐私

- 默认不记录完整提示词和课程正文。
- 生产日志对邮箱、Token 和文件内容脱敏。
- 删除接口需要覆盖数据库、文件存储、Chroma 和缓存。
- 明确记录第三方 LLM Provider 会接收哪些文本。

## 20. 可观测性

### 20.1 日志

所有请求携带 `request_id`。Agent/任务链路增加 `trace_id`、`user_id_hash`、`course_id`、`agent_type`、`model`、`prompt_version`、`latency_ms` 和结果状态。

不得记录 API Key、完整文档正文或默认保存完整用户答案。

### 20.2 指标

API：

- 请求量、错误率、P50/P95/P99 延迟
- 各端点 4xx/5xx

文档：

- 上传数、解析成功率、处理耗时
- 页数、Chunk 数、失败原因

RAG：

- 检索耗时、召回数量、重排耗时
- Evidence status 分布
- 引用验证失败次数

LLM/Agent：

- 调用量、错误率、超时、Token、估算费用
- 结构化输出校验失败和重试
- 各 Agent 延迟与降级次数

学习：

- 练习生成成功率
- Attempt 完成量
- 重评次数

### 20.3 健康检查

Liveness 不调用外部服务；Readiness 使用短超时检查依赖。LLM Provider 不纳入硬性 Readiness，以免 Provider 临时异常导致 API 容器被不断重启。

## 21. 测试策略

### 21.1 单元测试

- 文档状态机
- 分块边界与页码继承
- Citation ID 验证
- rubric 权重与分数计算
- 掌握度计算
- 权限过滤和缓存 Key
- 学术诚信策略映射

### 21.2 集成测试

- PostgreSQL Repository
- Redis 缓存失效
- Chroma 写入、过滤、检索和删除
- PDF/MD/TXT 解析
- 上传 → Worker → READY 完整流程
- 删除课程后的级联清理

集成测试使用容器化依赖和独立测试数据库，不能连接开发数据。

### 21.3 API 合约测试

- Pydantic 请求/响应 Schema
- HTTP 状态码和统一错误格式
- 越权访问返回 404 或 403 的一致策略
- 202 异步任务状态转换

### 21.4 LLM 测试

普通 CI 使用 Fake LLM 和固定响应，不调用真实模型。离线 Eval 单独执行真实模型评测。

必须保留：

- 提示词版本
- 模型名称
- 评测数据版本
- 指标结果
- 与 baseline 的差异

### 21.5 端到端关键路径

```text
创建课程
→ 上传资料
→ 等待 READY
→ 带引用问答
→ 生成练习
→ 提交答案
→ 查看反馈
→ 查看更新后的薄弱点
```

## 22. AI 评测

评测数据位于 `tests/evals/datasets`，测试结果位于忽略提交的 artifacts 目录，baseline 以 JSON 提交。

指标：

- Retrieval Recall@K
- Context Precision
- Citation Validity
- Answer Faithfulness
- Constraint Adherence
- Question Answerability
- Rubric Completeness
- Grading Ordering Accuracy
- Grading Repeatability

LLM-as-Judge 只能作为辅助指标。引用存在性、跨课程泄漏、rubric 权重和选择题唯一答案使用确定性检查。

## 23. 部署设计

### 23.1 本地 Docker Compose

服务：

```text
frontend（后续）
api
worker
postgres
redis
chromadb
prometheus
nginx
```

API 和 Worker 使用同一镜像、不同启动命令。上传文件、PostgreSQL、Chroma 和 Prometheus 使用独立持久卷。

### 23.2 启动顺序

1. PostgreSQL、Redis、Chroma 启动并通过健康检查。
2. 运行 Alembic migration。
3. API 和 Worker 启动。
4. Nginx 和可选前端启动。

### 23.3 备份

MVP 至少提供人工备份说明：

- PostgreSQL dump
- 上传文件目录
- Chroma 数据卷

PostgreSQL 与上传文件是主要恢复对象。向量索引应可以从原始文件重新构建。

## 24. EchoMind 代码迁移方案

### 24.1 可复用

| 现有文件 | 复用方式 |
|---|---|
| `api/main.py` | 拆分生命周期、健康检查和路由注册，不保留单文件业务接口 |
| `agents/agent_orchestrator.py` | 保留统计、超时、降级思想，替换 Agent 类型与工作流 |
| `core/skill_loader.py` | 保留并增加 Skill version 与 last-known-good |
| `core/llm_utils.py` | 合并到新的 LLM Gateway |
| `mcp/tool_manager.py` | 保留缓存、熔断、超时、fallback 框架 |
| `mcp/knowledge_base.py` | 重构为 VectorStore + Retriever，不沿用全局客服 collection |
| `memory/conversation_memory.py` | 保留 Redis 短期缓存，持久消息迁移到 PostgreSQL |
| `monitor/performance_monitor.py` | 保留指标和告警思想，重命名业务指标 |
| `evaluation/evaluator.py` | 重构为 RAG、出题与批改评测框架 |
| Docker/Prometheus/Nginx | 改名、增加 PostgreSQL 与 Worker |

### 24.2 必须替换

- General、Technical、Billing Agent。
- 客服意图、紧急程度和路由提示词。
- 三份客服 Skill。
- 客服知识库示例和客服评测 baseline。
- `/chat` 的客服语义请求与响应。
- `ECHOMIND_*` 配置和容器名称。
- README 中的 EchoMind 部署说明。

### 24.3 不直接复用

- 真实 `.env` 和本地 Chroma 数据。
- 原客服用户画像结构。
- 将 ChromaDB 同时作为长期业务数据库的设计。
- 依靠进程内全局对象维护权威状态的做法。

## 25. 实施顺序

### Milestone 1：工程基线

- 新建 `app/` 包和配置系统。
- 引入 PostgreSQL、SQLAlchemy、Alembic。
- 建立 User、Course、Document、Job 模型。
- 拆分健康检查和统一错误响应。
- 更新 Docker Compose。

验收：API、PostgreSQL、Redis、Chroma 能一键启动，数据库迁移成功。

### Milestone 2：资料摄取

- 文件存储接口。
- PDF、MD、TXT Parser。
- 分块与 Chroma 索引。
- Worker 和任务状态。
- 文档列表、重试、删除。

验收：上传资料后异步进入 READY，删除后不可检索。

### Milestone 3：Tutor RAG

- Retriever、Reranker、Evidence 判断。
- Citation 装配与验证。
- Tutor Agent 和多语言模式。
- Conversation/Message 持久化。

验收：一门真实课程完成带准确来源的多轮问答。

### Milestone 4：练习与批改

- PracticeSet、Question、Attempt 模型。
- Quiz Agent 结构化生成。
- Evaluator Agent 与服务端评分。
- 练习接口和历史记录。

验收：能够生成、作答、评分，并说明每项扣分依据。

### Milestone 5：个性化与质量

- TopicMastery 和推荐逻辑。
- Planner Agent。
- 自动化测试和离线 Eval。
- 监控、限流、性能和作品文档。

验收：错误会更新薄弱点，下一轮练习优先覆盖薄弱主题。

## 26. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| PDF 页码或文本提取不准确 | 引用不可验证 | 保存解析页结构；扫描件明确标记不支持 |
| LLM 编造引用 | 信任下降 | 引用 ID 白名单验证，不接受自由生成来源 |
| 题目超出课程范围 | 练习失真 | 题目必须关联 evidence；无证据不生成 |
| 批改分数漂移 | 用户不信任 | 固定 rubric、服务端算分、重复性评测 |
| 不同课程数据串联 | 严重隐私问题 | 数据库与 Chroma 双重强制过滤、专门泄漏测试 |
| 文档任务丢失或重复 | 状态异常 | 数据库 Job 权威状态、幂等、可重试 Worker |
| LLM 成本不可控 | 无法持续演示 | Token/费用指标、长度限制、缓存、小模型分层 |
| 复用客服代码形成技术债 | 维护困难 | 新 `app/` 结构垂直迁移，完成后删除旧入口 |
| 功能范围过大 | 项目难以完成 | 第一阶段只用一门课程跑通闭环 |

## 27. 开发前决策结论与默认值

为避免因非关键问题阻塞开发，采用以下默认值：

- 架构：模块化单体。
- 使用模式：本地单用户，但数据模型保留 `user_id`。
- 结构化数据库：PostgreSQL。
- 向量库：继续使用 ChromaDB。
- 缓存/队列：Redis。
- 文件：本地持久卷，接口可替换。
- 文档类型：PDF、MD、TXT。
- PDF：仅支持可提取文本的 PDF，OCR 延后。
- 回答语言默认：中文解释、英文术语。
- 练习语言默认：英文。
- 进度计划：主题优先级列表，日历延后。
- 前端：后端主链路稳定后改造现有 Vue 项目。
- 首个垂直切片：创建课程 → 上传资料 → 带引用问答。

## 28. Definition of Done

单个功能只有同时满足以下条件才算完成：

1. 符合 PRD 验收标准。
2. API Schema 和错误行为已定义。
3. 用户与课程数据隔离通过测试。
4. 关键业务逻辑有单元测试。
5. 数据库变更包含 Alembic migration。
6. Agent 输出经过结构化校验或引用验证。
7. 失败、超时和依赖不可用路径有明确行为。
8. 增加必要日志和指标，且不泄露敏感内容。
9. Docker 环境能够启动并验证该功能。
10. README 或相关设计文档已同步更新。
