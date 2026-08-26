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

`datasets/quiz_generation_v1.jsonl` 包含 30 个练习生成场景，覆盖两份资料、三种题型、三档难度、1/3/5 题数量、第一章页码范围和资料外主题。运行器检查题量、题型、难度、选项格式、内容完整性、来源、资料与页码范围、主题覆盖、拒绝生成、降级和延迟。

3 条冒烟评测：

```bash
python -m tests.evals.run_quiz_eval --course-id <课程ID> --smoke
```

完整评测：

```bash
python -m tests.evals.run_quiz_eval --course-id <课程ID>
```

每个成功案例会创建标题为 `[EVAL:quiz-v1:<case-id>]` 的练习集，并把检索片段发送给已配置的大模型。当前 API 不返回参考答案和 rubric，v1 不对这两项评分；它们需要后续服务层评测，不能通过公开 API 泄露给做题者。
