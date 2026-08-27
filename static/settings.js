const form = document.getElementById("form");
const statusEl = document.getElementById("status");
const runtimeEl = document.getElementById("runtime");
const providerSel = document.getElementById("llm-provider");

const PROVIDER_LABELS = {
  openai: "OpenAI-kompatibel (STACKIT, …)",
  ollama: "Ollama (lokal)",
  anthropic: "Anthropic",
  gemini: "Gemini",
};

function setStatus(text, ok) {
  statusEl.textContent = text;
  statusEl.className = "status " + (ok ? "ok" : "err");
}

function llmPayload() {
  return {
    provider: providerSel.value,
    model: document.getElementById("llm-model").value.trim(),
    baseUrl: document.getElementById("llm-base").value.trim(),
    timeout: Number(document.getElementById("llm-timeout").value || 180),
    apiKey: document.getElementById("llm-key").value,
  };
}

async function load() {
  const r = await fetch("/api/settings");
  const d = await r.json();
  providerSel.innerHTML = "";
  (d.llm.providers || []).forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = PROVIDER_LABELS[p] || p;
    if (p === d.llm.provider) opt.selected = true;
    providerSel.appendChild(opt);
  });
  document.getElementById("llm-model").value = d.llm.model || "";
  document.getElementById("llm-base").value = d.llm.baseUrl || "";
  document.getElementById("llm-timeout").value = d.llm.timeout || 180;
  document.getElementById("llm-key").value = "";
  document.getElementById("llm-key-hint").textContent = d.llm.apiKeyConfigured
    ? "API-Key hinterlegt"
    : "kein API-Key";
  document.getElementById("jira-enabled").checked = !!d.jira.enabled;
  document.getElementById("jira-base").value = d.jira.baseUrl || "";
  document.getElementById("jira-search").value = d.jira.searchUrl || "";
  document.getElementById("jira-email").value = d.jira.email || "";
  document.getElementById("jira-project").value = d.jira.projectKey || "";
  document.getElementById("jira-sheet-template").value = d.jira.effortSheetTemplateUrl || "";
  document.getElementById("jira-sheet-field").value = d.jira.effortSheetField || "";
  document.getElementById("jira-token").value = "";
  document.getElementById("jira-key").value = "";
  document.getElementById("jira-token-hint").textContent = d.jira.apiTokenConfigured
    ? "Token hinterlegt (Jira-User, nicht x-apikey)"
    : "Jira-Token dieses Users, nicht der Gateway-x-apikey";
  document.getElementById("jira-key-hint").textContent = d.jira.apiKeyConfigured
    ? "x-apikey hinterlegt"
    : "kein x-apikey";
  runtimeEl.textContent = `Aktiv: ${d.runtime.llmLabel} · Ticket-Port: ${d.runtime.ticketPort}`;
}

async function saveCurrent() {
  const payload = {
    llm: llmPayload(),
    jira: {
      enabled: document.getElementById("jira-enabled").checked,
      baseUrl: document.getElementById("jira-base").value,
      searchUrl: document.getElementById("jira-search").value,
      email: document.getElementById("jira-email").value,
      projectKey: document.getElementById("jira-project").value,
      effortSheetTemplateUrl: document.getElementById("jira-sheet-template").value,
      effortSheetField: document.getElementById("jira-sheet-field").value,
      apiToken: document.getElementById("jira-token").value,
      apiKey: document.getElementById("jira-key").value,
    },
  };
  const r = await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const d = await r.json();
  if (!r.ok) {
    throw new Error(typeof d.detail === "string" ? d.detail : "Speichern fehlgeschlagen");
  }
  return d;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  setStatus("Speichert…", true);
  try {
    await saveCurrent();
    setStatus("Gespeichert.", true);
    await load();
  } catch (err) {
    setStatus(err.message || "Netzwerkfehler", false);
  }
});

document.getElementById("test-llm").addEventListener("click", async () => {
  setStatus("Speichert und testet LLM…", true);
  try {
    // Formular zuerst speichern — sonst testet der Button alte DB-Werte.
    await saveCurrent();
    await load();
    const r = await fetch("/api/settings/test-llm", { method: "POST" });
    const d = await r.json();
    if (!r.ok) {
      setStatus(d.detail || "LLM-Test fehlgeschlagen", false);
      return;
    }
    setStatus(`LLM ok (${d.provider}${d.model ? " · " + d.model : ""})`, true);
    await load();
  } catch (err) {
    setStatus(err.message || "Netzwerkfehler", false);
  }
});

document.getElementById("test-jira").addEventListener("click", async () => {
  setStatus("Teste Jira…", true);
  try {
    await saveCurrent();
    const r = await fetch("/api/settings/test-jira", { method: "POST" });
    const d = await r.json();
    if (!r.ok) {
      setStatus(d.detail || "Jira-Test fehlgeschlagen", false);
      return;
    }
    setStatus(`Jira ok (${d.displayName || d.accountId})`, true);
  } catch (err) {
    setStatus(err.message || "Netzwerkfehler", false);
  }
});

(window.whenAuthed || Promise.resolve()).then(() =>
  load().catch(() => setStatus("Einstellungen nicht ladbar", false))
);
