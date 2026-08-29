const API = "/api/v1";
const state = { courses: [], course: null, conversationId: null, plan: null, documents: [] };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message || "操作没有完成，请稍后重试");
  }
  return body;
}

function toast(message, isError = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast show${isError ? " error" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.className = "toast", 3200);
}

function setLoading(button, loading, label = "处理中…") {
  if (!button.dataset.label) button.dataset.label = button.textContent;
  button.disabled = loading;
  button.textContent = loading ? label : button.dataset.label;
}

function formatDate(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(new Date(`${value}T00:00:00`));
}

async function loadCourses(preferredId) {
  const data = await request("/courses?size=100");
  state.courses = data.items;
  renderCourseList();
  if (!data.items.length) {
    $("#workspace").classList.add("hidden");
    $("#empty-state").classList.remove("hidden");
    return;
  }
  const saved = preferredId || localStorage.getItem("studypilot-course");
  await selectCourse(data.items.find((item) => item.id === saved) || data.items[0]);
}

function renderCourseList() {
  $("#course-list").innerHTML = state.courses.map((course) => `<button class="course-link ${state.course?.id === course.id ? "active" : ""}" data-course-id="${course.id}">${escapeHtml(course.name)}</button>`).join("");
}

async function selectCourse(course) {
  state.course = course;
  state.conversationId = null;
  localStorage.setItem("studypilot-course", course.id);
  renderCourseList();
  $("#empty-state").classList.add("hidden");
  $("#workspace").classList.remove("hidden");
  $("#page-title").textContent = "今天想学什么？";
  $("#course-name").textContent = course.name;
  $("#course-code").textContent = course.course_code || "";
  $("#semester").textContent = course.semester || course.institution || "";
  $("#course-description").textContent = course.description || "上传课程资料，开始你的个性化学习。";
  if (course.exam_date) {
    const days = Math.ceil((new Date(`${course.exam_date}T23:59:59`) - new Date()) / 86400000);
    $("#exam-days").textContent = days >= 0 ? `${days} 天` : "已结束";
    $("#exam-date").textContent = formatDate(course.exam_date);
  } else {
    $("#exam-days").textContent = "--";
    $("#exam-date").textContent = "未设置考试日期";
  }
  resetChat();
  await Promise.allSettled([loadProgress(), loadDocuments(), loadPlans(), loadConversations(), loadPracticeHistory()]);
  $(".sidebar").classList.remove("open");
}

async function loadProgress() {
  const [progress, topics, recommendations] = await Promise.all([
    request(`/courses/${state.course.id}/progress`),
    request(`/courses/${state.course.id}/topics`),
    request(`/courses/${state.course.id}/recommendations`),
  ]);
  $("#mastery").textContent = `${Math.round(progress.overall_mastery * 100)}%`;
  $("#attempts").textContent = progress.total_attempts;
  $("#weak-topics").textContent = `${progress.weak_topics} 个知识点`;
  $("#topic-list").innerHTML = topics.length ? topics.map((topic) => `<div class="topic-row"><div><strong>${escapeHtml(topic.topic)}</strong><small> · ${topic.attempt_count} 次练习</small></div><div class="progress-bar"><i style="width:${Math.round(topic.mastery_score * 100)}%"></i></div><strong>${Math.round(topic.mastery_score * 100)}%</strong><button class="mini-button danger" type="button" data-delete-topic="${escapeHtml(topic.topic)}" title="移除这个知识点">移除</button></div>`).join("") : `<div class="empty-inline">完成练习后，这里会显示你的知识点掌握情况。</div>`;
  $("#recommendations").innerHTML = recommendations.items.map((item) => `<div class="recommendation"><strong>${escapeHtml(item.topic)}</strong><small>${escapeHtml(item.reason)}<br>${escapeHtml(item.suggested_action)}</small></div>`).join("");
}

async function loadDocuments() {
  const data = await request(`/courses/${state.course.id}/documents?size=100`);
  state.documents = data.items;
  renderChatDocumentOptions();
  const labels = { lecture:"课堂讲义", reading:"阅读材料", assignment:"作业", past_exam:"往年试题", notes:"学习笔记", other:"其他" };
  $("#document-list").innerHTML = data.items.length ? data.items.map((doc) => `<div class="list-card"><div><strong>${escapeHtml(doc.filename)}</strong><p>${labels[doc.document_type] || doc.document_type} · ${(doc.size_bytes / 1024).toFixed(1)} KB${doc.chunk_count ? ` · ${doc.chunk_count} 个知识片段` : ""}</p></div><div class="history-actions"><span class="badge ${doc.status === "failed" ? "failed" : ""}">${doc.status === "ready" ? "已就绪" : doc.status === "failed" ? "处理失败" : "处理中"}</span>${doc.status === "failed" ? `<button class="mini-button" type="button" data-retry-document="${doc.id}">重试</button>` : ""}<button class="mini-button danger" type="button" data-delete-document="${doc.id}" data-filename="${escapeHtml(doc.filename)}">删除</button></div></div>`).join("") : `<div class="empty-inline">还没有课程资料。上传后，AI 教练会优先依据资料回答。</div>`;
  return data.items;
}

function renderChatDocumentOptions() {
  const select = $("#chat-document");
  const choices = $("#chat-document-choices");
  const selected = select.value;
  const documentType = $("#chat-document-type").value;
  const ready = state.documents.filter((document) => document.status === "ready" && (!documentType || document.document_type === documentType));
  const emptyLabel = documentType ? "该类型暂无可用资料" : "暂无可用资料";
  select.innerHTML = ready.length ? `<option value="">全部资料（${ready.length} 份）</option>${ready.map((document) => `<option value="${document.id}">${escapeHtml(document.filename)}</option>`).join("")}` : `<option value="">${emptyLabel}</option>`;
  select.disabled = ready.length === 0;
  if (ready.some((document) => document.id === selected)) select.value = selected;
  else select.value = "";
  choices.innerHTML = ready.length ? `<button type="button" class="document-choice" data-document-id="" role="radio">全部（${ready.length}）</button>${ready.map((document) => `<button type="button" class="document-choice" data-document-id="${document.id}" role="radio" title="${escapeHtml(document.filename)}">${escapeHtml(document.filename)}</button>`).join("")}` : `<span class="document-choice-empty">${emptyLabel}</span>`;
  updateDocumentChoiceState();
  updateScopePageLimits();
}

function updateDocumentChoiceState() {
  const selected = $("#chat-document").value;
  $$("#chat-document-choices [data-document-id]").forEach((button) => {
    const active = button.dataset.documentId === selected;
    button.classList.toggle("active", active);
    button.setAttribute("aria-checked", String(active));
  });
}

function updateScopePageLimits() {
  const selected = state.documents.find((document) => document.id === $("#chat-document").value);
  const pageCount = selected?.page_count || null;
  [$("#chat-page-from"), $("#chat-page-to")].forEach((input) => {
    if (pageCount) input.max = pageCount;
    else input.removeAttribute("max");
  });
  const documentType = $("#chat-document-type").value;
  const matching = state.documents.filter((document) => document.status === "ready" && (!documentType || document.document_type === documentType));
  $("#scope-hint").textContent = selected ? `已限定：${selected.filename}${pageCount ? `（共 ${pageCount} 页）` : ""}` : documentType ? `该类型共 ${matching.length} 份可用资料` : "默认检索当前课程的全部可用资料";
}

function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(0.1, bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function setUploadStatus(message = "", type = "") {
  const status = $("#upload-status");
  status.textContent = message;
  status.className = `upload-status${type ? ` ${type}` : ""}`;
}

function resetUploadPicker() {
  $("#document-file").value = "";
  $("#file-picker-title").textContent = "选择讲义、笔记或阅读材料";
  $("#file-picker-detail").textContent = "PDF、Markdown 或 TXT，最大 30 MB";
  const button = $("#upload-button");
  button.disabled = true;
  button.textContent = "请先选择文件";
  button.dataset.label = "上传资料";
}

async function followDocument(documentId, filename) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const document = await request(`/documents/${documentId}`);
    await loadDocuments();
    if (document.status === "ready") {
      setUploadStatus(`“${filename}”已整理完成，现在可以用它向 AI 教练提问。`, "success");
      toast("资料已就绪");
      return;
    }
    if (document.status === "failed") {
      const reason = document.error_message || "资料解析失败";
      setUploadStatus(`“${filename}”处理失败：${reason}`, "error");
      toast(reason, true);
      return;
    }
    const progress = document.job?.progress || 0;
    setUploadStatus(`“${filename}”已上传，正在整理知识内容… ${progress}%`);
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  setUploadStatus(`“${filename}”已上传，后台仍在处理。稍后刷新即可查看状态。`);
}

async function loadPlans() {
  const data = await request(`/courses/${state.course.id}/study-plans?size=20`);
  state.plan = data.items[0] || null;
  $("#plan-progress").textContent = state.plan ? `${Math.round(state.plan.completion_rate * 100)}%` : "待创建";
  $("#plan-list").innerHTML = data.items.length ? data.items.map(renderPlan).join("") : `<div class="empty-inline">设置可投入的时间，生成一份围绕薄弱知识点的学习安排。</div>`;
}

function renderPlan(plan) {
  return `<article class="plan-card"><header><div><h4>${escapeHtml(plan.title)}</h4><small>${formatDate(plan.start_date)} — ${formatDate(plan.end_date)} · 每日 ${plan.daily_minutes} 分钟</small></div><strong>${Math.round(plan.completion_rate * 100)}%</strong></header><div>${plan.tasks.map((task) => `<label class="task ${task.status === "completed" ? "done" : ""}"><input type="checkbox" data-task-id="${task.id}" ${task.status === "completed" ? "checked" : ""}><small>${formatDate(task.scheduled_date)}</small><span><strong>${escapeHtml(task.title)}</strong><small> · ${escapeHtml(task.description)}</small></span><small>${task.estimated_minutes} 分钟</small></label>`).join("")}</div></article>`;
}

function resetChat() {
  state.conversationId = null;
  const picker = document.querySelector("#conversation-select");
  if (picker) picker.value = "";
  $("#chat").innerHTML = `<div class="coach-message"><span class="bot-avatar">✦</span><div><strong>你好，我是你的学习教练。</strong><p>向我提问吧。我会优先依据你上传的课程资料回答，并标出信息来源。</p></div></div>`;
}

function inlineMarkdown(text) {
  return text
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[c(\d+)]/g, '<span class="citation-marker">[c$1]</span>');
}

function normalizeMathEscapes(content) {
  return content.replace(
    /(\$\$[\s\S]*?\$\$|\$[^$\n]+\$|\\\[[\s\S]*?\\\]|\\\([^\n]*?\\\))/g,
    (formula) => formula.replace(/\\_/g, "_"),
  );
}

function richText(content) {
  const lines = escapeHtml(normalizeMathEscapes(content)).split("\n");
  const blocks = [];
  let list = [];
  const flushList = () => {
    if (!list.length) return;
    blocks.push(`<ul>${list.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</ul>`);
    list = [];
  };
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (trimmed === "$$" || trimmed === "\\[") {
      flushList();
      const closing = trimmed === "$$" ? "$$" : "\\]";
      const formula = [];
      index += 1;
      while (index < lines.length && lines[index].trim() !== closing) {
        formula.push(lines[index]);
        index += 1;
      }
      blocks.push(`<div class="math-block">${trimmed}\n${formula.join("\n")}\n${closing}</div>`);
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    const bullet = line.match(/^\s*[-*]\s+(.+)$/);
    if (bullet) { list.push(bullet[1]); continue; }
    flushList();
    if (heading) {
      const level = Math.min(5, heading[1].length + 2);
      blocks.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
    } else if (line.trim()) blocks.push(`<p>${inlineMarkdown(line)}</p>`);
  }
  flushList();
  return blocks.join("");
}

function renderMessageMath(container) {
  if (typeof window.renderMathInElement !== "function") return;
  window.renderMathInElement(container, {
    delimiters: [
      {left: "$$", right: "$$", display: true},
      {left: "\\[", right: "\\]", display: true},
      {left: "$", right: "$", display: false},
      {left: "\\(", right: "\\)", display: false},
    ],
    throwOnError: false,
    ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code"],
  });
}

// What each degraded answer means, in the learner's terms. An answer that could
// not be generated normally should say so on its face — the reason is already in
// the API response, and reading the same as a normal answer is what misleads.
const FALLBACK_LABELS = {
  model_unconfigured: ["未配置模型", "没有可用的大模型，下面是直接从课程资料中检索到的原文。"],
  provider_request_failed: ["模型请求失败", "调用大模型时出错，下面是直接从课程资料中检索到的原文。"],
  empty_model_response: ["模型无输出", "大模型没有返回有效内容，下面是直接从课程资料中检索到的原文。"],
  citation_validation_failed: ["引用校验未通过", "大模型的回答没有给出资料引用，为避免误导已改为展示原文。"],
  citation_retry_failed: ["引用校验未通过", "大模型两次作答都没有给出资料引用，为避免误导已改为展示原文。"],
};

function fallbackNoticeHtml(reason) {
  if (!reason) return "";
  const [label, detail] = FALLBACK_LABELS[reason] || ["降级回答", "这条回答没有由大模型正常生成，展示的是可验证的课程资料原文。"];
  return `<div class="fallback-notice" title="${escapeHtml(reason)}"><span class="fallback-badge">${escapeHtml(label)}</span><span>${escapeHtml(detail)}</span></div>`;
}

// Several passages can come from one page, and the label only names the file
// and the page — so they read as duplicates. Group them into one source and
// keep every passage inside it, tagged with the marker the answer cites.
function groupCitations(citations) {
  const groups = new Map();
  citations.forEach((c) => {
    const key = `${c.document_id}#${c.page_number}`;
    if (!groups.has(key)) groups.set(key, { ...c, passages: [] });
    groups.get(key).passages.push({ id: c.citation_id, snippet: c.snippet });
  });
  return [...groups.values()];
}

function citationHtml(group) {
  const markers = group.passages.map((p) => p.id).filter(Boolean);
  const label = markers.length > 1 ? `<span class="citation-marker">${markers.map((id) => `[${id}]`).join("")}</span>` : "";
  const body = group.passages
    .map((p) => `<p>${group.passages.length > 1 && p.id ? `<span class="citation-marker">[${p.id}]</span> ` : ""}${escapeHtml(p.snippet)}</p>`)
    .join("");
  return `<details class="citation-item"><summary><a href="${API}/documents/${group.document_id}/content#page=${group.page_number}" target="_blank" rel="noopener">${escapeHtml(group.filename)} · 第 ${group.page_number} 页</a>${label}</summary>${body}${group.section_title ? `<small>章节：${escapeHtml(group.section_title)}</small>` : ""}</details>`;
}

function addMessage(role, content, citations = [], fallbackReason = null) {
  const item = document.createElement("div");
  item.className = role === "user" ? "user-message" : "coach-message";
  const citeHtml = citations.length ? `<div class="citations"><strong>可验证来源</strong>${groupCitations(citations).map(citationHtml).join("")}</div>` : "";
  item.innerHTML = role === "user" ? `<div>${escapeHtml(content)}</div>` : `<span class="bot-avatar">✦</span><div class="assistant-content">${fallbackNoticeHtml(fallbackReason)}${richText(content)}${citeHtml}</div>`;
  $("#chat").appendChild(item);
  if (role !== "user") renderMessageMath(item.querySelector(".assistant-content"));
  $("#chat").scrollTop = $("#chat").scrollHeight;
}

function answerFormHtml(question, { placeholder = "" } = {}) {
  // For a choice question the options are the answer. Asking the learner to also
  // type the letter made the radios decorative and the typing mandatory.
  // A multi-answer question needs checkboxes: radios would silently let the
  // learner pick only one of the answers the question actually has.
  const multiple = question.question_type === "multiple_choice";
  const control = multiple ? "checkbox" : "radio";
  const body = question.options
    ? `${multiple ? '<p class="choice-hint">可多选</p>' : ""}<div class="options">${question.options.map((option) => `<label><input type="${control}" name="q-${question.id}" value="${escapeHtml(option.id)}"${multiple ? "" : " required"}> ${escapeHtml(option.id)}. ${escapeHtml(option.text)}</label>`).join("")}</div>`
    : `<input required maxlength="12000" placeholder="${placeholder || "输入你的答案"}">`;
  return `<form class="answer-form ${question.options ? "choice" : ""}" data-question-id="${question.id}">${body}<button class="primary-button" type="submit">提交批改</button></form>`;
}

function practiceQuestionsHtml(practiceSet) {
  return practiceSet.questions.map((q, index) => `<article class="question-card"><h4>${index + 1}. ${escapeHtml(q.content)}</h4><small>知识点：${q.knowledge_points.map(escapeHtml).join("、")}</small>${answerFormHtml(q)}<div class="feedback hidden"></div></article>`).join("");
}

function addChatPractice(practiceSet) {
  const wrapper = document.createElement("div");
  wrapper.className = "chat-practice question-list";
  wrapper.innerHTML = practiceQuestionsHtml(practiceSet);
  $("#chat").appendChild(wrapper);
  $("#chat").scrollTop = $("#chat").scrollHeight;
}

$("#course-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-course-id]");
  if (button) selectCourse(state.courses.find((course) => course.id === button.dataset.courseId));
});
$$('[data-action="new-course"], #new-course-button').forEach((button) => button.addEventListener("click", () => openCourseDialog()));
$('[data-action="close-dialog"]').addEventListener("click", () => $("#course-dialog").close());
$("#menu-button").addEventListener("click", () => $(".sidebar").classList.toggle("open"));

$$('.tab').forEach((tab) => tab.addEventListener("click", () => {
  $$('.tab').forEach((item) => item.classList.toggle("active", item === tab));
  $$('.tab-panel').forEach((panel) => panel.classList.toggle("hidden", panel.id !== `panel-${tab.dataset.tab}`));
  if (tab.dataset.tab === "progress") Promise.allSettled([loadProgress(), loadInsights()]).catch(() => {});
  if (tab.dataset.tab === "practice") loadPracticeHistory().catch((error) => toast(error.message, true));
}));

$("#course-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  const courseId = $("#course-dialog").dataset.courseId;
  setLoading(button, true, courseId ? "正在保存…" : "正在创建…");
  try {
    const optional = (selector) => $(selector).value.trim() || null;
    const body = JSON.stringify({
      name: $("#new-name").value, course_code: optional("#new-code"),
      institution: optional("#new-institution"), semester: optional("#new-semester"),
      exam_date: optional("#new-exam-date"), target_grade: optional("#new-target"),
      description: optional("#new-description"),
    });
    const course = courseId
      ? await request(`/courses/${courseId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body })
      : await request("/courses", { method: "POST", headers: { "Content-Type": "application/json" }, body });
    $("#course-dialog").close();
    $("#course-dialog").dataset.courseId = "";
    event.target.reset();
    $("#new-institution").value = "KU Leuven";
    await loadCourses(course.id);
    toast(courseId ? "课程已更新" : "课程已创建");
  } catch (error) { toast(error.message, true); } finally { setLoading(button, false); }
});

$("#upload-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const button = event.submitter; const file = $("#document-file").files[0];
  if (!file) { setUploadStatus("请先选择一个 PDF、Markdown 或 TXT 文件。", "error"); toast("请先选择文件", true); return; }
  setLoading(button, true, "正在上传…");
  setUploadStatus(`正在上传“${file.name}”…`);
  try {
    const data = new FormData(); data.append("file", file); data.append("document_type", $("#document-type").value);
    const document = await request(`/courses/${state.course.id}/documents`, {method:"POST", body:data});
    toast("资料上传成功，开始整理内容"); await loadDocuments(); resetUploadPicker();
    await followDocument(document.id, document.filename);
  } catch (error) { setUploadStatus(`上传失败：${error.message}`, "error"); toast(error.message, true); }
  finally { if (!button.disabled) setLoading(button, false); }
});

$("#document-file").addEventListener("change", (event) => {
  const file = event.target.files[0]; const button = $("#upload-button");
  if (!file) { resetUploadPicker(); setUploadStatus(""); return; }
  const allowed = ["pdf", "md", "txt"].includes(file.name.split(".").pop().toLowerCase());
  const withinLimit = file.size <= 30 * 1024 * 1024;
  $("#file-picker-title").textContent = file.name;
  $("#file-picker-detail").textContent = `${formatFileSize(file.size)} · ${allowed && withinLimit ? "已选择，可以上传" : "文件不符合要求"}`;
  button.dataset.label = "上传资料"; button.textContent = "上传资料"; button.disabled = !(allowed && withinLimit);
  setUploadStatus(!allowed ? "仅支持 PDF、Markdown 和 TXT 文件。" : !withinLimit ? "文件大小不能超过 30 MB。" : "", allowed && withinLimit ? "" : "error");
});

$("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const button = event.submitter; const message = $("#chat-input").value.trim(); if (!message) return;
  const pageFrom = $("#chat-page-from").value ? Number($("#chat-page-from").value) : null;
  const pageTo = $("#chat-page-to").value ? Number($("#chat-page-to").value) : null;
  if (pageFrom && pageTo && pageFrom > pageTo) { toast("起始页不能大于结束页", true); return; }
  const selectedDocument = state.documents.find((document) => document.id === $("#chat-document").value);
  if (selectedDocument?.page_count && ((pageFrom && pageFrom > selectedDocument.page_count) || (pageTo && pageTo > selectedDocument.page_count))) { toast(`页码不能超过该资料的 ${selectedDocument.page_count} 页`, true); return; }
  const scope = { document_types: $("#chat-document-type").value ? [$("#chat-document-type").value] : [], document_ids: $("#chat-document").value ? [$("#chat-document").value] : [], page_from: pageFrom, page_to: pageTo };
  addMessage("user", message); $("#chat-input").value = ""; setLoading(button, true, "思考中…");
  const practiceOptions = {question_type:$("#chat-question-type").value, difficulty:$("#chat-difficulty").value, question_count:Number($("#chat-question-count").value), language:$("#chat-practice-language").value};
  try { const result = await request(`/courses/${state.course.id}/tutor/messages`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({conversation_id:state.conversationId, message, response_language:state.preferences?.explanation_language || "zh", mode:$("#answer-mode").value, scope, practice_options:practiceOptions})}); state.conversationId = result.conversation_id; addMessage("assistant", result.answer, result.citations, result.fallback_reason); if (result.practice_set) addChatPractice(result.practice_set); loadConversations().catch(() => {}); if (result.practice_set) loadPracticeHistory().catch(() => {}); } catch (error) { addMessage("assistant", `暂时无法回答：${error.message}`); } finally { setLoading(button, false); }
});

$("#chat-document-type").addEventListener("change", () => {
  renderChatDocumentOptions();
});
$("#chat-document").addEventListener("change", () => {
  $("#chat-page-from").value = "";
  $("#chat-page-to").value = "";
  updateDocumentChoiceState();
  updateScopePageLimits();
});
$("#chat-document-choices").addEventListener("click", (event) => {
  const button = event.target.closest("[data-document-id]");
  if (!button) return;
  $("#chat-document").value = button.dataset.documentId;
  $("#chat-document").dispatchEvent(new Event("change"));
});
$("#new-chat").addEventListener("click", resetChat);

$("#practice-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const button = event.submitter; setLoading(button, true, "正在出题…");
  try { const result = await request(`/courses/${state.course.id}/practice-sets`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({topic:$("#practice-topic").value.trim() || null, question_type:$("#question-type").value, difficulty:$("#difficulty").value, question_count:Number($("#question-count").value), language:$("#practice-language").value, prioritize_weak_topics:$("#weak-first").checked, scope:{}})}); $("#practice-result").innerHTML = practiceQuestionsHtml(result); toast("练习已生成"); } catch (error) { toast(error.message, true); } finally { setLoading(button, false); }
});

function selectedAnswer(form) {
  const chosen = [...form.querySelectorAll('input[type="radio"]:checked, input[type="checkbox"]:checked')];
  if (chosen.length) return chosen.map((input) => input.value).join(",");
  return form.querySelector('input:not([type="radio"]):not([type="checkbox"])')?.value ?? "";
}

document.addEventListener("submit", async (event) => {
  if (!event.target.matches(".answer-form")) return; event.preventDefault();
  if (!selectedAnswer(event.target)) { toast("请先作答", true); return; } const button = event.submitter; setLoading(button, true, "批改中…");
  try { const result = await request(`/questions/${event.target.dataset.questionId}/attempts`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({answer:selectedAnswer(event.target), include_language_feedback:Boolean(state.preferences?.include_language_feedback)})}); const feedback = event.target.nextElementSibling; feedback.classList.remove("hidden"); feedback.innerHTML = `<strong class="score">${Math.round(result.score)} / 100</strong><p>${escapeHtml(result.feedback.summary)}</p>${result.feedback.missing_concepts.length ? `<small>建议补充：${result.feedback.missing_concepts.map(escapeHtml).join("、")}</small>` : ""}`; await loadProgress(); } catch (error) { toast(error.message, true); } finally { setLoading(button, false); }
});

$("#plan-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const button = event.submitter; setLoading(button, true, "正在规划…");
  try { await request(`/courses/${state.course.id}/study-plans`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({duration_days:Number($("#duration-days").value), daily_minutes:Number($("#daily-minutes").value), include_weekends:$("#include-weekends").checked})}); await loadPlans(); toast("新的学习计划已生成"); } catch (error) { toast(error.message, true); } finally { setLoading(button, false); }
});

$("#plan-list").addEventListener("change", async (event) => {
  const input = event.target.closest("[data-task-id]"); if (!input) return; input.disabled = true;
  try { await request(`/study-tasks/${input.dataset.taskId}`, {method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({completed:input.checked})}); await loadPlans(); } catch (error) { input.checked = !input.checked; toast(error.message, true); } finally { input.disabled = false; }
});

$("#today").textContent = new Intl.DateTimeFormat("zh-CN", {month:"long", day:"numeric", weekday:"short"}).format(new Date());
loadCourses().catch((error) => { toast(`无法载入：${error.message}`, true); $("#empty-state").classList.remove("hidden"); });

/* ── Conversation history ─────────────────────────────────────────────────── */

async function loadConversations() {
  const select = $("#conversation-select");
  try {
    const data = await request(`/courses/${state.course.id}/tutor/conversations?size=20`);
    state.conversations = data.items;
    select.innerHTML = `<option value="">新对话</option>${data.items.map((item) => `<option value="${item.id}">${escapeHtml(item.title)} · ${formatDate(item.updated_at)}</option>`).join("")}`;
    select.value = state.conversationId || "";
  } catch (error) {
    select.innerHTML = `<option value="">新对话</option>`;
  }
}

async function openConversation(conversationId) {
  if (!conversationId) { resetChat(); loadConversations(); return; }
  const data = await request(`/courses/${state.course.id}/tutor/conversations/${conversationId}/messages?size=100`);
  state.conversationId = conversationId;
  $("#chat").innerHTML = "";
  // Stored messages keep the model name but not the reason, so a replayed
  // fallback is still marked — just without the specific cause.
  data.items.forEach((message) => addMessage(
    message.role === "user" ? "user" : "coach",
    message.content,
    message.citations || [],
    message.model_name === "retrieval-fallback" ? "unknown" : null,
  ));
  $("#chat").scrollTop = $("#chat").scrollHeight;
}

/* ── Practice history and retry ───────────────────────────────────────────── */

const QUESTION_TYPE_LABELS = { single_choice: "单选题", short_answer: "简答题", concept: "概念解释" };
const DIFFICULTY_LABELS = { basic: "基础", medium: "进阶", advanced: "挑战" };

async function loadPracticeHistory() {
  const container = $("#practice-history");
  const data = await request(`/courses/${state.course.id}/practice-sets?size=20`);
  state.practiceSets = data.items;
  if (!data.items.length) {
    container.innerHTML = `<div class="empty-inline">还没有练习记录。生成一组练习后，这里会保留历史和错题。</div>`;
    return;
  }
  container.innerHTML = data.items.map((item) => {
    const scored = item.average_score !== null;
    const meta = [
      `${QUESTION_TYPE_LABELS[item.question_type] || item.question_type} · ${DIFFICULTY_LABELS[item.difficulty] || item.difficulty}`,
      `${item.question_count} 题`,
      item.answered_count ? `已作答 ${item.answered_count}` : "未作答",
      item.incorrect_count ? `${item.incorrect_count} 题需加强` : "",
      formatDate(item.created_at),
    ].filter(Boolean).join(" · ");
    return `<article class="history-card" data-practice-set-id="${item.id}">
      <div><h4>${escapeHtml(item.title)}</h4><p>${escapeHtml(meta)}</p></div>
      <span class="history-score ${scored && item.average_score < 60 ? "low" : ""}">${scored ? `${Math.round(item.average_score)} 分` : "—"}</span>
      <div class="history-actions">
        <button class="mini-button" type="button" data-open-set="${item.id}">查看</button>
        ${item.incorrect_count ? `<button class="mini-button" type="button" data-retry-set="${item.id}">重练错题</button>` : ""}
      </div>
    </article>`;
  }).join("");
}

async function questionScores(questions) {
  const entries = await Promise.all(questions.map(async (question) => {
    try {
      const data = await request(`/questions/${question.id}/attempts?size=5`);
      return [question.id, data.items];
    } catch (error) {
      return [question.id, []];
    }
  }));
  return Object.fromEntries(entries);
}

function sourcesHtml(question) {
  if (!question.sources || !question.sources.length) return "";
  return `<details class="question-sources"><summary>来源（${question.sources.length}）</summary><ul>${question.sources.map((source) => `<li>${escapeHtml(source.filename)}${source.page_number ? ` · 第 ${source.page_number} 页` : ""}${source.section_title ? ` · ${escapeHtml(source.section_title)}` : ""}</li>`).join("")}</ul></details>`;
}

function rubricHtml(attempt) {
  if (!attempt || !attempt.criterion_results || !attempt.criterion_results.length) return "";
  return `<div class="rubric-list"><strong>评分要点</strong>${attempt.criterion_results.map((item) => `<div class="rubric-row ${item.earned_ratio < 1 ? "missed" : ""}"><span>${escapeHtml(item.criterion)}</span><b>${Math.round(item.points)} / ${Math.round(item.weight * 100)}</b></div>`).join("")}</div>`;
}

async function renderPracticeSet(practiceSetId, { onlyIncorrect = false } = {}) {
  const practiceSet = await request(`/practice-sets/${practiceSetId}`);
  const attempts = await questionScores(practiceSet.questions);
  const threshold = 60;
  const questions = practiceSet.questions.filter((question) => {
    if (!onlyIncorrect) return true;
    const best = (attempts[question.id] || []).reduce((max, item) => Math.max(max, item.score), -1);
    return best >= 0 && best <= threshold;
  });
  $$('.history-card').forEach((card) => card.classList.toggle("active", card.dataset.practiceSetId === practiceSetId));
  if (!questions.length) {
    $("#practice-detail").innerHTML = `<div class="empty-inline">这组练习没有需要重练的题目。</div>`;
    return;
  }
  $("#practice-detail").innerHTML = questions.map((question, index) => {
    const history = attempts[question.id] || [];
    const latest = history[0];
    const best = history.reduce((max, item) => Math.max(max, item.score), -1);
    const needsWork = best >= 0 && best <= threshold;
    return `<article class="question-card ${needsWork ? "needs-work" : ""}">
      <h4>${index + 1}. ${escapeHtml(question.content)}</h4>
      <small>知识点：${question.knowledge_points.map(escapeHtml).join("、")}${best >= 0 ? ` · 最佳得分 ${Math.round(best)}` : " · 未作答"}</small>
      ${sourcesHtml(question)}
      ${rubricHtml(latest)}
      ${answerFormHtml(question, { placeholder: best >= 0 ? "再答一次" : "输入你的答案" })}
      <div class="feedback hidden"></div>
    </article>`;
  }).join("");
  $("#practice-detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* ── Progress insights ────────────────────────────────────────────────────── */

async function loadInsights() {
  const [topics, practiceSets] = await Promise.all([
    request(`/courses/${state.course.id}/topics`),
    request(`/courses/${state.course.id}/practice-sets?size=20`),
  ]);

  const practiced = topics.filter((topic) => topic.attempt_count > 0)
    .sort((a, b) => new Date(a.last_practiced_at || 0) - new Date(b.last_practiced_at || 0))
    .slice(-12);
  $("#score-trend").innerHTML = practiced.length
    ? practiced.map((topic) => {
        const score = Math.round((topic.recent_score ?? topic.average_score ?? 0));
        return `<div class="trend-bar" title="${escapeHtml(topic.topic)}：${score} 分"><i class="${score < 60 ? "low" : ""}" style="height:${Math.max(score, 3)}%"></i><small>${score}</small></div>`;
      }).join("")
    : `<div class="empty-inline">完成练习后，这里会显示最近的得分变化。</div>`;

  const errors = {};
  topics.forEach((topic) => Object.entries(topic.common_errors || {}).forEach(([message, count]) => {
    errors[message] = (errors[message] || 0) + count;
  }));
  const ranked = Object.entries(errors).sort((a, b) => b[1] - a[1]).slice(0, 6);
  $("#common-errors").innerHTML = ranked.length
    ? ranked.map(([message, count]) => `<div class="error-row"><span>${escapeHtml(message)}</span><b>${count} 次</b></div>`).join("")
    : `<div class="empty-inline">暂无记录到的常见错误。</div>`;

  const recent = practiceSets.items.filter((item) => item.answered_count > 0).slice(0, 5);
  $("#recent-practice").innerHTML = recent.length
    ? recent.map((item) => `<div class="list-card"><div><strong>${escapeHtml(item.title)}</strong><p>${item.answered_count}/${item.question_count} 题已作答 · ${formatDate(item.created_at)}</p></div><span class="history-score ${item.average_score !== null && item.average_score < 60 ? "low" : ""}">${item.average_score !== null ? `${Math.round(item.average_score)} 分` : "—"}</span></div>`).join("")
    : `<div class="empty-inline">还没有已作答的练习。</div>`;
}

/* ── Wiring ───────────────────────────────────────────────────────────────── */

$("#conversation-select").addEventListener("change", (event) => {
  openConversation(event.target.value).catch((error) => toast(error.message, true));
});

$("#practice-history").addEventListener("click", (event) => {
  const open = event.target.closest("[data-open-set]");
  const retry = event.target.closest("[data-retry-set]");
  if (open) renderPracticeSet(open.dataset.openSet).catch((error) => toast(error.message, true));
  if (retry) renderPracticeSet(retry.dataset.retrySet, { onlyIncorrect: true }).catch((error) => toast(error.message, true));
});

$("#refresh-practice-history").addEventListener("click", () => {
  loadPracticeHistory().catch((error) => toast(error.message, true));
});

const COURSE_FIELDS = {
  name: "#new-name", course_code: "#new-code", semester: "#new-semester",
  institution: "#new-institution", exam_date: "#new-exam-date",
  target_grade: "#new-target", description: "#new-description",
};

function openCourseDialog(course = null) {
  const dialog = $("#course-dialog");
  dialog.dataset.courseId = course ? course.id : "";
  $("#course-dialog h2").textContent = course ? "编辑课程" : "添加课程";
  Object.entries(COURSE_FIELDS).forEach(([field, selector]) => {
    $(selector).value = course ? (course[field] || "") : "";
  });
  if (!course) $("#new-institution").value = "KU Leuven";
  dialog.showModal();
}

$("#edit-course").addEventListener("click", () => openCourseDialog(state.course));

$("#delete-course").addEventListener("click", async () => {
  const course = state.course;
  if (!confirm(`确定删除课程「${course.name}」吗？该课程的资料、练习、批改记录和学习计划都会一并删除，且无法恢复。`)) return;
  try {
    await request(`/courses/${course.id}`, { method: "DELETE" });
    toast("课程已删除");
    state.course = null;
    await loadCourses();
  } catch (error) {
    toast(error.message, true);
  }
});

$("#document-list").addEventListener("click", async (event) => {
  const remove = event.target.closest("[data-delete-document]");
  const retry = event.target.closest("[data-retry-document]");
  if (remove) {
    const { deleteDocument, filename } = remove.dataset;
    if (!confirm(`确定删除「${filename}」吗？该资料的知识片段会一并移除，之后的回答不再引用它。`)) return;
    try { await request(`/documents/${deleteDocument}`, { method: "DELETE" }); toast("资料已删除"); await loadDocuments(); }
    catch (error) { toast(error.message, true); }
  }
  if (retry) {
    try { await request(`/documents/${retry.dataset.retryDocument}/reprocess`, { method: "POST" }); toast("已重新提交处理"); await loadDocuments(); }
    catch (error) { toast(error.message, true); }
  }
});

$("#reset-progress").addEventListener("click", async () => {
  if (!confirm("确定清空这门课的学习进度吗？掌握度、薄弱知识点和作答统计都会被清除，且无法恢复。")) return;
  try {
    await request(`/courses/${state.course.id}/progress`, { method: "DELETE" });
    toast("学习进度已清空");
    await Promise.all([loadProgress(), loadInsights()]);
  } catch (error) {
    toast(error.message, true);
  }
});

/* ── Preferences ──────────────────────────────────────────────────────────── */

const PREFERENCE_FIELDS = {
  explanation_language: "#pref-explanation-language",
  answer_language: "#pref-answer-language",
  explanation_style: "#pref-explanation-style",
  default_question_type: "#pref-question-type",
  default_difficulty: "#pref-difficulty",
  default_question_count: "#pref-question-count",
  include_language_feedback: "#pref-language-feedback",
};

async function loadPreferences() {
  state.preferences = await request("/preferences");
  applyPreferenceDefaults();
  return state.preferences;
}

function applyPreferenceDefaults() {
  const preferences = state.preferences;
  if (!preferences) return;
  // Defaults seed the forms; a single turn can still override them.
  const set = (selector, value) => { const field = $(selector); if (field) field.value = value; };
  set("#answer-mode", preferences.explanation_style);
  set("#chat-question-type", preferences.default_question_type);
  set("#chat-difficulty", preferences.default_difficulty);
  set("#chat-question-count", preferences.default_question_count);
  set("#question-type", preferences.default_question_type);
  set("#difficulty", preferences.default_difficulty);
  set("#question-count", preferences.default_question_count);
  set("#practice-language", preferences.answer_language);
  set("#chat-practice-language", preferences.answer_language);
}

function fillPreferenceDialog() {
  const preferences = state.preferences;
  if (!preferences) return;
  Object.entries(PREFERENCE_FIELDS).forEach(([field, selector]) => {
    const input = $(selector);
    if (!input) return;
    if (input.type === "checkbox") input.checked = Boolean(preferences[field]);
    else input.value = preferences[field];
  });
}

$("#open-settings").addEventListener("click", async () => {
  try {
    if (!state.preferences) await loadPreferences();
    fillPreferenceDialog();
    $("#settings-dialog").showModal();
  } catch (error) { toast(error.message, true); }
});

$('[data-action="close-settings"]').addEventListener("click", () => $("#settings-dialog").close());

$("#settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  setLoading(button, true, "正在保存…");
  try {
    const body = {};
    Object.entries(PREFERENCE_FIELDS).forEach(([field, selector]) => {
      const input = $(selector);
      if (!input) return;
      if (input.type === "checkbox") body[field] = input.checked;
      else if (input.type === "number") body[field] = Number(input.value);
      else body[field] = input.value;
    });
    state.preferences = await request("/preferences", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    applyPreferenceDefaults();
    $("#settings-dialog").close();
    toast("偏好已保存");
  } catch (error) { toast(error.message, true); } finally { setLoading(button, false); }
});

$("#topic-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-topic]");
  if (!button) return;
  const topic = button.dataset.deleteTopic;
  if (!confirm(`确定移除知识点「${topic}」的掌握度记录吗？该知识点的得分和错误统计会被清除，且无法恢复。`)) return;
  try {
    await request(`/courses/${state.course.id}/topics/${encodeURIComponent(topic)}`, { method: "DELETE" });
    toast("知识点已移除");
    await Promise.allSettled([loadProgress(), loadInsights()]);
  } catch (error) { toast(error.message, true); }
});

loadPreferences().catch(() => {});
