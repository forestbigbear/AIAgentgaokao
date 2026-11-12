const A = window.App;
const countPaths = {students:"/students",universities:"/universities",majors:"/majors","knowledge-documents":"/knowledge-documents"};

async function refreshOverview() {
  const button = document.querySelector("#refresh"); A.busy(button, true);
  const results = await Promise.allSettled(Object.entries(countPaths).map(async ([key,path]) => {
    const result = await A.api(path + "?page_size=1");
    document.querySelector(`[data-count="${key}"]`).textContent = result.meta.total;
    return result;
  }));
  results.forEach((result, index) => {
    if (result.status === "rejected") document.querySelectorAll("[data-count]")[index].textContent = "失败";
  });
  const status = document.querySelector("#data-status");
  if (results.some((item) => item.status === "rejected")) A.state(status, "error", "部分数据读取失败，请检查服务后重试。", refreshOverview);
  else status.innerHTML = `<div class="notice info">数据库已连接，院校与专业来源请逐条核验。</div><p class="small muted">院校、专业和知识文档数量均来自当前数据库。</p>`;
  await loadRecent(); await loadCurrent(); A.busy(button, false);
}
async function loadRecent() {
  const target = document.querySelector("#recent-students"); A.state(target, "loading", "正在读取考生档案…");
  try {
    const result = await A.api("/students?page_size=5");
    if (!result.data.length) return A.state(target, "empty", "暂无考生档案。");
    target.innerHTML = `<div class="table-wrap"><table><thead><tr><th>省份</th><th>报考年份</th><th>位次</th><th>选科</th><th>风险偏好</th><th></th></tr></thead><tbody>${result.data.map((item) => `<tr><td>${A.escape(item.province)}</td><td>${item.exam_year}</td><td class="mono">${item.rank_no}</td><td>${A.escape(item.subject_combination)}</td><td>${A.escape(({conservative:"保守",balanced:"均衡",aggressive:"积极"})[item.risk_preference])}</td><td><button class="link-button select-student" data-id="${item.id}" type="button">设为当前考生</button></td></tr>`).join("")}</tbody></table></div>`;
    target.querySelectorAll(".select-student").forEach((button) => button.addEventListener("click", () => { A.setActiveStudent(Number(button.dataset.id)); A.loadStudentSelector(); loadCurrent(); A.toast("已切换当前考生"); }));
  } catch (error) { A.state(target, "error", error.message, loadRecent); }
}
async function loadCurrent() {
  const target = document.querySelector("#current-student"); const id = A.activeStudent();
  if (!id) return A.state(target, "empty", "尚未选择考生。");
  A.state(target, "loading", "正在读取当前考生…");
  try {
    const item = (await A.api(`/students/${id}`)).data;
    if (id !== A.activeStudent()) return;
    target.innerHTML = `<h2 style="font-size:17px;margin:0 0 12px">${A.escape(item.province)} · ${item.exam_year}</h2><p>高考成绩 <strong>${A.escape(item.score)}</strong>　全省位次 <strong>${item.rank_no}</strong></p><p class="muted">选科：${A.escape(item.subject_combination)}</p><div class="form-actions"><a class="button" href="pages/recommendation.html">生成方案</a><a class="button secondary" href="pages/history.html">历史方案</a></div>`;
  } catch (error) { if (id === A.activeStudent()) A.state(target, "error", error.message, loadCurrent); }
}
document.querySelector("#refresh").addEventListener("click", refreshOverview);
document.addEventListener("studentchange", loadCurrent);
refreshOverview();
