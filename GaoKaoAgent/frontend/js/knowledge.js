const A = window.App;
let page = 1;
const statusNames = {pending_embedding:"待向量化",indexing:"索引中",ready:"可检索",failed:"处理失败"};
const typeNames = {policy:"招生政策",charter:"招生章程",major:"专业介绍"};
function safeLink(url) { try { const parsed = new URL(url); return ["https:","http:"].includes(parsed.protocol) ? parsed.href : null; } catch { return null; } }
function sources(items) {
  if (!items?.length) return '<div class="state empty">未找到可引用的资料片段。</div>';
  return `<div class="source-list">${items.map((item,index) => `<div class="source-item"><h4>[${index+1}] ${A.escape(item.original_name || "未知文档")} · ${A.escape(item.page_or_section || "全文")}</h4><p>${A.source(item.source_name)}　适用年份 ${A.escape(item.applicable_year ?? "未标注")}</p><p>${A.escape(item.content || "")}</p>${safeLink(item.source_url) ? `<a class="small" href="${A.escape(safeLink(item.source_url))}" target="_blank" rel="noopener noreferrer">查看来源</a>` : ""}</div>`).join("")}</div>`;
}
async function ask(mode) {
  const question = document.querySelector("#question").value.trim();
  if (question.length < 2) return A.toast("请至少输入两个字符");
  const button = document.querySelector(mode === "qa" ? "#ask-button" : "#search-button"), target = document.querySelector("#answer-result");
  A.busy(button, true); A.state(target, "loading", mode === "qa" ? "正在检索并生成答案…" : "正在检索资料…");
  try {
    const result = (await A.json(mode === "qa" ? "/knowledge-qa" : "/knowledge-search", "POST", {question,limit:5})).data;
    if (mode === "qa") target.innerHTML = `<div class="panel"><div class="section-head"><h2>回答</h2></div><div class="answer">${A.escape(result.answer)}</div></div><div class="section-head" style="margin-top:18px"><h2>引用资料</h2></div>${sources(result.sources)}`;
    else target.innerHTML = `<div class="section-head"><h2>检索片段</h2></div>${sources(result)}`;
  } catch (error) { A.state(target, "error", error.message, () => ask(mode)); }
  finally { A.busy(button, false); }
}
async function upload(event) {
  event.preventDefault(); const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const file = form.elements.file.files[0];
  if (!file || file.size > 10*1024*1024) return A.toast("请选择不超过 10 MB 的文件");
  const button = document.querySelector("#upload-button"), message = document.querySelector("#upload-message");
  A.busy(button,true); message.replaceChildren();
  const data = new FormData(form);
  for (const key of ["source_url","applicable_region","applicable_year"]) if (!data.get(key)) data.delete(key);
  try {
    const result = (await A.api("/knowledge-documents", {method:"POST",body:data})).data;
    message.innerHTML = `<div class="notice info">${A.escape(result.original_name)} 已上传，状态：${A.escape(statusNames[result.ingest_status] || result.ingest_status)}。</div>`;
    form.reset(); page=1; loadDocuments();
  } catch (error) { message.innerHTML = `<div class="notice error">${A.escape(error.message)}</div>`; }
  finally { A.busy(button,false); }
}
async function loadDocuments() {
  const target = document.querySelector("#document-list"); A.state(target,"loading","正在读取知识文档…");
  try {
    const result = await A.api(`/knowledge-documents?${A.qs({page,page_size:10})}`);
    if (!result.data.length) { A.state(target,"empty","知识库暂无文档。"); document.querySelector("#document-pages").replaceChildren(); return; }
    target.innerHTML = `<div class="table-wrap"><table><thead><tr><th>文件</th><th>类型</th><th>来源</th><th>适用地区 / 年份</th><th>状态</th><th>上传时间</th><th>操作</th></tr></thead><tbody>${result.data.map((item)=>`<tr><td>${A.escape(item.original_name)}</td><td>${A.escape(typeNames[item.document_type] || item.document_type)}</td><td>${A.source(item.source_name)}</td><td>${A.escape(item.applicable_region || "未标注")} / ${A.escape(item.applicable_year ?? "未标注")}</td><td><span class="pill ${A.escape(item.ingest_status === "ready" ? "ready" : item.ingest_status === "failed" ? "failed" : "pending")}">${A.escape(statusNames[item.ingest_status] || item.ingest_status)}</span></td><td>${A.escape(A.date(item.uploaded_at))}</td><td>${item.ingest_status !== "ready" ? `<button class="link-button index" type="button" data-id="${item.id}">建立索引</button>　` : ""}<button class="link-button remove" type="button" data-id="${item.id}">删除</button></td></tr>`).join("")}</tbody></table></div>`;
    target.querySelectorAll(".index").forEach((button)=>button.addEventListener("click",()=>indexDocument(Number(button.dataset.id),button)));
    target.querySelectorAll(".remove").forEach((button)=>button.addEventListener("click",()=>deleteDocument(Number(button.dataset.id),button)));
    const pages=document.querySelector("#document-pages"); pages.innerHTML=`<button class="button secondary small" id="prev" type="button" ${page===1?"disabled":""}>上一页</button><span>${page} / ${Math.ceil(result.meta.total/10)}</span><button class="button secondary small" id="next" type="button" ${page*10>=result.meta.total?"disabled":""}>下一页</button>`;
    pages.querySelector("#prev").addEventListener("click",()=>{page--;loadDocuments();}); pages.querySelector("#next").addEventListener("click",()=>{page++;loadDocuments();});
  } catch (error) { A.state(target,"error",error.message,loadDocuments); }
}
async function indexDocument(id,button) {
  A.busy(button,true);
  try { await A.api(`/knowledge-documents/${id}/index`,{method:"POST"}); A.toast("索引已建立"); loadDocuments(); }
  catch(error) { A.toast(error.message); A.busy(button,false); }
}
async function deleteDocument(id,button) {
  if (!confirm("确定删除该文档及其向量索引？")) return;
  A.busy(button,true);
  try { await A.api(`/knowledge-documents/${id}`,{method:"DELETE"}); A.toast("文档已删除"); loadDocuments(); }
  catch(error) { A.toast(error.message); A.busy(button,false); }
}
document.querySelector("#qa-form").addEventListener("submit",(event)=>{event.preventDefault();ask("qa");});
document.querySelector("#search-button").addEventListener("click",()=>ask("search"));
document.querySelector("#upload-form").addEventListener("submit",upload);
document.querySelector("#refresh-documents").addEventListener("click",loadDocuments);
loadDocuments(); A.state(document.querySelector("#answer-result"),"empty","尚未提问。");
