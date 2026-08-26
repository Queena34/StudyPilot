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
  await Promise.allSettled([loadProgress(), loadDocuments(), loadPlans()]);
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
  $("#topic-list").innerHTML = topics.length ? topics.map((topic) => `<div class="topic-row"><div><strong>${escapeHtml(topic.topic)}</strong><small> · ${topic.attempt_count} 次练习</small></div><div class="progress-bar"><i style="width:${Math.round(topic.mastery_score * 100)}%"></i></div><strong>${Math.round(topic.mastery_score * 100)}%</strong></div>`).join("") : `<div class="empty-inline">完成练习后，这里会显示你的知识点掌握情况。</div>`;
  $("#recommendations").innerHTML = recommendations.items.map((item) => `<div class="recommendation"><strong>${escapeHtml(item.topic)}</strong><small>${escapeHtml(item.reason)}<br>${escapeHtml(item.suggested_action)}</small></div>`).join("");
}

async function loadDocuments() {
  const data = await request(`/courses/${state.course.id}/documents?size=100`);
  state.documents = data.items;
  renderChatDocumentOptions();
  const labels = { lecture:"课堂讲义", reading:"阅读材料", assignment:"作业", past_exam:"往年试题", notes:"学习笔记", other:"其他" };
  $("#document-list").innerHTML = data.items.length ? data.items.map((doc) => `<div class="list-card"><div><strong>${escapeHtml(doc.filename)}</strong><p>${labels[doc.document_type] || doc.document_type} · ${(doc.size_bytes / 1024).toFixed(1)} KB${doc.chunk_count ? ` · ${doc.chunk_count} 个知识片段` : ""}</p></div><span class="badge ${doc.status === "failed" ? "failed" : ""}">${doc.status === "ready" ? "已就绪" : doc.status === "failed" ? "处理失败" : "处理中"}</span></div>`).join("") : `<div class="empty-inline">还没有课程资料。上传后，AI 教练会优先依据资料回答。</div>`;
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
  $("#chat").innerHTML = `<div class="coach-message"><span class="bot-avatar">✦</span><div><strong>你好，我是你的学习教练。</strong><p>向我提问吧。我会优先依据你上传的课程资料回答，并标出信息来源。</p></div></div>`;
}

function inlineMarkdown(text) {
  return text
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[c(\d+)]/g, '<span class="citation-marker">[c$1]</span>');
}

function richText(content) {
  const lines = escapeHtml(content).split("\n");
  const blocks = [];
  let list = [];
  const flushList = () => {
    if (!list.length) return;
    blocks.push(`<ul>${list.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</ul>`);
    list = [];
  };
  for (const line of lines) {
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
  });
}

function addMessage(role, content, citations = []) {
  const item = document.createElement("div");
  item.className = role === "user" ? "user-message" : "coach-message";
  const citeHtml = citations.length ? `<div class="citations"><strong>可验证来源</strong>${citations.map((c) => `<details class="citation-item"><summary><a href="${API}/documents/${c.document_id}/content#page=${c.page_number}" target="_blank" rel="noopener">${escapeHtml(c.filename)} · 第 ${c.page_number} 页</a></summary><p>${escapeHtml(c.snippet)}</p>${c.section_title ? `<small>章节：${escapeHtml(c.section_title)}</small>` : ""}</details>`).join("")}</div>` : "";
  item.innerHTML = role === "user" ? `<div>${escapeHtml(content)}</div>` : `<span class="bot-avatar">✦</span><div class="assistant-content">${richText(content)}${citeHtml}</div>`;
  $("#chat").appendChild(item);
  if (role !== "user") renderMessageMath(item.querySelector(".assistant-content"));
  $("#chat").scrollTop = $("#chat").scrollHeight;
}

function practiceQuestionsHtml(practiceSet) {
  return practiceSet.questions.map((q, index) => `<article class="question-card"><h4>${index + 1}. ${escapeHtml(q.content)}</h4>${q.options ? `<div class="options">${q.options.map((o) => `<label><input type="radio" name="q-${q.id}" value="${escapeHtml(o.id)}"> ${escapeHtml(o.id)}. ${escapeHtml(o.text)}</label>`).join("")}</div>` : ""}<small>知识点：${q.knowledge_points.map(escapeHtml).join("、")}</small><form class="answer-form" data-question-id="${q.id}"><input required maxlength="12000" placeholder="输入你的答案${q.options ? "（如 A）" : ""}"><button class="primary-button" type="submit">提交批改</button></form><div class="feedback hidden"></div></article>`).join("");
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
$$('[data-action="new-course"], #new-course-button').forEach((button) => button.addEventListener("click", () => $("#course-dialog").showModal()));
$('[data-action="close-dialog"]').addEventListener("click", () => $("#course-dialog").close());
$("#menu-button").addEventListener("click", () => $(".sidebar").classList.toggle("open"));

$$('.tab').forEach((tab) => tab.addEventListener("click", () => {
  $$('.tab').forEach((item) => item.classList.toggle("active", item === tab));
  $$('.tab-panel').forEach((panel) => panel.classList.toggle("hidden", panel.id !== `panel-${tab.dataset.tab}`));
  if (tab.dataset.tab === "progress") loadProgress().catch((error) => toast(error.message, true));
}));

$("#course-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const button = event.submitter; setLoading(button, true, "正在创建…");
  try {
    const optional = (selector) => $(selector).value.trim() || null;
    const course = await request("/courses", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ name:$("#new-name").value, course_code:optional("#new-code"), institution:optional("#new-institution"), semester:optional("#new-semester"), exam_date:optional("#new-exam-date"), target_grade:optional("#new-target"), description:optional("#new-description") }) });
    $("#course-dialog").close(); event.target.reset(); $("#new-institution").value = "KU Leuven"; await loadCourses(course.id); toast("课程已创建");
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
  try { const result = await request(`/courses/${state.course.id}/tutor/messages`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({conversation_id:state.conversationId, message, response_language:"zh", mode:$("#answer-mode").value, scope})}); state.conversationId = result.conversation_id; addMessage("assistant", result.answer, result.citations); if (result.practice_set) addChatPractice(result.practice_set); } catch (error) { addMessage("assistant", `暂时无法回答：${error.message}`); } finally { setLoading(button, false); }
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
  try { const result = await request(`/courses/${state.course.id}/practice-sets`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({topic:$("#practice-topic").value.trim() || null, question_type:$("#question-type").value, difficulty:$("#difficulty").value, question_count:Number($("#question-count").value), language:"zh", prioritize_weak_topics:$("#weak-first").checked, scope:{}})}); $("#practice-result").innerHTML = practiceQuestionsHtml(result); toast("练习已生成"); } catch (error) { toast(error.message, true); } finally { setLoading(button, false); }
});

document.addEventListener("submit", async (event) => {
  if (!event.target.matches(".answer-form")) return; event.preventDefault(); const button = event.submitter; setLoading(button, true, "批改中…");
  try { const result = await request(`/questions/${event.target.dataset.questionId}/attempts`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({answer:event.target.querySelector("input").value})}); const feedback = event.target.nextElementSibling; feedback.classList.remove("hidden"); feedback.innerHTML = `<strong class="score">${Math.round(result.score)} / 100</strong><p>${escapeHtml(result.feedback.summary)}</p>${result.feedback.missing_concepts.length ? `<small>建议补充：${result.feedback.missing_concepts.map(escapeHtml).join("、")}</small>` : ""}`; await loadProgress(); } catch (error) { toast(error.message, true); } finally { setLoading(button, false); }
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
