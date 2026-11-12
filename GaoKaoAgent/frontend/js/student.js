const A = window.App;
const form = document.querySelector("#student-form");
let editingId = null, page = 1;
const splitList = (value) => value.split(/[，,;；]/).map((part) => part.trim()).filter(Boolean);
function clearForm() {
  editingId = null; form.reset(); document.querySelector("#form-title").textContent = "新增考生";
  document.querySelector("#submit-student").textContent = "保存考生";
  document.querySelector("#submit-student").dataset.oldText = "保存考生";
  document.querySelector("#form-message").replaceChildren();
  form.querySelectorAll(".field-error").forEach((node) => node.textContent = "");
  form.querySelectorAll(".invalid").forEach((node) => node.classList.remove("invalid"));
}
function validate() {
  let first = null;
  for (const input of form.querySelectorAll("input[required], input[type=number]")) {
    const message = !input.value.trim() ? "请填写此项" : !input.validity.valid ? "请填写有效范围内的数值" : "";
    input.classList.toggle("invalid", Boolean(message));
    input.closest(".field").querySelector(".field-error").textContent = message;
    if (message && !first) first = input;
  }
  for (const name of ["interests", "target_cities"]) {
    const input = form.elements[name], values = splitList(input.value);
    const message = values.length > 20 || values.some((item) => item.length > 100) ? "最多 20 项，每项不超过 100 字" : "";
    input.classList.toggle("invalid", Boolean(message));
    input.closest(".field").querySelector(".field-error").textContent = message;
    if (message && !first) first = input;
  }
  if (first) first.focus();
  return !first;
}
function values() {
  return {
    province: form.elements.province.value.trim(), exam_year: Number(form.elements.exam_year.value),
    score: Number(form.elements.score.value), rank_no: Number(form.elements.rank_no.value),
    subject_combination: form.elements.subject_combination.value.trim(),
    risk_preference: form.elements.risk_preference.value,
    interests: splitList(form.elements.interests.value), target_cities: splitList(form.elements.target_cities.value),
  };
}
async function save(event) {
  event.preventDefault(); if (!validate()) return;
  const button = document.querySelector("#submit-student"), message = document.querySelector("#form-message");
  A.busy(button, true); message.replaceChildren();
  try {
    const result = await A.json(editingId ? `/students/${editingId}` : "/students", editingId ? "PATCH" : "POST", values());
    A.setActiveStudent(result.data.id); await A.loadStudentSelector();
    A.toast(editingId ? "考生信息已更新" : "考生信息已保存");
    clearForm(); page = 1; await Promise.all([loadList(), loadDetail()]);
  } catch (error) { message.innerHTML = `<div class="notice error">${A.escape(error.message)}</div>`; }
  finally { A.busy(button, false); }
}
async function edit(id) {
  try {
    const item = (await A.api(`/students/${id}`)).data;
    editingId = id;
    for (const name of ["province","exam_year","score","rank_no","subject_combination","risk_preference"])
      form.elements[name].value = item[name];
    form.elements.interests.value = item.interests.join("，");
    form.elements.target_cities.value = item.target_cities.join("，");
    document.querySelector("#form-title").textContent = "修改考生 #" + id;
    document.querySelector("#submit-student").textContent = "保存修改";
    form.scrollIntoView({behavior:"smooth", block:"start"});
  } catch (error) { A.toast(error.message); }
}
async function loadList() {
  const target = document.querySelector("#student-list"); A.state(target, "loading", "正在读取考生档案…");
  try {
    const result = await A.api(`/students?${A.qs({page,page_size:10})}`);
    if (!result.data.length) { A.state(target, "empty", "暂无考生档案。"); document.querySelector("#student-pages").replaceChildren(); return; }
    target.innerHTML = `<div class="table-wrap"><table><thead><tr><th>编号</th><th>省份 / 年份</th><th>成绩</th><th>位次</th><th>选科</th><th>风险偏好</th><th>操作</th></tr></thead><tbody>${result.data.map((item) => `<tr><td>#${item.id}</td><td>${A.escape(item.province)} · ${item.exam_year}</td><td>${A.escape(item.score)}</td><td>${item.rank_no}</td><td>${A.escape(item.subject_combination)}</td><td>${A.escape(({balanced:"均衡",conservative:"保守",aggressive:"积极"})[item.risk_preference])}</td><td><button type="button" class="link-button choose" data-id="${item.id}">选用</button>　<button type="button" class="link-button edit" data-id="${item.id}">修改</button></td></tr>`).join("")}</tbody></table></div>`;
    target.querySelectorAll(".choose").forEach((node) => node.addEventListener("click", async () => { A.setActiveStudent(Number(node.dataset.id)); await A.loadStudentSelector(); loadDetail(); A.toast("已切换当前考生"); }));
    target.querySelectorAll(".edit").forEach((node) => node.addEventListener("click", () => edit(Number(node.dataset.id))));
    const pages = document.querySelector("#student-pages");
    pages.innerHTML = `<button class="button secondary small" type="button" id="prev" ${page <= 1 ? "disabled" : ""}>上一页</button><span>${page} / ${Math.ceil(result.meta.total / 10)}</span><button class="button secondary small" type="button" id="next" ${page * 10 >= result.meta.total ? "disabled" : ""}>下一页</button>`;
    pages.querySelector("#prev").addEventListener("click", () => { page--; loadList(); });
    pages.querySelector("#next").addEventListener("click", () => { page++; loadList(); });
  } catch (error) { A.state(target, "error", error.message, loadList); }
}
async function loadDetail() {
  const target = document.querySelector("#selected-detail"), id = A.activeStudent();
  if (!id) return A.state(target, "empty", "尚未选择考生。");
  A.state(target, "loading", "正在读取档案…");
  try {
    const item = (await A.api(`/students/${id}`)).data;
    if (id !== A.activeStudent()) return;
    target.innerHTML = `<div class="small muted">考生 #${item.id}</div><h3>${A.escape(item.province)} · ${item.exam_year}</h3><p>成绩 ${A.escape(item.score)}　位次 ${item.rank_no}</p><p>选科：${A.escape(item.subject_combination)}</p><p>专业兴趣：${A.escape(item.interests.join("、") || "未填写")}</p><p>目标城市：${A.escape(item.target_cities.join("、") || "未填写")}</p><div class="form-actions"><a class="button" href="recommendation.html">开始推荐</a></div>`;
  } catch (error) { if (id === A.activeStudent()) A.state(target, "error", error.message, loadDetail); }
}
form.addEventListener("submit", save);
document.querySelector("#reset-student").addEventListener("click", clearForm);
document.querySelector("#refresh-students").addEventListener("click", loadList);
document.addEventListener("studentchange", loadDetail);
loadList(); loadDetail();
