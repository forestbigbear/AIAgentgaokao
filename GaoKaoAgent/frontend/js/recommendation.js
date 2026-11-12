const A = window.App;
const statusLabels = {completed:"已完成",partial:"部分完成",insufficient_data:"数据不足",invalid_input:"输入异常",failed:"运行失败",running:"运行中"};
let resultRevision = 0;
function latestRiskEvent(events) {
  return [...(events || [])].reverse().find((event) => event.agent_name === "risk_assessment" && event.status === "completed") || null;
}
function card(item) {
  const e = item.evidence || {};
  const history = e.history_records || [];
  const rankBasis = history.map((row) => `${A.escape(row.exam_year)} 年 ${A.escape(row.min_rank_no)} 位次（${A.escape(row.source_name || "未注明来源")}）`).join("；");
  return `<article class="recommend-item"><div class="item-top"><div><h3>${A.escape(item.university_name)}</h3><div class="small muted">${A.escape(item.major_name)}</div></div><div class="score">${A.escape(item.match_score)}</div></div><p>${A.escape(item.reason_text)}</p><div class="source-row"><span class="small muted">计划 ${A.escape(e.plan_year ?? "—")} 年</span>${A.source(e.plan_source)}</div><p>历史最低位次：${rankBasis || "无可用记录"}</p><p class="small">${A.escape(item.risk_notes || "")}</p></article>`;
}
function render(run, items, risk, gaps, unranked) {
  const status = document.querySelector("#run-status"), target = document.querySelector("#recommendation-result");
  const actions = document.querySelector("#result-actions");
  status.innerHTML = `<div class="notice ${run.status === "failed" ? "error" : "info"}">运行 #${run.id} · ${A.escape(statusLabels[run.status] || run.status)} · 调整 ${run.adjustment_count} 次 · ${A.escape(A.date(run.finished_at))}</div>`;
  actions.innerHTML = `<a class="button secondary small" href="agents.html?run=${run.id}">Agent 记录</a>${run.plan ? `<a class="button secondary small" href="history.html?plan=${run.plan.id}">方案详情</a>` : ""}`;
  if (!items.length) A.state(target, "empty", "当前没有可用的志愿推荐。请检查考生信息和招生数据。");
  else target.innerHTML = `<div class="tier-grid">${["冲","稳","保"].map((tier) => { const group=items.filter((item)=>item.tier===tier); return `<div class="tier-column ${A.tierClass(tier)}"><div class="tier-head"><strong>${tier}</strong><span>${group.length} 项</span></div>${group.length ? group.map(card).join("") : '<div class="state empty">暂无该梯度候选</div>'}</div>`; }).join("")}</div>`;
  const riskTarget = document.querySelector("#risk-result");
  if (!risk) A.state(riskTarget, "empty", "尚无风险评估结果。");
  else riskTarget.innerHTML = `<div class="panel"><div class="section-head"><strong>总体风险</strong><span class="pill ${A.escape(risk.overall_risk)}">${A.escape(({high:"较高",medium:"需关注",low:"较低"})[risk.overall_risk] || risk.overall_risk)}</span></div>${risk.issues?.length ? `<ul class="notice-list">${risk.issues.map((issue)=>`<li>${A.escape(issue)}</li>`).join("")}</ul>` : '<p class="muted">未发现额外风险。</p>'}${risk.suggestions?.length ? `<h3 class="small">调整建议</h3><ul class="notice-list">${risk.suggestions.map((item)=>`<li>${A.escape(item)}</li>`).join("")}</ul>` : ""}<div class="notice info">${A.escape(risk.disclaimer || "仅供决策辅助，不保证录取。")}</div></div>`;
  const gapTarget = document.querySelector("#gap-result");
  if (!gaps.length && !unranked.length) A.state(gapTarget, "empty", "本次未记录数据缺口。");
  else gapTarget.innerHTML = `<div class="panel"><ul class="notice-list">${[...new Set(gaps)].map((gap)=>`<li>${A.escape(gap)}</li>`).join("")}${unranked.map((item)=>`<li>${A.escape(item.university_name)} / ${A.escape(item.major_name)}：${A.escape(item.reason)}</li>`).join("")}</ul></div>`;
}
async function loadStudent() {
  const target = document.querySelector("#student-summary"), id = A.activeStudent();
  document.querySelector("#start-run").disabled = !id;
  if (!id) return A.state(target, "empty", "请选择考生或先录入档案。");
  A.state(target, "loading", "正在读取考生档案…");
  try {
    const item = (await A.api(`/students/${id}`)).data;
    if (id !== A.activeStudent()) return;
    target.innerHTML = `<strong>${A.escape(item.province)} · ${item.exam_year}</strong><div class="small muted">位次 ${item.rank_no} · ${A.escape(item.subject_combination)} · 风险偏好 ${A.escape(({balanced:"均衡",conservative:"保守",aggressive:"积极"})[item.risk_preference])}</div>`;
  } catch (error) { if (id === A.activeStudent()) A.state(target, "error", error.message, loadStudent); }
}
async function loadLastRun() {
  const revision = ++resultRevision;
  const studentId = A.activeStudent();
  const id = Number(localStorage.getItem(`gaokao_run_id_${studentId}`));
  document.querySelector("#run-status").replaceChildren();
  document.querySelector("#result-actions").replaceChildren();
  A.state(document.querySelector("#risk-result"), "empty", "尚无风险评估结果。");
  A.state(document.querySelector("#gap-result"), "empty", "尚无数据缺口记录。");
  if (!id || !studentId) {
    A.state(document.querySelector("#recommendation-result"), "empty", "尚未生成推荐方案。");
    return;
  }
  A.state(document.querySelector("#recommendation-result"), "loading", "正在读取最近运行结果…");
  try {
    const run = (await A.api(`/workflow-runs/${id}`)).data;
    if (studentId !== A.activeStudent() || revision !== resultRevision) return;
    if (run.student_id !== studentId) throw new Error("运行记录与当前考生不匹配");
    const riskEvent = latestRiskEvent(run.events);
    const risk = riskEvent?.output_summary || null, gaps = riskEvent?.input_summary?.data_gaps || [];
    render(run, run.plan?.items || [], risk, gaps, []);
  } catch (error) { if (studentId === A.activeStudent() && revision === resultRevision) A.state(document.querySelector("#recommendation-result"), "error", error.message, loadLastRun); }
}
async function start() {
  const id = A.activeStudent(); if (!id) return A.toast("请先选择考生");
  const revision = ++resultRevision;
  const button = document.querySelector("#start-run"); A.busy(button, true);
  document.querySelector("#run-status").replaceChildren();
  document.querySelector("#result-actions").replaceChildren();
  A.state(document.querySelector("#recommendation-result"), "loading", "六个 Agent 正在分析数据，请稍候…");
  A.state(document.querySelector("#risk-result"), "loading", "等待风险复核…");
  A.state(document.querySelector("#gap-result"), "loading", "等待数据检查…");
  try {
    const result = (await A.json("/workflow-runs", "POST", {student_id:id,max_adjustments:Number(document.querySelector("#max-adjustments").value)})).data;
    localStorage.setItem(`gaokao_run_id_${id}`, result.run.id);
    if (id !== A.activeStudent() || revision !== resultRevision) return;
    render(result.run, result.recommendations, result.risk_report, result.data_gaps || [], result.unranked_candidates || []);
    A.toast("方案已生成并保存");
  } catch (error) {
    if (id === A.activeStudent() && revision === resultRevision) {
      A.state(document.querySelector("#recommendation-result"), "error", error.message, start);
      A.state(document.querySelector("#risk-result"), "empty", "本次运行未产生风险评估结果。");
      A.state(document.querySelector("#gap-result"), "empty", "本次运行未产生数据检查结果。");
    }
  }
  finally { A.busy(button, false); }
}
document.querySelector("#start-run").addEventListener("click", start);
document.addEventListener("studentchange", () => { loadStudent(); loadLastRun(); });
loadStudent(); loadLastRun();
