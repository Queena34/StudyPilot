# StudyPilot 迁移说明

StudyPilot 是从 EchoMind Python 版本抽取的干净开发基线，目标是构建面向国际研究生的双语 AI 学习教练。

## 已复用的基础能力

- FastAPI API 框架
- 多 Agent 编排与意图识别
- Redis 对话记忆
- ChromaDB RAG 知识库
- Skills 动态加载
- 工具缓存、超时、熔断与降级
- Prometheus 监控与端到端评测
- Docker Compose 部署配置

## 未复制的内容

- 原项目 Git 历史
- 真实 `.env` 配置和密钥
- Python 虚拟环境
- ChromaDB 本地运行数据
- 日志、缓存和 IDE 配置
- 原项目 wiki 展示文档

## 下一阶段业务迁移

1. 将客服意图替换为课程问答、学习计划、出题、批改和进度分析。
2. 将 General、Technical、Billing Agent 替换为 Tutor、Planner、Quiz、Evaluator Agent。
3. 将客服 Skills 替换为教学、出题、评分和学术诚信规则。
4. 将知识库元数据调整为用户、课程、资料类型、章节、页码和语言。
5. 增加 PDF、PPTX、DOCX 等课程资料解析。
6. 建立学习画像、薄弱知识点和复习记录数据模型。
7. 新增自动化测试和面向学习场景的评测集。

当前复制的客服业务代码仅作为重构模板，不代表 StudyPilot 的最终业务设计。
