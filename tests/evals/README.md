# StudyPilot 评测集

这里存放可复现、可版本管理的离线评测。普通单元测试检查代码是否正确；本目录的评测检查 RAG 回答是否忠于指定资料。

## RAG v1

- 数据集：`datasets/rag_questions_v1.jsonl`，固定 30 题，覆盖事实、概念、公式、章节范围和 5 个资料外问题。
- 运行器：`run_rag_eval.py`，调用本地 StudyPilot API，并固定到题目指定的文档。
- 指标：引用格式有效率、文档范围遵循率、章节范围遵循率、资料外问题识别率、关键词覆盖率、降级率和平均延迟。关键词按中英文同义词组匹配，一个概念命中任一表达即得分；数据集也可用字符串数组定义题目专用同义词组。
- 输出：`artifacts/evals/rag_latest.json` 和 `rag_latest.md`，该目录不会提交到 Git。

先启动项目，然后进行 3 题冒烟评测：

```bash
python -m tests.evals.run_rag_eval --course-id <课程ID> --limit 3
```

完整评测：

```bash
python -m tests.evals.run_rag_eval --course-id <课程ID>
```

运行器会把检索到的课程片段交给已配置的大模型。只有在确认资料允许发送给模型服务商后才运行。自动化测试不会执行这些真实 API 请求。

## 基线规则

`baselines/rag_v1.json` 保存完整 30 题真实运行的模型、日期、配置和实测指标。以后必须使用同一数据集版本和配置比较；原始回答仅保存在忽略提交的本地 artifacts 中。

PRD 的目标包括引用有效率不低于 95%、跨资料泄漏为 0、可回答题正确率不低于 90%。当前 v1 是 API 层的确定性代理指标；人工忠实度评分、检索器 Recall@K、练习题质量和判分一致性将在后续评测集补充。

## Quiz v1

`datasets/quiz_generation_v1.jsonl` 包含 30 个练习生成场景，覆盖两份资料、三种题型、三档难度、1/3/5 题数量、第一章页码范围和资料外主题。运行器检查题量、题型、难度、选项格式、内容完整性、来源、资料与页码范围、主题锚点覆盖、拒绝生成、降级和延迟。主题锚点只要求题面、知识点或选择题选项体现所选主题，不要求问答题在题面中泄露参考答案。

3 条冒烟评测：

```bash
python -m tests.evals.run_quiz_eval --course-id <课程ID> --smoke
```

完整评测：

```bash
python -m tests.evals.run_quiz_eval --course-id <课程ID>
```

每个成功案例会创建标题为 `[EVAL:quiz-v1:<case-id>]` 的练习集，并把检索片段发送给已配置的大模型。当前 API 不返回参考答案和 rubric，v1 不对这两项评分；它们需要后续服务层评测，不能通过公开 API 泄露给做题者。

`baselines/quiz_v1.json` 保存完整 30 场景实测结果。正常主题会先经过中英查询扩展和资料支持性判断；只有连续两次明确判定不支持才拒绝生成。后续比较必须保持相同数据集版本和支持性策略。

## Grading v1

`datasets/grading_answers_v1.jsonl` 固定 10 道题，每题包含正确、部分正确和错误三档答案，以及不可变 rubric 和资料证据。运行器默认对每档答案重复批改 3 次，共 90 次模型调用，评估分数区间、三档排序、10 分以内重复稳定性、rubric 完整性、证据有效性、反馈完整性、fallback 和延迟。

先运行 1 道题、每档 1 次的冒烟评测：

```bash
python -m tests.evals.run_grading_eval --limit 1 --repeats 1
```

完整基线：

```bash
python -m tests.evals.run_grading_eval --repeats 3
```

该运行器直接评测 Evaluator Gateway，不创建 Attempt、不更新学习进度，也不污染课程数据库。原始批改反馈保存在忽略提交的 `artifacts/evals/grading_latest.json`。

### 完整基线（90 次）

`baselines/grading_v1.json` 已记录 10 题 × 三档 × 3 次重复的完整基线，模型 `deepseek-v4-flash`，总耗时约 3 分 37 秒：

| 指标 | 结果 |
|---|---:|
| run_success_rate | 100% |
| ordering_accuracy | 100% |
| repeatability_within_10_points | 100% |
| criterion_completeness / evidence_validity / feedback_completeness | 100% |
| fallback_rate | 0% |
| **score_band_accuracy** | **90%** |
| average_latency_ms | 2394 |

90% 的成因已完整诊断。9 次越界全部集中在 `grade-003/004/005` 的 partial 档，三次重复精确一致（均为 25.0），因此是确定性行为而非模型抖动。这三题都是 2 条 rubric、各 0.5 权重，partial 答案各自完整覆盖其中一条，理论应得 50。

受控实验（去掉答案中"但我没有说明…"这类元评论后重新批改）区分出两个原因：

- `grade-003` 由 25 升至 50 —— **数据集人为杂质**。真实学生不会在答案里自述缺了什么，这句话把已覆盖条目的得分也拉了下去。
- `grade-004`、`grade-005` 去杂后仍为 25 —— **批改器偏保守**，对答案明确表述但措辞简短的 rubric 条目只给 0.5。例如 `grade-005` 的答案"误差项是不可直接观测的"与 rubric 条目"说明误差不可直接观测"直接对应，仍只得 0.5。

基线**如实记录当前行为，未通过修改数据集抬高数值**。排序一致性和重复稳定性满分说明批改稳定且可预期；偏差是绝对分数偏低而非判断混乱，对学习者的影响是被低估而非被误导。元评论杂质将在 `grading-v2` 中移除；保守倾向记为 K-17，三个样本不足以支撑放宽评分标准。

六条合入门槛见基线文件，其中 `ordering_accuracy` 必须为 1.0 —— 正确高于部分正确、部分正确高于错误，这是批改可用性的底线。

## Router v1 / v2

`datasets/router_intents_v1.jsonl` 包含 45 条路由用例，覆盖路线图要求的四类场景：单意图（23）、模糊意图（8）、复合意图（6）、上下文追问（5），另加 3 条显式范围保持用例。

与其他评测不同，路由没有检索和数据库依赖，运行器在进程内直接调用 `LearningIntentRouter`，不需要启动 API。

规则层基线（确定性、零成本，可在 CI 中运行）：

```bash
python -m tests.evals.run_router_eval --rules-only
```

完整混合评测（模糊、复合和追问用例会调用已配置的大模型）：

```bash
python -m tests.evals.run_router_eval
```

指标含义：

- `intent_accuracy` 只在“应当给出确定意图”的用例上计算，需要澄清的用例不计入，避免把正确的澄清判为错误。
- `rule_resolution_rate` 和 `llm_invocation_rate` 用于监控“规则优先”是否仍然成立。若 LLM 调用率持续上升，说明规则层退化或数据集变难。
- `scope_preservation_rate` 是硬性约束，必须恒为 100%：任何路由路径都不得修改学习者显式选择的课程、资料、类型和页码范围。
- `composite_supporting_accuracy` 衡量复合意图的辅助 Agent 识别，当前偏低是已知项，需要在编排层落地后一并改进。

`baselines/router_v1.json` 在同一份数据集下并列保存**两种模式**的基线：

- `modes.rules_only`：不调用任何模型，结果完全可复现，是可进 CI 的回归防线。实测意图准确率 70.0%、规则解决率 55.6%、范围保持 100%。
- `modes.hybrid`：完整混合路由的真实能力基线。实测意图准确率 92.5%、执行模式准确率 93.3%、范围保持 100%、LLM 调用率 44.4%、平均延迟 569ms，并逐条记录了 3 条误判用例及其判断说明。

文件中的 `regression_rules` 是这套基线的合入门槛，其中两条是硬性的：`scope_preservation_rate` 必须恒为 1.0；`rules_only` 除 `average_latency_ms` 外的全部指标必须逐位复现。后续比较必须使用相同 `dataset_version` 和相同 `configuration` 阈值。

### Router v2

`datasets/router_intents_v2.jsonl` 在 v1 的 45 条基础上增加 12 条，共 57 条，覆盖新增的 `answer_evaluation` 意图：6 条答案提交、2 条**误判防护**（提到"参考答案""标准答案"但实为提问，不得被当成交卷）、2 条 `Evaluator→Planner` 复合、2 条计划生成。

v2 是默认数据集。v1 保留用于历史对比：

```bash
python -m tests.evals.run_router_eval --rules-only --dataset-version router-v1
```

`baselines/router_v2.json` 实测：rules-only 意图准确率 73.1%、规则解决率 63.2%；hybrid 意图准确率 90.4%、执行模式准确率 94.7%、复合辅助 Agent 准确率 66.7%（v1 为 57.1%）、范围保持 100%。5 条误判用例逐条记录了判断说明。

新增答案提交规则后，**v1 的全部指标仍逐位复现**，说明该规则没有在既有用例上产生误判。

## Integrity v1

`datasets/integrity_requests_v1.jsonl` 包含 61 条学术诚信判定用例，检查 `app/agents/integrity.py` 的四级 Guard。

**数据集刻意向假阳性倾斜。** 61 条中 36 条是正当学习请求：8 条普通提问，24 条刻意包含「作业」「考试」「论文」「答案」等敏感措辞（例如"下周要考试了，帮我制定复习计划""参考答案里为什么要先做中心化"），4 条是"我做完了帮我检查"这类自有成果复核。另有 4 条 `review_exemption_abuse` 用例，验证复核豁免不能被反过来用于让助手代做作业。

这样加权的理由是**两类错误代价不对称**：拒绝帮助一个正当提问的学生，直接损害产品的核心用途；漏判一次作弊则不然。因此指标把两个方向分开报告，不合并成单一准确率。

Guard 完全确定性、不调用任何模型，所以这套评测免费、秒级、可逐位复现：

```bash
python -m tests.evals.run_integrity_eval
```

关键指标：

- `false_positive_rate`：正当学习请求被限制的比例。**必须为 0**，这是本评测集存在的首要理由。
- `blocking_precision`：短路整轮的判定中确为实时考试的比例。**必须为 1.0**，只有实时考试允许拒答。
- `help_retention_rate`：非阻断的轮次仍然提供了帮助的比例。PRD 8.7 要求提示不能替代帮助本身。
- `notice_brevity_rate`：提示不超过 120 字符的比例。
- `false_negative_rate` 与 `wrong_severity_rate`：漏判和判错档位，代价低于假阳性但仍需跟踪。

`baselines/integrity_v1.json` 实测全部指标为满分（level_accuracy 100%、false_positive_rate 0%），并写明了七条合入门槛。建立该评测集时抓到一个真实缺陷：「我作业做完了，帮我检查思路对不对」被判为 `hint_only`，即学生做完作业请人复核反而被限制，已通过新增自有成果复核豁免修复。

## Orchestrator v1

`datasets/orchestrator_flows_v1.jsonl` 包含 30 条编排流程用例，直接对应路线图第 9 节对编排层的四项要求：

| 要求 | 用例数 |
|---|---:|
| Agent 选择 | 9 |
| 执行顺序 | 4 |
| 上下文传递 | 3 |
| 失败降级 | 7 |
| 澄清 / 学术诚信 / Trace | 7 |

Agent 被替换为**脚本化替身**，所以这套评测只考察编排本身 —— 选谁、按什么顺序、上下文是否传到、失败时保住了什么。不调用模型也不碰数据库，因此免费、秒级、逐位可复现。

```bash
python -m tests.evals.run_orchestrator_eval
```

指标分开报告而不合并，因为一个"选对了 Agent 但在辅助步骤失败时丢了答案"的编排层不是部分正确，而是在最要紧的地方坏了。`answer_preservation_rate`、`isolation_rate`、`context_passing_accuracy`、`failure_containment` 四项在 `baselines/orchestrator_v1.json` 中都是硬性门槛，必须为 100%。

## Loop v1（端到端闭环）

`run_loop_eval.py` 是唯一打真实 API 的编排类评测。它按学习者的实际路径走完五个阶段，每一步对照**真实状态**校验后置条件，而不是对照 mock：

```text
1-explain   讲解 → 有引用、引用可解析、证据充分、诚信判定为允许
2-practice  出题 → 练习集真实创建、题量符合、每题有来源、路由经过 quiz
3-grade     批改 → 路由经过 evaluator、grade_answer 工具真实调用、报出得分
4-mastery   掌握度 → 作答数确实增加、主题记录存在
5-plan      计划 → 路由经过 planner、create_study_plan 真实调用、计划已持久化
```

```bash
python -m tests.evals.run_loop_eval --course-id <课程ID>
```

需要运行中的 StudyPilot、已配置模型密钥，以及一门已完成资料入库的课程。**会在该课程下创建真实的练习集、作答记录和学习计划**，不要对演示课程之外的数据运行。

`baselines/loop_v1.json` 实测五阶段全部通过、`loop_closed: true`、总延迟约 22.5 秒。其中四条门槛是硬性的：讲解必须带可解析引用；`grade_answer` 工具必须真实调用（不能只是模型在对话里说了句评价）；作答必须落到掌握度（否则闭环只是表面成立）；计划必须真实创建并持久化。本评测调用真实模型，延迟仅供参考，不作为回归门槛。

## Faithfulness v1（人工抽检）

其余七套评测衡量的都是机器可判定的**代理指标** —— 引用能否解析、是否落在指定文档内、关键词是否出现。没有一项能回答产品真正立足的那个问题：**这个回答对它引用的原文忠实吗**。该判断只能由人做出，这套流程就是为此准备的。

### 三步

```bash
# 1. 抽样：真实提问，抓回答案与被引用的原文片段
python -m tests.evals.run_faithfulness_sample --course-id <课程ID> --size 12

# 2. 评审：本机浏览器打开，逐条判断，填完后导出 JSON
open artifacts/evals/faithfulness_review.html

# 3. 评分
python -m tests.evals.run_faithfulness_eval --verdicts faithfulness_verdicts.json --reviewer <姓名>
```

评审页**只留在本机**：它逐字引用了学习者自己的课程资料，不要上传或外发。进度自动存在浏览器 localStorage 中，可以分几次填完。

### 抽样方式

按问题类型分层抽样（概念、公式、方法、示例、解释、资料外问题等），保证一个容易的层不能独自撑起结果。随机种子固定，同一种子可复现同一批样本。每题固定到数据集指定的资料——与 RAG 运行器一致；不加范围时"根据资料第一章"这类问题会跨两份资料检索失败，那样只会浪费评审者的时间。

### 四项判断

| 判断 | 取值 |
|---|---|
| 依据 | 完全有依据 / 部分有依据 / 没有依据 |
| 引用准确性 | 准确 / 大致相关但不精确 / 指错了地方 |
| 是否编造 | 是 / 否 |
| 是否说明资料未涵盖 | 是 / 否 |

### 门槛

`baselines/faithfulness_v1.json` 写明五条，其中两条是硬性的：

- **`fabrication_rate` 必须为 0** —— 编造内容直接摧毁「答案锚定在你自己的资料上」这一产品前提。
- **`declined_when_unsupported_rate` 必须为 1.0** —— 资料外问题必须被明确指出，不得作答。

评分脚本会**拒绝给未填完的评审表打分**：半份评审报出的满分比没有评审更有害。基线中同时记录评审者姓名与随机种子，更换任一项后不得与旧结果直接比较。
