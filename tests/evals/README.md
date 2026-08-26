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
