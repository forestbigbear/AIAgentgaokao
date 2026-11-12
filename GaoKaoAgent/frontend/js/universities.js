const A = window.App;
const form = document.querySelector("#catalog-filter");
const labels = {universities:"院校",majors:"专业","admission-plans":"招生计划","admission-records":"历年录取"};
let resource = "universities", page = 1;
const columnSets = {
  universities: [["name","院校"],["province","所在地"],["city","城市"],["level","层次"],["applicable_year","适用年份"],["source_name","来源"],["updated_at","更新时间"]],
  majors: [["university_name","院校"],["name","专业"],["subject_requirements","选科要求"],["category","类别"],["applicable_year","适用年份"],["source_name","来源"]],
  "admission-plans": [["university_name","院校"],["major_name","专业"],["province","招生省份"],["exam_year","年份"],["batch_name","批次"],["planned_count","计划数"],["subject_requirements","选科要求"],["source_name","来源"]],
  "admission-records": [["university_name","院校"],["major_name","专业"],["province","省份"],["exam_year","年份"],["batch_name","批次"],["min_score","最低分"],["min_rank_no","最低位次"],["source_name","来源"]],
};
function showFilters() {
  const visible = {universities:["university","city"],majors:["major","subject"],"admission-plans":["university","major","subject"],"admission-records":["university","major"]}[resource];
  form.querySelectorAll("[data-filter]").forEach((node) => node.hidden = !visible.includes(node.dataset.filter));
  document.querySelector("#catalog-heading").textContent = labels[resource];
  document.querySelectorAll("#catalog-tabs .tab").forEach((node) => node.classList.toggle("active", node.dataset.resource === resource));
}
function filters() {
  const fields = form.elements;
  const data = {province:fields.province.value.trim(),year:fields.year.value.trim()};
  if (resource === "universities") { data.name = fields.university_name.value.trim(); data.city = fields.city.value.trim(); }
  if (resource === "majors") { data.name = fields.major_name.value.trim(); data.subject = fields.subject.value.trim(); }
  if (resource.startsWith("admission-")) {
    data.university_name = fields.university_name.value.trim();
    data.major_name = fields.major_name.value.trim();
    if (resource === "admission-plans") data.subject = fields.subject.value.trim();
  }
  return data;
}
function renderValue(row, key) {
  if (key === "source_name") return A.source(row[key]);
  if (key === "updated_at") return A.escape(A.date(row[key]));
  return A.escape(row[key] ?? "—");
}
async function loadCatalog() {
  const target = document.querySelector("#catalog-result"); A.state(target, "loading", "正在查询数据库…");
  document.querySelector("#catalog-total").textContent = "";
  try {
    const result = await A.api(`/${resource}?${A.qs({...filters(),page,page_size:20})}`);
    document.querySelector("#catalog-total").textContent = `共 ${result.meta.total} 条`;
    if (!result.data.length) { A.state(target, "empty", "没有符合条件的记录。"); document.querySelector("#catalog-pages").replaceChildren(); return; }
    const columns = columnSets[resource];
    target.innerHTML = `<div class="table-wrap"><table><thead><tr>${columns.map(([,title]) => `<th>${title}</th>`).join("")}</tr></thead><tbody>${result.data.map((row) => `<tr>${columns.map(([key]) => `<td>${renderValue(row,key)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    const pages = document.querySelector("#catalog-pages");
    pages.innerHTML = `<button class="button secondary small" id="prev" type="button" ${page===1?"disabled":""}>上一页</button><span>${page} / ${Math.ceil(result.meta.total/20)}</span><button class="button secondary small" id="next" type="button" ${page*20>=result.meta.total?"disabled":""}>下一页</button>`;
    pages.querySelector("#prev").addEventListener("click", () => { page--; loadCatalog(); });
    pages.querySelector("#next").addEventListener("click", () => { page++; loadCatalog(); });
  } catch (error) { A.state(target, "error", error.message, loadCatalog); }
}
document.querySelectorAll("#catalog-tabs .tab").forEach((button) => button.addEventListener("click", () => { resource=button.dataset.resource; page=1; showFilters(); loadCatalog(); }));
form.addEventListener("submit", (event) => { event.preventDefault(); page=1; loadCatalog(); });
document.querySelector("#clear-filter").addEventListener("click", () => { form.reset(); page=1; loadCatalog(); });
showFilters(); loadCatalog();
