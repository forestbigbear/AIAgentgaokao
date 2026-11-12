(function () {
  const pages = [
    ["overview", "总览", "index.html"],
    ["student", "考生信息", "pages/student.html"],
    ["universities", "院校专业", "pages/universities.html"],
    ["recommendation", "智能推荐", "pages/recommendation.html"],
    ["agents", "Agent 工作流", "pages/agents.html"],
    ["knowledge", "政策知识库", "pages/knowledge.html"],
    ["models", "模型连接", "pages/models.html"],
    ["history", "历史方案", "pages/history.html"],
  ];
  const root = location.pathname.includes("/pages/") ? "../" : "";
  const page = document.body.dataset.page;
  const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[char]);
  const qs = (params) => new URLSearchParams(Object.entries(params).filter(([, value]) => value !== "" && value !== null && value !== undefined)).toString();

  async function api(path, options = {}) {
    let response;
    try { response = await fetch("/api/v1" + path, options); }
    catch { throw new Error("无法连接后端服务，请检查服务状态后重试。"); }
    let body;
    try { body = await response.json(); } catch { throw new Error("服务响应无法解析"); }
    if (!response.ok || body.code !== "OK") {
      const fields = body.meta?.fields?.map((item) => item.field + "：" + item.message).join("；");
      const descriptions = {
        EMBEDDING_NOT_CONFIGURED: "尚未配置 Embedding 服务，文档可以上传，但暂不能检索或问答。",
        LLM_NOT_CONFIGURED: "尚未配置问答模型，请先查看检索结果。",
        MODEL_API_ERROR: "模型服务暂时不可用，请检查配置后重试。",
        EMBEDDING_INDEX_EXISTS: "已有知识库向量。更换 Embedding 服务或模型前，请先删除已索引文档；更换后重新上传并建立索引。",
        DATABASE_ERROR: "数据库暂时不可用，请稍后重试。",
      };
      const error = new Error(descriptions[body.code] || fields || body.message || "请求失败");
      error.code = body.code;
      error.status = response.status;
      throw error;
    }
    return body;
  }
  const json = (path, method, data) => api(path, {method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
  const activeStudent = () => Number(localStorage.getItem("gaokao_student_id")) || null;
  function setActiveStudent(id) {
    if (id) localStorage.setItem("gaokao_student_id", String(id));
    else localStorage.removeItem("gaokao_student_id");
    document.dispatchEvent(new CustomEvent("studentchange", {detail: {studentId: id || null}}));
  }
  function state(target, kind, message, retry) {
    target.replaceChildren();
    const box = document.createElement("div");
    box.className = "state " + kind;
    box.textContent = message;
    if (retry) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button secondary small";
      button.textContent = "重试";
      button.addEventListener("click", retry);
      box.append(document.createElement("br"), button);
    }
    target.append(box);
  }
  function toast(message) {
    document.querySelector(".toast")?.remove();
    const element = document.createElement("div");
    element.className = "toast";
    element.role = "status";
    element.textContent = message;
    document.body.append(element);
    setTimeout(() => element.remove(), 4000);
  }
  function busy(button, yes) {
    if (!button) return;
    if (yes) { button.dataset.oldText = button.textContent; button.disabled = true; button.textContent = "处理中…"; }
    else { button.disabled = false; button.textContent = button.dataset.oldText || button.textContent; }
  }
  const date = (value) => value ? new Date(value).toLocaleString("zh-CN", {hour12:false}) : "—";
  const source = (value) => `<span class="pill ${String(value || "").includes("模拟") ? "simulated" : ""}">${escape(value || "未注明来源")}</span>`;
  const tierClass = (tier) => ({"冲":"reach","稳":"steady","保":"safe"})[tier] || "";
  const studentLabel = (item) => `${item.province} · ${item.exam_year} · 位次 ${item.rank_no}`;

  async function loadStudentSelector() {
    const select = document.querySelector("#active-student");
    if (!select) return;
    select.innerHTML = '<option value="">选择考生</option>';
    try {
      const result = await api("/students?page_size=100");
      result.data.forEach((item) => select.add(new Option(studentLabel(item), item.id)));
      const selectedId = activeStudent();
      if (selectedId && !result.data.some((item) => item.id === selectedId)) {
        try {
          const item = (await api(`/students/${selectedId}`)).data;
          select.add(new Option(studentLabel(item), item.id));
        } catch (error) {
          if (error.status === 404) setActiveStudent(null);
          else throw error;
        }
      }
      select.value = activeStudent() ? String(activeStudent()) : "";
    } catch (error) {
      select.innerHTML = '<option value="">考生加载失败</option>';
      select.title = error.message + "；点击重试";
      select.addEventListener("click", loadStudentSelector, {once:true});
    }
  }
  function initShell() {
    const nav = pages.map(([key, label, path]) => `<a class="nav-link ${page === key ? "active" : ""}" href="${root}${path}">${label}</a>`).join("");
    document.body.insertAdjacentHTML("afterbegin", `<div class="layout"><aside class="sidebar"><a class="brand" href="${root}index.html">高考志愿决策系统<small>Gaokao Agent</small></a><div class="nav-label">工作台</div><nav aria-label="主导航">${nav}</nav></aside><div class="workspace"><header class="topbar"><span class="topbar-title">${escape(pages.find(([key]) => key === page)?.[1] || "工作台")}</span><div class="topbar-right"><span class="flag">模拟数据仅供演示</span><select id="active-student" aria-label="当前考生"><option value="">加载考生中…</option></select></div></header><div id="page-slot"></div></div></div>`);
    document.querySelector("#page-slot").append(document.querySelector("main"));
    document.querySelector("#active-student").addEventListener("change", (event) => setActiveStudent(Number(event.target.value) || null));
    loadStudentSelector();
  }
  window.App = {api, json, qs, escape, state, toast, busy, date, source, tierClass, activeStudent, setActiveStudent, loadStudentSelector, studentLabel, root};
  initShell();
})();
