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

`baselines/rag_v1.json` 当前明确标记为 `not_run`，不填写估算数据。完成 30 题真实评测后，再记录日期、模型、配置和实测指标作为基线。以后必须使用同一数据集版本比较。

PRD 的目标包括引用有效率不低于 95%、跨资料泄漏为 0、可回答题正确率不低于 90%。当前 v1 是 API 层的确定性代理指标；人工忠实度评分、检索器 Recall@K、练习题质量和判分一致性将在后续评测集补充。
