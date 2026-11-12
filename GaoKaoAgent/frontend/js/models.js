const A = window.App;
const headers = {"Content-Type":"application/json", "X-Local-Settings":"1"};
const form = document.querySelector("#model-form");
let activeKind = "llm";
let configs = null;

function render() {
  const config = configs[activeKind];
  document.querySelector("#model-heading").textContent = activeKind === "llm" ? "问答模型" : "Embedding";
  const status = document.querySelector("#model-status");
  status.textContent = config.ready ? "已配置" : "未配置";
  status.className = "pill " + (config.ready ? "ready" : "pending");
  form.elements.base_url.value = config.base_url || "";
  form.elements.model.value = config.model || "";
  form.elements.api_key.value = "";
  form.elements.api_key.required = !config.has_key;
  form.elements.api_key.placeholder = config.has_key ? "已保存密钥；留空则保持不变" : "填写密钥";
  document.querySelector("#key-hint").textContent = config.has_key ? "已保存密钥；出于安全原因不显示原文。" : "尚未保存密钥。";
  document.querySelector("#show-model-key").checked = false;
  form.elements.api_key.type = "password";
  document.querySelector("#model-message").replaceChildren();
  document.querySelectorAll("#model-tabs .tab").forEach((tab) => {
    const selected = tab.dataset.kind === activeKind;
    tab.classList.toggle("active", selected);
    tab.setAttribute("aria-selected", String(selected));
  });
  form.hidden = false;
}

async function load() {
  const target = document.querySelector("#config-load");
  A.state(target, "loading", "正在读取模型配置…");
  form.hidden = true;
  try {
    configs = (await A.api("/model-settings", {headers})).data;
    target.replaceChildren();
    render();
  } catch (error) { A.state(target, "error", error.message, load); }
}

function payload() {
  return {base_url: form.elements.base_url.value.trim(),
          model: form.elements.model.value.trim(),
          api_key: form.elements.api_key.value.trim() || null};
}

async function save(event) {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const kind = activeKind, button = document.querySelector("#save-model");
  A.busy(button, true);
  A.state(document.querySelector("#model-message"), "loading", "正在保存配置…");
  try {
    configs[kind] = (await A.api(`/model-settings/${kind}`, {method:"PUT",headers,
      body:JSON.stringify(payload())})).data;
    render();
    A.state(document.querySelector("#model-message"), "ready", "配置已保存，并在当前服务生效。");
  } catch (error) { A.state(document.querySelector("#model-message"), "error", error.message); }
  finally { A.busy(button, false); }
}

async function testConnection() {
  if (!form.reportValidity()) return;
  const kind = activeKind, button = document.querySelector("#test-model"), target = document.querySelector("#model-message");
  A.busy(button, true);
  A.state(target, "loading", "正在连接模型服务…");
  try {
    const result = (await A.api(`/model-settings/${kind}/test`, {method:"POST",headers,
      body:JSON.stringify(payload())})).data;
    A.state(target, "ready", kind === "embedding" ? `连接成功，向量维度 ${result.dimension}。` : `连接成功。示例回答：${result.sample_answer}`);
  } catch (error) { A.state(target, "error", error.message, testConnection); }
  finally { A.busy(button, false); }
}

async function clearConfig() {
  const kind = activeKind;
  if (!confirm(`确定清除${kind === "llm" ? "问答模型" : "Embedding"}配置？`)) return;
  const button = document.querySelector("#clear-model"), target = document.querySelector("#model-message");
  A.busy(button, true);
  try {
    configs[kind] = (await A.api(`/model-settings/${kind}`, {method:"DELETE",headers})).data;
    render();
    A.state(target, "empty", "配置已清除。");
  } catch (error) { A.state(target, "error", error.message); }
  finally { A.busy(button, false); }
}

document.querySelectorAll("#model-tabs .tab").forEach((tab) => tab.addEventListener("click", () => {
  activeKind = tab.dataset.kind;
  if (configs) render();
}));
document.querySelector("#show-model-key").addEventListener("change", (event) => {
  form.elements.api_key.type = event.target.checked ? "text" : "password";
});
form.addEventListener("submit", save);
document.querySelector("#test-model").addEventListener("click", testConnection);
document.querySelector("#clear-model").addEventListener("click", clearConfig);
load();
