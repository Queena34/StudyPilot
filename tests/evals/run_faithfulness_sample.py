"""Draw a stratified sample of real tutor answers for human faithfulness review.

Asks the running StudyPilot a spread of questions, captures each answer together
with the exact source snippets it cited, and writes a self-contained review page.
The page stays on disk: it quotes the learner's own course material, so it is not
something to publish anywhere.

The reviewer's judgement is the product here. Nothing in this file decides whether
an answer is faithful.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import random
import shutil
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from app.agents.presenters import CITATION_SNIPPET_LIMIT
from app.rag.chunking import TextChunker


DATASET_VERSION = "faithfulness-v2"
DEFAULT_SAMPLE_SIZE = 30

#: Bumped whenever the review page changes what a reviewer can see. It keys the
#: browser's saved progress, so judgements made against an older, less complete
#: view are never silently restored into a corrected round.
INSTRUMENT_REVISION = "rendered-3"

#: The review page shows the passage the model actually read. That holds only
#: while a citation carries the whole chunk, so the claim is checked rather than
#: asserted — if the chunker ever outgrows the citation limit, this fails loudly
#: instead of quietly handing the reviewer a fragment.
if TextChunker().max_chars > CITATION_SNIPPET_LIMIT:  # pragma: no cover - guard
    raise RuntimeError(
        "citation limit is smaller than a chunk; the review page would show fragments"
    )


def _request(url: str, *, method: str = "GET", body: dict | None = None) -> dict[str, Any]:
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(
        url, data=payload, method=method,
        headers={"Content-Type": "application/json"} if payload else {},
    )
    try:
        with urlopen(request, timeout=180) as response:  # noqa: S310 - explicit local eval URL
            return json.loads(response.read())
    except HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}: {error.read().decode('utf-8', 'replace')}") from error
    except URLError as error:
        raise RuntimeError(f"request failed for {url}: {error}") from error


def _stratified(cases: list[dict[str, Any]], size: int, seed: int) -> list[dict[str, Any]]:
    """Sample across question kinds so one easy stratum cannot carry the result."""

    if size < 1:
        raise ValueError("sample size must be positive")
    if size > len(cases):
        raise ValueError(
            f"sample size {size} exceeds the {len(cases)} available evaluation cases"
        )

    buckets: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        stratum = "no-answer" if not case["answerable"] else case["tags"][0]
        case["stratum"] = stratum
        buckets.setdefault(stratum, []).append(case)

    generator = random.Random(seed)
    for bucket in buckets.values():
        generator.shuffle(bucket)

    picked: list[dict[str, Any]] = []
    order = sorted(buckets)
    while len(picked) < size and any(buckets[name] for name in order):
        for name in order:
            if buckets[name] and len(picked) < size:
                picked.append(buckets[name].pop())
    return picked


def _document_ids(base: str, course_id: str) -> dict[str, str]:
    data = _request(f"{base}/api/v1/courses/{course_id}/documents?size=100")
    return {item["filename"]: item["id"] for item in data["items"]}


def _ask(
    base: str, course_id: str, case: dict[str, Any], documents: dict[str, str]
) -> dict[str, Any]:
    # Pin to the document the question names, exactly as the RAG runner does.
    # Left unscoped, a chapter-scoped question spans both files and retrieves
    # nothing, which would waste the reviewer's time on an artefact of sampling.
    document_id = documents.get(case.get("document", ""))
    scope = {"document_ids": [document_id]} if document_id else {}
    payload = _request(
        f"{base}/api/v1/courses/{course_id}/tutor/messages",
        method="POST",
        body={"message": case["question"], "response_language": "zh", "scope": scope},
    )
    citations = []
    for item in payload.get("citations", []):
        # The API already returns the whole chunk: its citation limit is larger
        # than the chunker's ceiling, so nothing is cut. Re-retrieving to "get
        # the full text" was worse than useless — the answer is retrieved with a
        # translated query and a section filter, so a second plain retrieval
        # returned different chunks and matched almost nothing, leaving most
        # citations wrongly labelled "preview only".
        snippet = item.get("snippet", "")
        citations.append({
            "citation_id": item["citation_id"],
            "document_id": item["document_id"],
            "filename": item["filename"],
            "page_number": item.get("page_number"),
            "section_title": item.get("section_title"),
            # Mark the boundary explicitly if a future API response reaches the
            # citation ceiling, so a reviewer never judges a truncation unknowingly.
            "text": snippet,
            "truncated": len(snippet) >= CITATION_SNIPPET_LIMIT,
        })
    return {
        "id": case["id"],
        "stratum": case["stratum"],
        "answerable": case["answerable"],
        "expected_document": case.get("document"),
        "scoped_to_document": bool(document_id),
        "question": case["question"],
        "answer": payload.get("answer", ""),
        "evidence_status": payload.get("evidence_status"),
        "citations": citations,
    }


#: The renderer is lifted from the running web app rather than reimplemented, so
#: the reviewer judges exactly what a learner sees, and the two cannot drift.
_RENDERER_FUNCTIONS = (
    "escapeHtml",
    "inlineMarkdown",
    "normalizeMathEscapes",
    "richText",
    "renderMessageMath",
)


def _renderer_source() -> str:
    source = (Path(__file__).resolve().parents[2] / "app/web/static/app.js").read_text(
        encoding="utf-8"
    )
    blocks = []
    for name in _RENDERER_FUNCTIONS:
        marker = f"function {name}("
        start = source.index(marker)
        depth, index = 0, source.index("{", start)
        opening = index
        while True:
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        blocks.append(source[start : index + 1])
    return "\n\n".join(blocks)


def _copy_katex(output: Path) -> bool:
    """KaTeX travels with the page so formulas still render offline."""

    source = Path(__file__).resolve().parents[2] / "app/web/static/vendor/katex"
    if not source.is_dir():
        return False
    target = output / "vendor" / "katex"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return True


def _review_page(sample: dict[str, Any]) -> str:
    cases = sample["cases"]
    base = sample["base_url"]
    cards = []
    for index, case in enumerate(cases, start=1):
        citations = "".join(
            f"""<details class="cite"><summary><b>[{html.escape(item['citation_id'])}]</b>
              <a href="{base}/api/v1/documents/{item['document_id']}/content#page={item.get('page_number') or 1}"
                 target="_blank" rel="noopener">{html.escape(item['filename'])}{f" · 第 {item['page_number']} 页" if item.get('page_number') else ""}</a>
              {f" · {html.escape(item['section_title'])}" if item.get('section_title') else ""}
              <span class="len">{len(item['text'])} 字符{'（仅预览）' if item.get('truncated') else ''}</span></summary>
              <p class="raw-note">下面是检索器实际交给模型的原始抽取文本。PDF 抽取会破坏数学符号
                （例如 ε 常变成 ✏、下标丢失），公式请点上方链接对照原文 PDF。</p>
              <blockquote>{html.escape(item['text'])}</blockquote></details>"""
            for item in case["citations"]
        ) or '<p class="none">这个回答没有给出任何引用。</p>'
        unanswerable = "" if case["answerable"] else '<span class="tag warn">资料外问题</span>'
        cards.append(f"""
<article class="case" data-case-id="{html.escape(case['id'])}">
  <header>
    <span class="idx">{index} / {len(cases)}</span>
    <code>{html.escape(case['id'])}</code>
    <span class="tag">{html.escape(case['stratum'])}</span>
    {unanswerable}
    <span class="tag muted">evidence: {html.escape(str(case['evidence_status']))}</span>
  </header>
  <h3>{html.escape(case['question'])}</h3>
  <div class="answer assistant-content" data-markdown="{html.escape(json.dumps(case['answer']))}"></div>
  <h4>被引用的原文</h4>
  {citations}
  <div class="verdict">
    <label>回答的每个论断都能在引用的原文中找到依据吗？
      <select data-field="grounding">
        <option value="">— 请选择 —</option>
        <option value="supported">完全有依据</option>
        <option value="partially_supported">部分有依据</option>
        <option value="unsupported">没有依据</option>
      </select></label>
    <label>引用指向的位置准确吗？
      <select data-field="citations">
        <option value="">— 请选择 —</option>
        <option value="accurate">准确</option>
        <option value="imprecise">大致相关但不精确</option>
        <option value="wrong">指错了地方</option>
      </select></label>
    <label class="check"><input type="checkbox" data-field="fabricated">
      存在资料中根本没有的内容（编造）</label>
    <label class="check"><input type="checkbox" data-field="admits_gap">
      明确说明了资料未涵盖某部分</label>
    <label class="full">备注
      <textarea data-field="note" rows="2" placeholder="判断理由，尤其是打了负面评价时"></textarea></label>
  </div>
</article>""")

    renderer = _renderer_source()
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>StudyPilot 忠实度抽检 — {sample['sampled_at'][:10]}</title>
<link rel="stylesheet" href="vendor/katex/katex.min.css">
<script src="vendor/katex/katex.min.js"></script>
<script src="vendor/katex/contrib/auto-render.min.js"></script>
<style>
 body{{margin:0;background:#f4f2eb;color:#17201b;font:15px/1.7 -apple-system,"PingFang SC",sans-serif}}
 .wrap{{max-width:900px;margin:auto;padding:32px 20px 90px}}
 h1{{font:28px Georgia,serif;margin:0 0 6px}} .lede{{color:#68736c;margin:0 0 26px}}
 .case{{margin:0 0 22px;padding:22px 24px;background:#fffefa;border:1px solid #e4e2da;border-radius:14px}}
 header{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px}}
 .idx{{font:12px Georgia,serif;color:#68736c}} code{{font-size:12px;color:#527}}
 .tag{{padding:2px 8px;border-radius:999px;background:#e8efe9;color:#3f725e;font-size:11px}}
 .tag.warn{{background:#fbe7e2;color:#a84936}} .tag.muted{{background:#eceee9;color:#68736c}}
 h3{{margin:0 0 12px;font-size:16px}}
 .answer{{padding:14px 18px;background:#edf3ee;border-radius:10px;font-size:14px;line-height:1.75}}
 .answer h3,.answer h4,.answer h5{{margin:15px 0 7px;color:#244d3e;line-height:1.35;font-size:15px}}
 .answer h3:first-child,.answer h4:first-child{{margin-top:0}}
 .answer p{{margin:0 0 9px}} .answer ul{{margin:7px 0 11px;padding-left:21px}} .answer li{{margin:3px 0}}
 .answer code{{padding:2px 5px;border-radius:4px;background:#dfe9e2;font-family:ui-monospace,Menlo,monospace;font-size:.9em}}
 .answer .math-block{{margin:10px 0;overflow-x:auto;text-align:center}}
 .answer .katex-display{{margin:13px 0;overflow-x:auto;overflow-y:hidden}}
 .citation-marker{{color:#376b57;font-size:.82em;font-weight:700;white-space:nowrap}}
 .raw-note{{margin:8px 0 0;color:#8a7a55;background:#faf6e9;padding:7px 9px;border-radius:7px;font-size:11px;line-height:1.55}}
 .cite a{{color:#315f4d}}
 h4{{margin:18px 0 8px;font-size:13px;color:#4f6a5c}}
 .cite{{margin:6px 0;padding:8px 11px;border:1px solid #d5dfd7;border-radius:9px;background:#f8fbf8;font-size:13px}}
 .cite blockquote{{margin:9px 0 2px;padding:2px 0 2px 11px;border-left:3px solid #cddbd1;color:#4f5d55;
   font-size:13px;white-space:pre-wrap;max-height:340px;overflow:auto}}
 .len{{margin-left:6px;color:#8a948e;font-size:11px}}
 .none{{color:#a84936;font-size:13px}}
 .verdict{{display:grid;gap:11px;margin-top:18px;padding-top:16px;border-top:1px dashed #cfd6d0}}
 .verdict label{{display:grid;gap:5px;font-size:13px;color:#42504a}}
 .verdict label.check{{display:flex;align-items:center;gap:8px}}
 select,textarea{{padding:8px 10px;border:1px solid #cfd3cd;border-radius:8px;font:inherit;background:white}}
 .bar{{position:fixed;left:0;right:0;bottom:0;display:flex;gap:14px;align-items:center;justify-content:center;
      padding:13px;background:#183d32;color:#f5f5ed;font-size:14px}}
 .bar button{{padding:9px 18px;border:0;border-radius:9px;background:#ffbd86;color:#3a2415;font:inherit;font-weight:650;cursor:pointer}}
 .done{{color:#7fca91}}
</style></head><body><div class="wrap">
<h1>忠实度抽检</h1>
<p class="lede">共 {len(cases)} 条，抽自 {html.escape(sample['dataset'])}，随机种子 {sample['seed']}，评审页版本 {sample['instrument']}。
判断标准只有一个：<b>回答是否忠于它引用的原文</b>。展开引用可以看到<b>完整</b>的被引用片段
（通常一两千字，需要往下滚动 —— 支撑句常常不在开头）。
进度会自动保存在本机浏览器中，填完后导出 JSON 交给评分脚本。</p>
{''.join(cards)}
</div>
<div class="bar"><span id="progress">0 / {len(cases)} 已评审</span>
<button id="export" type="button">导出评审结果</button>
<span class="done" id="saved"></span></div>
<script>
{renderer}

document.querySelectorAll("[data-markdown]").forEach((node) => {{
  node.innerHTML = richText(JSON.parse(node.dataset.markdown));
  renderMessageMath(node);
}});

const KEY = "studypilot-faithfulness-{sample['instrument']}-{sample['seed']}";
const store = JSON.parse(localStorage.getItem(KEY) || "{{}}");

function readCase(node) {{
  const verdict = {{}};
  node.querySelectorAll("[data-field]").forEach((field) => {{
    verdict[field.dataset.field] = field.type === "checkbox" ? field.checked : field.value;
  }});
  return verdict;
}}
function complete(v) {{ return Boolean(v && v.grounding && v.citations); }}
function refresh() {{
  const total = document.querySelectorAll(".case").length;
  const done = Object.values(store).filter(complete).length;
  document.getElementById("progress").textContent = done + " / " + total + " 已评审";
}}
document.querySelectorAll(".case").forEach((node) => {{
  const id = node.dataset.caseId;
  const saved = store[id];
  if (saved) node.querySelectorAll("[data-field]").forEach((field) => {{
    if (saved[field.dataset.field] === undefined) return;
    if (field.type === "checkbox") field.checked = saved[field.dataset.field];
    else field.value = saved[field.dataset.field];
  }});
  node.addEventListener("change", () => {{
    store[id] = readCase(node);
    localStorage.setItem(KEY, JSON.stringify(store));
    document.getElementById("saved").textContent = "已保存";
    setTimeout(() => document.getElementById("saved").textContent = "", 1200);
    refresh();
  }});
}});
document.getElementById("export").addEventListener("click", () => {{
  const blob = new Blob([JSON.stringify(store, null, 2)], {{type: "application/json"}});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "faithfulness_verdicts.json";
  link.click();
}});
refresh();
</script></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample tutor answers for human review.")
    parser.add_argument("--course-id", required=True)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=20260826)
    args = parser.parse_args()

    dataset = Path(__file__).parent / "datasets" / "rag_questions_v1.jsonl"
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line]
    picked = _stratified(cases, args.size, args.seed)

    documents = _document_ids(args.base_url, args.course_id)
    missing = {case.get("document") for case in picked} - set(documents) - {None}
    if missing:
        print(f"警告：课程中缺少这些资料，相关问题将不加范围提问：{', '.join(sorted(missing))}")

    collected = []
    for index, case in enumerate(picked, start=1):
        print(f"[{index}/{len(picked)}] {case['id']} ({case['stratum']})")
        collected.append(_ask(args.base_url, args.course_id, case, documents))

    sample = {
        "dataset_version": DATASET_VERSION,
        "dataset": "rag_questions_v1.jsonl",
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "course_id": args.course_id,
        "seed": args.seed,
        "base_url": args.base_url.rstrip("/"),
        "instrument": INSTRUMENT_REVISION,
        "cases": collected,
    }
    output = Path("artifacts/evals")
    output.mkdir(parents=True, exist_ok=True)
    (output / "faithfulness_sample.json").write_text(
        json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    has_katex = _copy_katex(output)
    (output / "faithfulness_review.html").write_text(_review_page(sample), encoding="utf-8")
    if not has_katex:
        print("警告：未找到 app/web/static/vendor/katex，公式将以原始 LaTeX 显示")
    print(
        f"\n抽样完成：{len(collected)} 条\n"
        "  样本：artifacts/evals/faithfulness_sample.json\n"
        "  评审页：artifacts/evals/faithfulness_review.html（本机打开，不要外发）\n"
        "填完后导出 faithfulness_verdicts.json，然后运行：\n"
        "  python -m tests.evals.run_faithfulness_eval --verdicts <导出的文件路径>"
    )


if __name__ == "__main__":
    main()
