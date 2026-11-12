const A = window.App;
const names = {student_profile:"考生画像",task_planning:"任务规划",data_retrieval:"数据检索",university_matching:"院校匹配",recommendation:"志愿推荐",risk_assessment:"风险评估",adjustment:"方案调整"};
const order = ["student_profile","task_planning","data_retrieval","university_matching","recommendation","risk_assessment"];
let timer = null;
function resetRun(message) {
  clearTimeout(timer);
  document.querySelector("#progress-fill").style.width = "0%";
  document.querySelector("#run-meta").textContent = "";
  document.querySelector("#node-overview").replaceChildren();
  A.state(document.querySelector("#run-events"), "empty", message);
}
function eventCard(event) {
  const text = event.error_message || "";
  return `<article class="event ${event.status === "failed" ? "failed" : ""}"><div class="event-head"><h3>${A.escape(names[event.agent_name] || event.agent_name)}</h3><span class="pill ${A.escape(event.status)}">${A.escape(({running:"执行中",completed:"完成",failed:"失败"})[event.status] || event.status)}</span></div><p>${A.escape(A.date(event.created_at))}${text ? ` · ${A.escape(text)}` : ""}</p>${event.input_summary || event.output_summary ? `<details><summary>查看输入与输出</summary>${event.input_summary ? `<strong class="small">输入</strong><pre>${A.escape(JSON.stringify(event.input_summary,null,2))}</pre>` : ""}${event.output_summary ? `<strong class="small">输出</strong><pre>${A.escape(JSON.stringify(event.output_summary,null,2))}</pre>` : ""}</details>` : ""}</article>`;
}
function render(run) {
  const latest = Object.fromEntries(order.map((key) => [key, [...run.events].reverse().find((event) => event.agent_name === key)]));
  const complete = order.filter((key) => latest[key]?.status === "completed").length;
  document.querySelector("#progress-fill").style.width = `${Math.round(complete / order.length * 100)}%`;
  document.querySelector("#run-meta").textContent = `运行 #${run.id} · ${run.status} · ${complete}/6 节点完成 · 调整 ${run.adjustment_count} 次`;
  document.querySelector("#node-overview").innerHTML = order.map((key,index) => `<div class="metric"><div class="metric-label">${String(index+1).padStart(2,"0")} · ${names[key]}</div><div class="metric-value" style="font-size:15px;margin-top:16px">${A.escape(({running:"执行中",completed:"已完成",failed:"失败"})[latest[key]?.status] || "未开始")}</div><div class="metric-note">${A.escape(A.date(latest[key]?.created_at))}</div></div>`).join("");
  const target = document.querySelector("#run-events");
  if (!run.events.length) A.state(target, "empty", "尚无执行事件。");
  else target.innerHTML = `<div class="event-list">${run.events.map(eventCard).join("")}</div>`;
  clearTimeout(timer);
  if (run.status === "running") timer = setTimeout(loadRun, 2500);
}
async function loadRun() {
  const id = Number(document.querySelector("#run-id").value);
  if (!id) return resetRun("输入运行编号，或先生成推荐方案。");
  const studentId = A.activeStudent();
  const target = document.querySelector("#run-events"); A.state(target, "loading", "正在读取执行记录…");
  try {
    const run = (await A.api(`/workflow-runs/${id}`)).data;
    if (id !== Number(document.querySelector("#run-id").value) || studentId !== A.activeStudent()) return;
    if (studentId && run.student_id !== studentId) throw new Error("该运行记录不属于当前考生");
    render(run);
    localStorage.setItem(`gaokao_run_id_${run.student_id}`, run.id);
  } catch (error) { if (studentId === A.activeStudent()) { resetRun("执行记录读取失败。"); A.state(target, "error", error.message, loadRun); } }
}
document.querySelector("#run-form").addEventListener("submit", (event) => { event.preventDefault(); loadRun(); });
document.querySelector("#refresh-run").addEventListener("click", loadRun);
document.addEventListener("studentchange", () => {
  const id = A.activeStudent();
  document.querySelector("#run-id").value = id ? localStorage.getItem(`gaokao_run_id_${id}`) || "" : "";
  history.replaceState(null, "", location.pathname);
  resetRun("输入运行编号，或先生成推荐方案。");
  if (document.querySelector("#run-id").value) loadRun();
});
document.querySelector("#run-id").value = new URLSearchParams(location.search).get("run") || localStorage.getItem(`gaokao_run_id_${A.activeStudent()}`) || "";
loadRun();
