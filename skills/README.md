# StudyPilot 教学 Skills

Skill 是一段可独立维护的教学策略说明，用来补充 Agent 的行为规范。它适合放置讲解结构、命题标准、批改边界和语言处理规则——这些内容需要能被非工程人员审阅和调整，不适合硬编码在 prompt 字符串里。

## 当前 Skills

```text
skills/socratic_guidance/SKILL.md       # 苏格拉底式引导：分级提示，不直接给答案
skills/layered_explanation/SKILL.md     # 分层概念讲解：定义—展开—例子—误解—边界
skills/mathematical_notation/SKILL.md   # 数学公式讲解：LaTeX 规范与逐符号拆解
skills/exam_revision/SKILL.md           # 考试复习策略：排序原则与时间分配
skills/question_authoring/SKILL.md      # 命题规范：干扰项设计与难度分档
skills/rubric_grading/SKILL.md          # rubric 批改：不可变原则与反馈结构
skills/bilingual_terminology/SKILL.md   # 中英双语术语：对照、翻译陷阱与语言选择
```

`agents` 字段对应 `app/agents/routing.py` 中的 `AgentName`：`tutor`、`quiz`、`evaluator`、`planner`。

## 文件格式

每个 Skill 一个目录，主文件为 `SKILL.md`，开头是 YAML frontmatter：

```yaml
---
name: 显示名称
description: 一句话说明适用场景
keywords: 逗号分隔，命中任一关键词才注入；留空表示对该 Agent 始终注入
agents: 逗号分隔的 AgentName；留空表示适用于所有 Agent
enabled: true
---
```
