const A = window.App;
let page = 1;
const planStatus = {generated:"自动生成",draft:"人工草稿"};
function tiers(items) { return Object.fromEntries(["冲","稳","保"].map((tier)=>[tier,items.filter((item)=>item.tier===tier).length])); }
async function loadList() {
  const target=document.querySelector("#plan-list"), studentId=A.activeStudent();
  if (!studentId) { document.querySelector("#plan-pages").replaceChildren(); return A.state(target,"empty","请选择考生以查看历史方案。"); }
  A.state(target,"loading","正在读取历史方案…");
  try {
    const result=await A.api(`/plans?${A.qs({student_id:studentId,page,page_size:10})}`);
    if (studentId !== A.activeStudent()) return;
    if (!result.data.length) { A.state(target,"empty","当前考生暂无历史方案。"); document.querySelector("#plan-pages").replaceChildren(); return; }
    target.innerHTML=`<div class="table-wrap"><table><thead><tr><th>编号</th><th>生成时间</th><th>类型</th><th>年份</th><th>条目</th><th>说明</th><th>操作</th></tr></thead><tbody>${result.data.map((plan)=>`<tr><td>#${plan.id}</td><td>${A.escape(A.date(plan.created_at))}</td><td><span class="pill">${A.escape(planStatus[plan.status]||plan.status)}</span></td><td>${plan.exam_year}</td><td>${plan.item_count}</td><td>${A.escape(plan.summary||"—")}</td><td><button class="link-button view-plan" type="button" data-id="${plan.id}">查看</button>　<button class="link-button compare-a" type="button" data-id="${plan.id}">设为 A</button>　<button class="link-button compare-b" type="button" data-id="${plan.id}">设为 B</button></td></tr>`).join("")}</tbody></table></div>`;
    target.querySelectorAll(".view-plan").forEach((button)=>button.addEventListener("click",()=>loadDetail(Number(button.dataset.id))));
    for (const side of ["a","b"]) target.querySelectorAll(`.compare-${side}`).forEach((button)=>button.addEventListener("click",()=>{document.querySelector(`#compare-${side}`).value=button.dataset.id;A.toast(`已选方案 ${side.toUpperCase()}`);}));
    const pages=document.querySelector("#plan-pages"); pages.innerHTML=`<button id="prev" type="button" class="button secondary small" ${page===1?"disabled":""}>上一页</button><span>${page} / ${Math.ceil(result.meta.total/10)}</span><button id="next" type="button" class="button secondary small" ${page*10>=result.meta.total?"disabled":""}>下一页</button>`;
    pages.querySelector("#prev").addEventListener("click",()=>{page--;loadList();}); pages.querySelector("#next").addEventListener("click",()=>{page++;loadList();});
  } catch(error) { if (studentId === A.activeStudent()) A.state(target,"error",error.message,loadList); }
}
async function getPlan(id, studentId) {
  const plan=(await A.api(`/plans/${id}`)).data;
  if (plan.student_id !== studentId) throw new Error("该方案不属于当前考生");
  return plan;
}
async function loadDetail(id) {
  const target=document.querySelector("#plan-detail"), studentId=A.activeStudent(); A.state(target,"loading","正在读取方案详情…");
  try {
    const plan=await getPlan(id,studentId); if (studentId !== A.activeStudent()) return;
    document.querySelector("#detail-heading").textContent=`#${plan.id} · ${A.date(plan.created_at)}`;
    if (!plan.items.length) return A.state(target,"empty","该方案没有条目。");
    target.innerHTML=`<div class="notice info">${A.escape(plan.summary||"无方案说明")}</div><div class="table-wrap"><table><thead><tr><th>梯度</th><th>院校</th><th>专业</th><th>匹配分</th><th>推荐依据</th><th>风险说明</th></tr></thead><tbody>${plan.items.map((item)=>`<tr><td><span class="pill ${A.tierClass(item.tier)}">${A.escape(item.tier)}</span></td><td>${A.escape(item.university_name)}</td><td>${A.escape(item.major_name)}</td><td>${A.escape(item.match_score)}</td><td>${A.source(item.evidence?.plan_source)}<div class="small muted">${A.escape(item.reason_text)}</div></td><td>${A.escape(item.risk_notes||"—")}</td></tr>`).join("")}</tbody></table></div>`;
    history.replaceState(null,"",`?plan=${plan.id}`);
  } catch(error) { if (studentId === A.activeStudent()) A.state(target,"error",error.message,()=>loadDetail(id)); }
}
async function compare(event) {
  event.preventDefault(); const a=Number(document.querySelector("#compare-a").value),b=Number(document.querySelector("#compare-b").value),target=document.querySelector("#compare-result"),studentId=A.activeStudent();
  if (!studentId) return A.state(target,"empty","请先选择考生。");
  if (!a||!b||a===b) return A.state(target,"error","请选择两个不同的方案编号。");
  A.state(target,"loading","正在读取两份方案…");
  try {
    const [one,two]=await Promise.all([getPlan(a,studentId),getPlan(b,studentId)]);
    if (studentId !== A.activeStudent()) return;
    const left=tiers(one.items),right=tiers(two.items);
    const key=(item)=>`${item.university_id}-${item.major_id}`;
    const candidates=[...new Set([...one.items.map(key),...two.items.map(key)])];
    const rows=candidates.map((id)=>{const first=one.items.find((item)=>key(item)===id),second=two.items.find((item)=>key(item)===id),item=first||second;return `<tr><td>${A.escape(item.university_name)} / ${A.escape(item.major_name)}</td><td>${first?`${A.escape(first.tier)} · ${A.escape(first.match_score)}`:"—"}</td><td>${second?`${A.escape(second.tier)} · ${A.escape(second.match_score)}`:"—"}</td></tr>`;}).join("");
    target.innerHTML=`<div class="table-wrap"><table class="comparison"><thead><tr><th>项目</th><th>方案 #${one.id}</th><th>方案 #${two.id}</th></tr></thead><tbody><tr><td>生成时间</td><td>${A.escape(A.date(one.created_at))}</td><td>${A.escape(A.date(two.created_at))}</td></tr><tr><td>梯度数量</td><td>冲 ${left["冲"]} · 稳 ${left["稳"]} · 保 ${left["保"]}</td><td>冲 ${right["冲"]} · 稳 ${right["稳"]} · 保 ${right["保"]}</td></tr>${rows}</tbody></table></div>`;
  } catch(error) { if (studentId === A.activeStudent()) A.state(target,"error",error.message,()=>compare(event)); }
}
document.querySelector("#refresh-plans").addEventListener("click",loadList);
document.querySelector("#compare-form").addEventListener("submit",compare);
document.addEventListener("studentchange",()=>{page=1;loadList();A.state(document.querySelector("#plan-detail"),"empty","请选择方案查看详情。");A.state(document.querySelector("#compare-result"),"empty","请选择两个方案进行比较。");document.querySelector("#detail-heading").textContent="";document.querySelector("#compare-form").reset();history.replaceState(null,"",location.pathname);});
loadList(); A.state(document.querySelector("#plan-detail"),"empty","请选择方案查看详情。"); A.state(document.querySelector("#compare-result"),"empty","请选择两个方案进行比较。");
const initialId=Number(new URLSearchParams(location.search).get("plan"));
if (initialId && A.activeStudent()) loadDetail(initialId);
