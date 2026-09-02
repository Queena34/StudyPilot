# StudyPilot

A bilingual AI study coach for international graduate students. Upload your course
material and StudyPilot explains concepts with citations, writes practice questions
it can grade, marks them against a rubric criterion by criterion, and schedules
revision from what you actually got wrong — all from that material alone.

**The core constraint: it never fills a gap with general knowledge.** If the material
does not cover something, it says so rather than answering from memory.

[中文](README.md)

Positioning, user scenarios, core flows, scope boundaries and acceptance criteria: [Product requirements (PRD, in Chinese)](docs/PRD.md).

---

## Screens

**Grounded explanations** — mathematics renders as LaTeX, inline `[c1]` markers point
at the sources below, and sources are grouped by page, expand to the passage the
model actually read, and link into the PDF at that page.

![Grounded explanations](docs/screenshots/01-chat-citations.png)

**Practice and grading** — single choice, multiple answers, short answer and concept
questions. Multi-answer questions earn `(hits − misses) / answers`, floored at zero.

![Practice and grading](docs/screenshots/02-practice-grading.png)

**Progress** — mastery, score trend and recurring mistakes, aggregated from every attempt.

![Progress](docs/screenshots/03-progress.png)

**Study plan** — daily tasks generated from weak topics and the exam date.

![Study plan](docs/screenshots/04-plan.png)

---

## Quick start

```bash
cp .env.example .env        # add your model key
docker compose up -d --build
```

- Workspace: <http://localhost:8000/>
- API docs: <http://localhost:8000/docs>

Upload, parsing, retrieval and citation work without a model key — you get verifiable
retrieval results instead of generated prose. With a key configured you get full
explanations carrying `[c1]` citations:

```env
STUDYPILOT_ANTHROPIC_API_KEY=your_api_key
STUDYPILOT_ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

---

## What it does

**Material**
- Create a course, set the exam date, upload PDF / Markdown / TXT.
- A background worker parses, chunks, embeds and indexes asynchronously, with visible progress.
- **It detects how each document divides itself.** Numbered chapters (`Chapter 3.` / `第三章`),
  slide handouts split by their title pages, and Markdown headings each get their own
  detector; when none applies the document is stated to have no structure rather than
  being given an invented one. A document that numbers its own chapters keeps those
  numbers — a textbook opening on `Chapter 0` still answers "chapter one" with `Chapter 1`.

**Asking**
- Retrieval is scoped by course, material type, named documents, page range and section,
  and understands references like "the first document" or "the second PDF".
- Every answer cites filename and page; a citation expands to the passage and links into the PDF.
- Ask in Chinese about English material: the question is translated into the material's
  language before retrieval, and the answer comes back in Chinese, English or both.

**Practice and grading**
- Questions carry their sources and a rubric. Question language is set separately from
  explanation language — students are often taught in one language and examined in another.
- Grading follows an immutable rubric and returns per-criterion scores, what was missed
  and what to do next. Choice questions are graded deterministically, without a model.
- Practice history, retry of missed questions, rubric and source display.

**Study management**
- Attempts aggregate into mastery levels and weak topics, which drive the study plan.
- Language and teaching-style preferences; individual weak topics can be inspected and removed.

**Academic integrity**
- Four deterministic levels. Ghost-writing an assignment and live-exam cheating get no
  answers, while legitimate study help continues — what is refused is doing the work,
  not learning from it.

---

## Architecture

```text
Single chat entry point
  ↓
Hybrid LearningIntentRouter        Rules first; the LLM is called only for low-confidence,
  ↓  RoutingDecision + QueryPlan   ambiguous and composite requests
Academic integrity guard           Four levels, before any agent runs
  ↓
LearningAgentOrchestrator          Dispatches by execution_mode, passes context when sequential
  ├─ TutorAgent      course Q&A and explanation
  ├─ QuizAgent       question generation
  ├─ EvaluatorAgent  rubric grading
  ├─ PlannerAgent    study plan reading and generation
  └─ Progress / Catalog / General
  ↓
TeachingToolManager                9 teaching tools; course ownership and document scope
  ↓                                are validated in one place
AgentResult + AgentTrace
```

Three constraints run through the whole system:

- **A scope the learner chose explicitly is never overridden by a model.** Course,
  documents, type, pages and section never enter the model's input, and the tool layer
  verifies the documents really belong to that course — anything else returns 403.
- **Scope is parsed once.** Intent and scope become a structured `QueryPlan` in the
  router; every agent and service downstream consumes those fields rather than
  re-reading the message. Otherwise one phrase like "chapter one" gets three
  different readings in three different places.
- **Rules first.** The most common unambiguous requests are resolved by deterministic
  rules at zero latency; measured over the routing suite, the LLM is called on about 40% of cases.

**Retrieval**: `BAAI/bge-small-en-v1.5` embeddings (384-dim, ONNX inference, baked into
the image so nothing is downloaded at runtime), 1200/200 chunking, fused scoring
`0.7 × vector + 0.3 × lexical`. Cross-lingual retrieval does not rely on multilingual
embeddings — the question is translated into the material's language first. That costs
one small model call and buys a smaller, sharper English retrieval model; it also means
a bad translation is visible, whereas an embedding that fails to align is a black box.

**Stack**: FastAPI + PostgreSQL + ChromaDB + Redis + Docker. Entry point `app.main:app`,
all routes under `/api/v1`; the front end is a vanilla HTML/CSS/JS workspace served by FastAPI.

---

## Testing and evaluation

Unit tests check that the code is correct. The offline evaluations under `tests/evals/`
check that **model behaviour stays faithful to the material** — the part of an LLM
application that actually breaks and that unit tests cannot see.

```bash
docker compose exec api python -m pytest tests/unit -q
```

Eleven versioned suites, each with a recorded baseline and an explicit merge gate. See
[tests/evals/README.md](tests/evals/README.md):

| Suite | Size | Baseline | Needs a model |
|---|---|---|---|
| Router v2 | 57 cases | 98.1% agent, 100% composite-step detection, 100% clarification, 100% scope preservation (86.5% intent; nearly all of the gap is same-agent label overlap) | partly |
| Integrity v1 | 61 cases | every metric perfect, 0% false positives | no |
| Orchestrator v1 | 30 cases | every metric 100% | no |
| Loop v1 | 5 stages | loop closes, 22.5s end to end | yes |
| RAG v1 | 30 questions | 100% citation validity, 100% scope adherence, 98% keyword coverage | yes |
| Quiz v1 | 30 scenarios | 96.7% generation success, 100% topic coverage | yes |
| Grading v1 | 10 × 3 bands × 3 runs | every metric 100% | yes |
| Faithfulness v2 | 30 human-reviewed | grounding and citation accuracy 100%, fabrication 0%, unsupported-query refusal 100% | human |
| Cross-lingual v1 | 14 questions × 2 languages | 100% parity, no unsupported citations | yes |
| Injection v1 | 10 attack classes | 100% resistance, 0% canary leakage | yes |
| Paraphrase v1 | 11 groups, 41 cases | 100% group consistency, 100% intent accuracy | partly |

Three suites call no model at all — free, seconds long, reproducible bit for bit, and
suitable for CI:

```bash
docker compose exec api python -m tests.evals.run_router_eval --rules-only
docker compose exec api python -m tests.evals.run_integrity_eval
docker compose exec api python -m tests.evals.run_orchestrator_eval
```

Baselines **record what the system actually does; no dataset was edited to make a number
look better**. The metrics themselves have been corrected more than once — the injection
suite once scored "the model named the attack and refused to follow it" as a failure, and
a detector that punishes correct behaviour is worse than no detector. Those corrections
are written down in `tests/evals/README.md`.

---

## Out of scope

StudyPilot answers only what the learner's own uploaded material covers. **Mental-health
crises and emotional support, professional medical, legal or financial advice, and factual
questions outside the material are out of scope, and the system does not attempt to detect
them.** Those situations need trained people and human escalation, which this project does
not have — so it declines the role rather than shipping an unreliable version of it.
