(function () {
  const intro = document.getElementById("intro-prompt");
  const introText = document.getElementById("intro-prompt-text");
  const jiraBtn = document.getElementById("jira-create");
  const ticketFinish = document.getElementById("ticket-finish");
  const openJiraLink = document.getElementById("ticket-open-jira");
  const newChangeBtn = document.getElementById("ticket-new-change");
  const ticket = document.getElementById("ticket");
  const headline = document.getElementById("ticket-headline");
  const metaRoot = document.getElementById("ticket-meta");
  const priorityEl = document.getElementById("ticket-priority");
  const priorityCell = document.getElementById("ticket-priority-cell");
  const kindEl = document.getElementById("ticket-kind");
  const overview = document.getElementById("ticket-overview");
  const overviewFields = document.getElementById("ticket-overview-fields");
  const costs = document.getElementById("ticket-costs");
  const costFields = document.getElementById("ticket-cost-fields");
  const effortSheetOpen = document.getElementById("effort-sheet-open");
  const effortSheetLink = document.getElementById("effort-sheet-link");
  let effortSheetTemplateUrl = "";
  let effortSheetOpenUrl = "";
  const team = document.getElementById("ticket-team");
  const teamFields = document.getElementById("ticket-team-fields");
  const filesSection = document.getElementById("ticket-files");
  const fileList = document.getElementById("ticket-file-list");
  const fileAdd = document.getElementById("ticket-file-add");
  const fileInput = document.getElementById("ticket-file-input");
  const fieldsRoot = document.getElementById("ticket-fields");
  if (
    !intro ||
    !introText ||
    !jiraBtn ||
    !ticket ||
    !headline ||
    !metaRoot ||
    !priorityEl ||
    !priorityCell ||
    !kindEl ||
    !overview ||
    !overviewFields ||
    !costs ||
    !costFields ||
    !team ||
    !teamFields ||
    !filesSection ||
    !fileList ||
    !fileAdd ||
    !fileInput ||
    !fieldsRoot
  )
    return;

  const STEPS = [
    {
      key: "title",
      prompt: "Wie lautet der Titel des Changes?",
      placeholder: "Titel Change",
      label: "Titel",
      kind: "headline",
    },
    {
      key: "start",
      prompt: "Wann soll der Change starten?",
      placeholder: "Start",
      label: "Start",
      kind: "meta",
      date: true,
    },
    {
      key: "end",
      prompt: "Wann soll der Change fertig sein?",
      placeholder: "Ende",
      label: "Ende",
      kind: "meta",
      date: true,
    },
    {
      key: "sponsor",
      prompt: "Wer beauftragt diesen Change?",
      placeholder: "Auftraggeber",
      label: "Auftraggeber",
      kind: "meta",
      choices: [
        "SCS - Bau",
        "SCS - FM",
        "SCS - EM",
        "SCS - V&S",
        "SCS - CSM",
        "IPAI",
        "SIS",
        "CIT",
      ],
    },
    {
      key: "components",
      prompt: "Welche Stichwörter / Tags passen?",
      placeholder: "Stichwörter / Tags",
      label: "Stichwörter / Tags",
      kind: "meta",
      jiraLookup: "components",
      multi: true,
      hint:
        "Stichwörter beschreiben Systeme, Themen oder Bereiche — z. B. SAP, Schul-App oder Digitalisierung. Mehrere auswählbar.",
    },
    {
      key: "nonprofit",
      prompt: "Ist das Projekt gemeinnützig?",
      placeholder: "Gemeinnützig",
      label: "Ist das Projekt gemeinnützig",
      kind: "meta",
      choices: ["Ja", "Nein", "Weiß ich noch nicht"],
    },
    {
      key: "description",
      prompt: "Worum geht es — in wenigen Sätzen?",
      placeholder: "Beschreibung",
      label: "Beschreibung",
      kind: "overview",
      long: true,
      enhance: true,
    },
    {
      key: "approver",
      prompt: "Wer genehmigt den Change (nach Freigabematrix)?",
      placeholder: "Name suchen…",
      label: "Genehmigende Person",
      kind: "team",
      jiraLookup: "user",
      choices: ["Ich weiß es nicht"],
      keepForm: true,
    },
    {
      key: "lead",
      prompt: "Wer übernimmt die Gesamtprojektleitung?",
      placeholder: "Gesamtprojektleitung",
      label: "Gesamtprojektleitung",
      kind: "team",
      jiraLookup: "user",
    },
    {
      key: "change_team",
      prompt: "Welche Personen unterstützen bei diesem Projekt?",
      placeholder: "Namen, durch Komma getrennt",
      label: "Change-Team",
      kind: "team",
    },
    {
      key: "stakeholder",
      prompt: "Wer sind die Stakeholder?",
      placeholder: "Stakeholder",
      label: "Stakeholder",
      kind: "team",
    },
    {
      key: "process_owner",
      prompt:
        "Welche Person aus der SCS übernimmt die Verantwortung, wenn der Change in den Betrieb übergegangen ist?",
      placeholder: "Name suchen…",
      label: "Process Owner",
      kind: "team",
      jiraLookup: "user",
      choices: ["Ich weiß es noch nicht"],
      keepForm: true,
    },
    {
      key: "solution_owner",
      prompt:
        "Welche Person aus der IT übernimmt die Verantwortung, wenn der Change in den Betrieb übergegangen ist?",
      placeholder: "Name suchen…",
      label: "Solution Owner",
      kind: "team",
      onlyKind: "it_request",
      jiraLookup: "user",
      choices: ["Ich weiß es noch nicht"],
      keepForm: true,
    },
    {
      key: "it_owner",
      prompt: "Wer ist die verantwortliche Person aus der IT?",
      placeholder: "Ist die verantwortliche Person aus der IT",
      label: "Ist die verantwortliche Person aus der IT",
      kind: "team",
      onlyKind: "it_request",
      jiraLookup: "user",
    },
  ];

  const AUTHOR_STEP = {
    key: "author",
    label: "Autor",
    kind: "team",
    jiraLookup: "user",
  };

  const BENEFIT_STEP = {
    key: "benefit",
    label: "Nutzen",
    kind: "overview",
    long: true,
    enhance: true,
  };

  const REASON_STEP = {
    key: "reason",
    label: "Begründung",
    kind: "overview",
    long: true,
    enhance: true,
  };

  const SOLUTION_STEP = {
    key: "solution",
    label: "Lösungen/Maßnahme",
    kind: "overview",
    long: true,
    enhance: true,
  };

  const RISKS_STEP = {
    key: "risks",
    label: "Bekannte Risiken",
    kind: "overview",
    long: true,
    enhance: true,
  };

  const COST_FB_STEP = {
    key: "effort_fb",
    label: "Aufwand FB",
    kind: "cost",
    prompt: "Wie viele Personentage braucht der Fachbereich?",
    placeholder: "z. B. 8 PT",
  };

  const COST_IT_STEP = {
    key: "effort_it",
    label: "Aufwand IT",
    kind: "cost",
    onlyKind: "it_request",
    prompt: "Wie viele Personentage braucht die IT?",
    placeholder: "z. B. 5 PT",
  };

  const COST_MONEY_STEP = {
    key: "costs",
    label: "Kosten",
    kind: "cost",
  };

  const PRIORITY_STEP = {
    key: "priority",
    label: "Priorität",
    kind: "priority",
  };

  const THIN_STORY = 80;
  const SKIP_THIN = "Trotzdem so weitermachen";
  function isUnknownFieldValue(text) {
    const raw = String(text || "")
      .trim()
      .toLowerCase()
      .replace(/[.!?]+$/g, "");
    if (!raw) return false;
    const phrases = [
      "keine ahnung",
      "keine idee",
      "kein plan",
      "weiss nicht",
      "weiß nicht",
      "weiss ich nicht",
      "weiß ich nicht",
      "weiss ich noch nicht",
      "weiß ich noch nicht",
      "ich weiss nicht",
      "ich weiß nicht",
      "ich weiss es nicht",
      "ich weiß es nicht",
      "ich weiss es noch nicht",
      "ich weiß es noch nicht",
      "unbekannt",
      "unklar",
      "egal",
    ];
    return phrases.some((phrase) => raw === phrase || raw.startsWith(phrase));
  }

  window.isUnknownFieldValue = isUnknownFieldValue;
  const CLARIFY_PROMPT =
    "Noch etwas konkreter: Was ist heute das Problem — und was soll danach besser laufen?";

  function setIntro(text) {
    const raw = String(text || "").trim();
    if (!raw) {
      intro.hidden = true;
      introText.textContent = "";
      return;
    }
    introText.textContent = raw;
    intro.hidden = false;
  }

  let stepIndex = 0;
  const values = {};
  const labels = {};
  let editingKey = null;
  let kindLocked = false;
  let autoFillBusy = false;
  let overviewGen = 0;
  let clarifyDescription = false;
  let forceThinOk = false;
  const jiraUserCache = [];
  const jiraComponentCache = [];
  const jiraOptionCache = {};
  let jiraComponentsPrefetch = null;
  const jiraOptionsPrefetch = {};

  function optionFieldKey(kind) {
    const raw = String(kind || "");
    if (raw.startsWith("option:")) return raw.slice("option:".length);
    return "";
  }

  function isOptionLookup(kind) {
    return Boolean(optionFieldKey(kind));
  }

  function isBrowseLookup(kind) {
    return kind === "components" || isOptionLookup(kind);
  }

  function toLookupItem(row, kind) {
    if (kind === "user") {
      const name = row.name || "";
      const display = row.displayName || name;
      return {
        name,
        displayName: display,
        label: row.label || `${display} (${name})`,
      };
    }
    const name = row.name || row.label || "";
    return { name, label: row.label || name };
  }

  function lookupCache(kind) {
    if (kind === "user") return jiraUserCache;
    if (kind === "components") return jiraComponentCache;
    const field = optionFieldKey(kind);
    if (!field) return [];
    if (!jiraOptionCache[field]) jiraOptionCache[field] = [];
    return jiraOptionCache[field];
  }

  function filterLookupCache(kind, query) {
    const cache = lookupCache(kind);
    const needle = String(query || "").trim().toLowerCase();
    if (!needle) {
      return isBrowseLookup(kind) ? cache.slice() : cache.slice(0, 12);
    }
    const hits = cache.filter((item) => {
      const blob = `${item.label || ""} ${item.name || ""} ${item.displayName || ""}`.toLowerCase();
      return blob.includes(needle) || blob.split(/\s+/).some((part) => part.startsWith(needle));
    });
    return isBrowseLookup(kind) ? hits : hits.slice(0, 12);
  }

  async function prefetchJiraComponents() {
    if (jiraComponentsPrefetch) return jiraComponentsPrefetch;
    jiraComponentsPrefetch = (async () => {
      try {
        const r = await fetch("/api/jira/components?q=&limit=200");
        const body = await r.json().catch(() => ({}));
        if (!r.ok) {
          jiraComponentsPrefetch = null;
          return;
        }
        jiraComponentCache.length = 0;
        for (const row of body.items || []) {
          jiraComponentCache.push(toLookupItem(row, "components"));
        }
      } catch {
        jiraComponentsPrefetch = null;
      }
    })();
    return jiraComponentsPrefetch;
  }

  async function prefetchJiraOptions(fieldKey) {
    const field = String(fieldKey || "").trim();
    if (!field) return;
    if (jiraOptionsPrefetch[field]) return jiraOptionsPrefetch[field];
    jiraOptionsPrefetch[field] = (async () => {
      try {
        const r = await fetch(
          `/api/jira/options?field=${encodeURIComponent(field)}&q=&limit=200&kind=it_request`
        );
        const body = await r.json().catch(() => ({}));
        if (!r.ok) {
          jiraOptionsPrefetch[field] = null;
          return;
        }
        const cache = lookupCache(`option:${field}`);
        cache.length = 0;
        for (const row of body.items || []) {
          cache.push(toLookupItem(row, `option:${field}`));
        }
      } catch {
        jiraOptionsPrefetch[field] = null;
      }
    })();
    return jiraOptionsPrefetch[field];
  }

  void prefetchJiraComponents();

  window.jiraSuggest = async function (kind, query) {
    const needle = String(query || "").trim();
    const optionKey = optionFieldKey(kind);
    if (kind === "components") await prefetchJiraComponents();
    else if (optionKey) await prefetchJiraOptions(optionKey);
    const local = filterLookupCache(kind, needle);
    if (!needle) return local;
    if (optionKey) {
      try {
        const issueKind = ticketKind() === "change_request" ? "change_request" : "it_request";
        const r = await fetch(
          `/api/jira/options?field=${encodeURIComponent(optionKey)}&q=${encodeURIComponent(needle)}&limit=100&kind=${issueKind}`
        );
        const body = await r.json().catch(() => ({}));
        if (!r.ok) return local;
        const remote = (body.items || []).map((row) => toLookupItem(row, kind));
        const cache = lookupCache(kind);
        for (const item of remote) {
          if (!cache.some((c) => c.name === item.name)) cache.push(item);
        }
        return filterLookupCache(kind, needle);
      } catch {
        return local;
      }
    }
    const endpoint = kind === "user" ? "/api/jira/users" : "/api/jira/components";
    const limit = kind === "components" ? 100 : 20;
    try {
      const r = await fetch(
        `${endpoint}?q=${encodeURIComponent(needle)}&limit=${limit}`
      );
      const body = await r.json().catch(() => ({}));
      if (!r.ok) return local;
      const remote = (body.items || []).map((row) => toLookupItem(row, kind));
      const cache = lookupCache(kind);
      for (const item of remote) {
        if (!cache.some((c) => c.name === item.name)) cache.push(item);
      }
      const merged = new Map();
      for (const item of [...local, ...remote]) {
        merged.set(item.name || item.label, item);
      }
      const all = Array.from(merged.values());
      return kind === "components" ? all : all.slice(0, 12);
    } catch {
      return local;
    }
  };

  function ticketContext(skip) {
    const ignore = new Set(skip || []);
    return Object.entries(values)
      .filter(([key, val]) => val && !ignore.has(key))
      .map(([, val]) => val)
      .join("\n");
  }

  function ticketKind() {
    return kindEl.dataset.kind || "open";
  }

  function stepVisible(step) {
    if (!step) return false;
    if (step.onlyKind && ticketKind() !== step.onlyKind) return false;
    return true;
  }

  const KIND_OPTIONS = [
    { kind: "change_request", label: "Change Request" },
    { kind: "it_request", label: "IT Request" },
  ];

  function closeKindDropdown() {
    document.getElementById("kind-dropdown")?.remove();
  }

  function openKindDropdown() {
    closeKindDropdown();
    const drop = document.createElement("div");
    drop.id = "kind-dropdown";
    drop.className = "kind-dropdown";
    drop.setAttribute("role", "listbox");
    drop.setAttribute("aria-label", "Art des Changes");

    KIND_OPTIONS.forEach(({ kind, label }) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "kind-option" + (ticketKind() === kind ? " is-selected" : "");
      btn.textContent = label;
      btn.onclick = () => {
        closeKindDropdown();
        kindLocked = true;
        setKind(label, kind);
      };
      drop.appendChild(btn);
    });

    const hint = document.createElement("p");
    hint.className = "kind-dropdown-hint";
    hint.textContent = "KI erkennt automatisch — hier manuell überschreiben";
    drop.appendChild(hint);

    document.body.appendChild(drop);

    const rect = kindEl.getBoundingClientRect();
    drop.style.top = (rect.bottom + window.scrollY + 6) + "px";
    drop.style.left = rect.left + "px";

    setTimeout(() => {
      document.addEventListener("click", function outsideKind(e) {
        if (!drop.contains(e.target) && e.target !== kindEl) {
          closeKindDropdown();
          document.removeEventListener("click", outsideKind);
        }
      });
    }, 0);
  }

  kindEl.style.cursor = "pointer";
  kindEl.title = "Art manuell ändern";
  kindEl.addEventListener("click", (e) => {
    e.stopPropagation();
    openKindDropdown();
  });

  function setKind(label, kind) {
    kindEl.textContent = label || "Typ offen";
    kindEl.dataset.kind = kind || "open";
    kindEl.dataset.locked = kindLocked ? "1" : "";
    syncKindFields();
    syncJiraButton();
  }

  async function refreshKind() {
    if (kindLocked) return;
    if (!values.description) {
      setKind("Typ offen", "open");
      return;
    }
    const text = ticketContext();
    if (!text) {
      setKind("Typ offen", "open");
      return;
    }
    try {
      const r = await fetch("/api/sessions/kind", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!r.ok) return;
      const body = await r.json();
      setKind(body.label, body.kind);
    } catch {
      /* Typ bleibt */
    }
  }

  function setPriority(label, level) {
    if (!priorityEl) return;
    priorityEl.textContent = "Mittel";
    values.priority = "Mittel";
    priorityEl.dataset.level = "medium";
    priorityCell?.classList.remove("is-editable");
    priorityCell?.classList.add("is-fixed");
    if (priorityCell) {
      priorityCell.title = "Priorität ist fest auf Mittel";
      priorityCell.dataset.key = "priority";
    }
    syncJiraButton();
  }

  function refreshPriority() {
    setPriority("Mittel", "medium");
  }

  function esc(value) {
    return String(value ?? "").replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
    );
  }

  function isoToDe(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || "").trim());
    return m ? `${m[3]}.${m[2]}.${m[1]}` : "";
  }

  function deToIso(value) {
    const s = String(value || "").trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    const m = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(s);
    if (!m) return "";
    return `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
  }

  function stepByKey(key) {
    if (key === "author") return AUTHOR_STEP;
    if (key === "benefit") return BENEFIT_STEP;
    if (key === "reason") return REASON_STEP;
    if (key === "solution") return SOLUTION_STEP;
    if (key === "risks") return RISKS_STEP;
    if (key === "effort_fb") return COST_FB_STEP;
    if (key === "effort_it") return COST_IT_STEP;
    if (key === "costs") return COST_MONEY_STEP;
    if (key === "priority") return PRIORITY_STEP;
    return STEPS.find((item) => item.key === key) || null;
  }

  function isThinDescription(text) {
    const raw = String(text || "").trim();
    if (!raw) return true;
    if (raw.length < THIN_STORY) return true;
    return raw.split(/\s+/).filter(Boolean).length < 12;
  }

  window.ticketIdleUI = function () {
    const row = document.getElementById("choice-row");
    if (row) {
      row.hidden = true;
      row.replaceChildren();
    }
  };

  function currentStep() {
    while (stepIndex < STEPS.length && !stepVisible(STEPS[stepIndex])) {
      stepIndex += 1;
    }
    if (autoFillBusy) return null;
    const step = STEPS[stepIndex] || null;
    if (!step) return null;
    if (step.key === "description" && clarifyDescription) {
      return {
        ...step,
        prompt: CLARIFY_PROMPT,
        choices: [SKIP_THIN],
        keepForm: true,
      };
    }
    return step;
  }

  function autoSteps() {
    const steps = [
      AUTHOR_STEP,
      BENEFIT_STEP,
      REASON_STEP,
      SOLUTION_STEP,
      RISKS_STEP,
      PRIORITY_STEP,
    ];
    return steps;
  }

  function requiredSteps() {
    return STEPS.filter(stepVisible).concat(autoSteps().filter(stepVisible));
  }

  function fieldFilled(step) {
    const raw = String(values[step.key] || "").trim();
    if (!raw) return false;
    if (isUnknownFieldValue(raw)) return true;
    return !/konnte nicht ermittelt werden\.?$/i.test(raw);
  }

  function ticketComplete() {
    if (autoFillBusy) return false;
    if (currentStep()) return false;
    return requiredSteps().every(fieldFilled);
  }

  function finishVisible() {
    return Boolean(ticketFinish && !ticketFinish.hidden);
  }

  function showFinishActions(key, jiraUrl) {
    if (!ticketFinish || !openJiraLink || !newChangeBtn) return;
    jiraBtn.hidden = true;
    ticketFinish.hidden = false;
    if (jiraUrl) {
      openJiraLink.href = jiraUrl;
      openJiraLink.classList.remove("is-disabled");
      openJiraLink.removeAttribute("aria-disabled");
    } else {
      openJiraLink.href = "#";
      openJiraLink.classList.add("is-disabled");
      openJiraLink.setAttribute("aria-disabled", "true");
    }
    setIntro(key ? `Ticket-Nummer: ${key}` : "Change in Jira angelegt");
  }

  function syncJiraButton() {
    if (finishVisible()) return;
    if (autoFillBusy) {
      jiraBtn.hidden = true;
      return;
    }
    const done = !currentStep() && ticketComplete();
    jiraBtn.hidden = !done;
    if (!done) return;
    setIntro("Bitte alle Felder noch einmal prüfen");
    intro.classList.add("field-prompt-in");
  }

  function ensureFieldShell(step) {
    if (step.kind === "headline") {
      headline.dataset.key = step.key;
      return headline;
    }

    if (step.kind === "meta") {
      metaRoot.hidden = false;
      let cell = metaRoot.querySelector(`[data-key="${step.key}"]`);
      if (!cell) {
        cell = document.createElement("div");
        cell.className = "ticket-meta-item";
        cell.dataset.key = step.key;
        cell.innerHTML = `<dt>${esc(step.label)}</dt><dd><span id="ticket-${esc(
          step.key
        )}-value" class="ticket-row-value"></span></dd>`;
        metaRoot.appendChild(cell);
      }
      cell.hidden = false;
      return document.getElementById(`ticket-${step.key}-value`);
    }

    if (step.kind === "overview") {
      overview.hidden = false;
      let row = overviewFields.querySelector(`[data-key="${step.key}"]`);
      if (!row) {
        row = document.createElement("div");
        row.className = "ticket-block";
        if (step.key === "description") row.classList.add("is-lead");
        row.dataset.key = step.key;
        const enhance = step.enhance
          ? `<button type="button" class="ai-enhance ticket-ai" data-enhance="${esc(
              step.key
            )}" hidden>mit KI aufwerten</button>`
          : "";
        row.innerHTML = `<dt>${esc(step.label)}</dt><dd><span id="ticket-${esc(
          step.key
        )}-value" class="ticket-row-value ticket-prose"></span>${enhance}</dd>`;
        overviewFields.appendChild(row);
      }
      row.hidden = false;
      return document.getElementById(`ticket-${step.key}-value`);
    }

    if (step.kind === "team") {
      team.hidden = false;
      let cell = teamFields.querySelector(`[data-key="${step.key}"]`);
      if (!cell) {
        cell = document.createElement("div");
        cell.className = "ticket-meta-item";
        cell.dataset.key = step.key;
        cell.innerHTML = `<dt>${esc(step.label)}</dt><dd><span id="ticket-${esc(
          step.key
        )}-value" class="ticket-row-value"></span></dd>`;
        teamFields.appendChild(cell);
      }
      cell.hidden = false;
      return document.getElementById(`ticket-${step.key}-value`);
    }

    if (step.kind === "cost") {
      costs.hidden = false;
      let cell = costFields.querySelector(`[data-key="${step.key}"]`);
      if (!cell) {
        cell = document.createElement("div");
        cell.className = "ticket-meta-item";
        cell.dataset.key = step.key;
        cell.innerHTML = `<dt>${esc(step.label)}</dt><dd><span id="ticket-${esc(
          step.key
        )}-value" class="ticket-row-value"></span></dd>`;
        costFields.appendChild(cell);
      }
      cell.hidden = false;
      return document.getElementById(`ticket-${step.key}-value`);
    }

    let row = fieldsRoot.querySelector(`.ticket-row[data-key="${step.key}"]`);
    if (!row) {
      row = document.createElement("div");
      row.className = "ticket-row";
      row.dataset.key = step.key;
      row.innerHTML = `<dt>${esc(step.label)}</dt><dd><span id="ticket-${esc(
        step.key
      )}-value" class="ticket-row-value"></span></dd>`;
      fieldsRoot.appendChild(row);
    }
    row.hidden = false;
    return document.getElementById(`ticket-${step.key}-value`);
  }

  function revealCurrentField() {
    const step = currentStep();
    if (!step || step.kind === "headline") return;
    ensureFieldShell(step);
  }

  function fieldHost(step) {
    if (step.kind === "headline") return headline;
    if (step.kind === "priority") return priorityEl;
    return document.getElementById(`ticket-${step.key}-value`);
  }

  function fieldCell(step) {
    if (step.kind === "headline") return headline;
    if (step.kind === "priority") return priorityCell;
    if (step.kind === "meta") {
      return metaRoot.querySelector(`[data-key="${step.key}"]`);
    }
    if (step.kind === "overview") {
      return overviewFields.querySelector(`[data-key="${step.key}"]`);
    }
    if (step.kind === "team") {
      return teamFields.querySelector(`[data-key="${step.key}"]`);
    }
    if (step.kind === "cost") {
      return costFields.querySelector(`[data-key="${step.key}"]`);
    }
    return fieldsRoot.querySelector(`.ticket-row[data-key="${step.key}"]`);
  }

  function showAuthor() {
    const actor = window.currentActor || {};
    const id = String(actor.jiraName || actor.externalSubject || "").trim();
    const label = String(
      actor.displayName || window.currentActorName || ""
    ).trim();
    const stored = id || label;
    if (stored) setLookupValue("author", stored, label || stored);
    const el = ensureFieldShell(AUTHOR_STEP);
    if (el && (label || stored)) el.textContent = label || stored;
    const cell = fieldCell(AUTHOR_STEP);
    cell?.classList.add("is-done");
    armEdit(AUTHOR_STEP);
  }

  function syncKindFields() {
    const showIt = ticketKind() === "it_request";

    // Verantwortliche Person aus der IT + Solution Owner
    for (const key of ["it_owner", "solution_owner"]) {
      const cell = teamFields.querySelector(`[data-key="${key}"]`);
      if (cell) cell.hidden = !showIt;
      else if (showIt) {
        const idx = STEPS.findIndex((item) => item.key === key);
        if (idx !== -1 && stepIndex > idx) {
          ensureFieldShell(stepByKey(key));
          armEdit(stepByKey(key));
        }
      }
    }

    // Solution Category + Solution entfallen

    // IT-Aufwand
    const itCell = costFields.querySelector('[data-key="effort_it"]');
    if (itCell) itCell.hidden = !showIt;
    else if (showIt && !costs.hidden) {
      ensureFieldShell(COST_IT_STEP);
      armEdit(COST_IT_STEP);
    }
  }

  function displayFor(key) {
    return labels[key] || values[key] || "";
  }

  function setLookupValue(key, name, label) {
    const id = String(name || "").trim();
    const shown = String(label || name || "").trim();
    if (id) values[key] = id;
    else delete values[key];
    if (shown) labels[key] = shown;
    else delete labels[key];
  }

  function setEnhanceVisible(step, on) {
    const host = fieldCell(step);
    const btn = host?.querySelector(".ticket-ai");
    if (!btn) return;
    btn.hidden = !on;
    if (!on) {
      btn.textContent = "mit KI aufwerten";
      btn.disabled = false;
    }
  }

  function armEdit(step) {
    const host = fieldCell(step) || (step.kind === "headline" ? headline : null);
    if (!host) return;
    host.classList.add("is-editable");
    host.dataset.key = step.key;
  }

  function readValue(el) {
    return String(el?.innerText || el?.textContent || "")
      .replace(/\u00a0/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function clearFieldExtras(valueEl) {
    if (valueEl?._lookupAbort) {
      valueEl._lookupAbort.abort();
      valueEl._lookupAbort = null;
    }
    const parent = valueEl.parentElement;
    parent?.querySelector(".field-edit-chips")?.remove();
    parent?.querySelector(".field-edit-cal")?.remove();
    parent?.querySelector(".field-edit-lookup")?.remove();
    valueEl.hidden = false;
  }

  function cancelEdit() {
    if (!editingKey) return;
    const step = stepByKey(editingKey);
    const valueEl = fieldHost(step);
    if (valueEl) {
      valueEl.textContent = displayFor(editingKey);
      valueEl.contentEditable = "false";
      valueEl.classList.remove("is-editing");
      clearFieldExtras(valueEl);
    }
    setEnhanceVisible(step, false);
    editingKey = null;
  }

  function commitEdit() {
    if (!editingKey) return;
    const step = stepByKey(editingKey);
    const valueEl = fieldHost(step);
    const key = editingKey;
    editingKey = null;
    if (!valueEl) return;
    const parent = valueEl.parentElement;
    const cal = parent?.querySelector(".field-edit-cal");
    let text = "";
    if (step?.date) {
      text = cal?.dataset.picked
        ? isoToDe(cal.dataset.picked) || values[key] || ""
        : values[key] || "";
    } else if (step?.choices?.length && valueEl.hidden) {
      text = values[key] || "";
    } else {
      text = readValue(valueEl) || displayFor(key) || "";
    }
    valueEl.contentEditable = "false";
    valueEl.classList.remove("is-editing");
    clearFieldExtras(valueEl);
    if (step?.jiraLookup) {
      const prevName = values[key] || "";
      const prevLabel = labels[key] || "";
      if (text && (text === prevLabel || text === prevName)) {
        valueEl.textContent = prevLabel || prevName || text;
      } else if (text) {
        setLookupValue(key, text, text);
        valueEl.textContent = text;
      } else {
        delete values[key];
        delete labels[key];
        valueEl.textContent = "";
      }
    } else {
      valueEl.textContent = text;
      if (text) values[key] = text;
      else delete values[key];
    }
    setEnhanceVisible(step, false);
    if (key === "effort_fb" || key === "effort_it") {
      void reviewEffort();
    }
    void refreshPriority();
    void refreshKind();
    syncJiraButton();
  }

  const resolveCache = new Map();

  async function resolveJiraLookup(kind, value) {
    const optionKey = optionFieldKey(kind);
    const key = `${kind}:${String(value || "").trim().toLowerCase()}`;
    if (resolveCache.has(key)) return resolveCache.get(key);
    const pending = (async () => {
      const r = await fetch("/api/jira/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          optionKey
            ? { kind: "option", field: optionKey, value }
            : { kind, value }
        ),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || "Jira-Lookup fehlgeschlagen");
      return body;
    })();
    resolveCache.set(key, pending);
    try {
      return await pending;
    } catch (err) {
      resolveCache.delete(key);
      throw err;
    }
  }

  function renderFieldChips(step, valueEl) {
    clearFieldExtras(valueEl);
    valueEl.hidden = true;
    const row = document.createElement("div");
    row.className = "choice-row field-edit-chips";
    step.choices.forEach((value) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "suggestion";
      chip.textContent = value;
      if (value === values[step.key]) chip.classList.add("is-selected");
      chip.onclick = () => {
        if (step.key === "priority") {
          editingKey = null;
          clearFieldExtras(valueEl);
          refreshPriority();
          return;
        }
        values[step.key] = value;
        valueEl.textContent = value;
        editingKey = null;
        clearFieldExtras(valueEl);
        void refreshPriority();
        void refreshKind();
        syncJiraButton();
      };
      row.appendChild(chip);
    });
    valueEl.insertAdjacentElement("afterend", row);
  }

  function renderJiraLookup(step, valueEl) {
    clearFieldExtras(valueEl);
    const isTags = step.jiraLookup === "components" || Boolean(step.multi);

    // Stichwörter / Tags: Chips ohne Suchfeld.
    if (isTags) {
      valueEl.hidden = false;
      valueEl.contentEditable = "false";
      valueEl.classList.remove("is-editing");
      if (!readValue(valueEl) && displayFor(step.key)) {
        valueEl.textContent = displayFor(step.key);
      }
      const wrap = document.createElement("div");
      wrap.className = "field-edit-lookup";
      wrap.addEventListener("mousedown", (ev) => ev.stopPropagation());
      if (step.hint) {
        const hint = document.createElement("p");
        hint.className = "field-tags-hint";
        hint.textContent = step.hint;
        wrap.appendChild(hint);
      }
      const list = document.createElement("div");
      list.className = "field-lookup-list";
      wrap.appendChild(list);
      valueEl.insertAdjacentElement("afterend", wrap);

      function selectedComponents() {
        return String(values[step.key] || labels[step.key] || "")
          .split(/[,;]/)
          .map((part) => part.trim())
          .filter(Boolean);
      }

      function pick(item) {
        const label = item.label || item.displayName || item.name || "";
        const name = item.name || label;
        const current = selectedComponents();
        const key = name.toLowerCase();
        const next = current.some((part) => part.toLowerCase() === key)
          ? current.filter((part) => part.toLowerCase() !== key)
          : [...current, name];
        const joined = next.join(", ");
        if (joined) {
          setLookupValue(step.key, joined, joined);
          valueEl.textContent = joined;
        } else {
          delete values[step.key];
          delete labels[step.key];
          valueEl.textContent = "";
        }
        void loadSuggestions("").then((items) => {
          if (editingKey !== step.key) return;
          renderList(items);
        });
        syncJiraButton();
      }

      async function loadSuggestions(query) {
        if (!window.jiraSuggest) {
          return filterLookupCache(step.jiraLookup, query);
        }
        try {
          return await window.jiraSuggest(step.jiraLookup, query);
        } catch {
          return filterLookupCache(step.jiraLookup, query);
        }
      }

      function renderList(items) {
        list.innerHTML = "";
        if (!items.length) {
          const empty = document.createElement("span");
          empty.className = "field-lookup-empty";
          empty.textContent = "Keine Stichwörter / Tags geladen";
          list.appendChild(empty);
          return;
        }
        const selected = new Set(
          selectedComponents().map((part) => part.toLowerCase())
        );
        items.forEach((item) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "suggestion field-lookup-item";
          btn.textContent = item.label || item.name;
          const key = String(item.name || item.label || "").toLowerCase();
          if (selected.has(key)) btn.classList.add("is-selected");
          btn.onclick = (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            pick(item);
          };
          list.appendChild(btn);
        });
      }

      void loadSuggestions("").then((items) => {
        if (editingKey !== step.key) return;
        renderList(items);
      });
      return;
    }

    valueEl.hidden = false;
    valueEl.contentEditable = "true";
    valueEl.classList.add("is-editing");
    if (!readValue(valueEl) && displayFor(step.key)) {
      valueEl.textContent = displayFor(step.key);
    }
    const wrap = document.createElement("div");
    wrap.className = "field-edit-lookup";
    wrap.addEventListener("mousedown", (ev) => ev.stopPropagation());
    if (step.choices?.length) {
      const chips = document.createElement("div");
      chips.className = "choice-row field-edit-chips";
      step.choices.forEach((value) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "suggestion";
        chip.textContent = value;
        if (value === values[step.key] || (isUnknownFieldValue(value) && isUnknownFieldValue(values[step.key]))) {
          chip.classList.add("is-selected");
        }
        chip.onclick = (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          values[step.key] = value;
          delete labels[step.key];
          valueEl.textContent = value;
          valueEl.contentEditable = "false";
          valueEl.classList.remove("is-editing");
          editingKey = null;
          clearFieldExtras(valueEl);
          void refreshPriority();
          void refreshKind();
          syncJiraButton();
        };
        chips.appendChild(chip);
      });
      wrap.appendChild(chips);
    }
    const list = document.createElement("div");
    list.className = "field-lookup-list";
    wrap.appendChild(list);
    valueEl.insertAdjacentElement("afterend", wrap);

    let timer = 0;
    let requestId = 0;
    const ac = new AbortController();
    valueEl._lookupAbort = ac;

    async function loadSuggestions(query) {
      if (!window.jiraSuggest) {
        return filterLookupCache(step.jiraLookup, query);
      }
      try {
        return await window.jiraSuggest(step.jiraLookup, query);
      } catch {
        return filterLookupCache(step.jiraLookup, query);
      }
    }

    function pick(item) {
      const label = item.label || item.displayName || item.name || "";
      const name = item.name || label;
      setLookupValue(step.key, name, label);
      valueEl.textContent = label;
      valueEl.contentEditable = "false";
      valueEl.classList.remove("is-editing");
      editingKey = null;
      clearFieldExtras(valueEl);
      void refreshPriority();
      void refreshKind();
      syncJiraButton();
    }

    function renderList(items) {
      list.innerHTML = "";
      const query = readValue(valueEl);
      if (!items.length) {
        const empty = document.createElement("span");
        empty.className = "field-lookup-empty";
        empty.textContent = query
          ? "Keine Treffer in Jira — Enter speichert Freitext"
          : step.jiraLookup === "user"
            ? "Name tippen — Jira schlägt vor"
            : isOptionLookup(step.jiraLookup)
              ? "Keine Optionen geladen"
              : "Keine Treffer";
        list.appendChild(empty);
        return;
      }
      const shown = isBrowseLookup(step.jiraLookup)
        ? items
        : items.slice(0, 12);
      shown.forEach((item) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "suggestion field-lookup-item";
        btn.textContent = item.label || item.name;
        btn.onclick = (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          pick(item);
        };
        list.appendChild(btn);
      });
    }

    function scheduleSuggest() {
      const query = readValue(valueEl);
      renderList(filterLookupCache(step.jiraLookup, query));
      window.clearTimeout(timer);
      const current = ++requestId;
      timer = window.setTimeout(async () => {
        const items = await loadSuggestions(query);
        if (current !== requestId || editingKey !== step.key) return;
        renderList(items);
      }, 120);
    }

    valueEl.addEventListener("input", scheduleSuggest, { signal: ac.signal });
    void loadSuggestions(readValue(valueEl)).then((items) => {
      if (editingKey !== step.key) return;
      renderList(items);
    });
    window.setTimeout(() => {
      if (editingKey !== step.key) return;
      valueEl.focus();
      const range = document.createRange();
      range.selectNodeContents(valueEl);
      range.collapse(false);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
    }, 0);
  }

  function renderDatePicker(step, valueEl) {
    clearFieldExtras(valueEl);
    if (typeof window.mountCalendar !== "function") {
      valueEl.hidden = false;
      valueEl.contentEditable = "true";
      valueEl.classList.add("is-editing");
      valueEl.focus();
      return;
    }
    valueEl.hidden = true;
    const cal = document.createElement("div");
    cal.className = "cal field-edit-cal";
    cal.addEventListener("mousedown", (ev) => ev.stopPropagation());
    window.mountCalendar(cal, {
      value: deToIso(values[step.key]),
      onPick: (iso) => {
        const text = isoToDe(iso);
        if (!text) return;
        cal.dataset.picked = iso;
        values[step.key] = text;
        valueEl.textContent = text;
        editingKey = null;
        clearFieldExtras(valueEl);
        void refreshPriority();
        void refreshKind();
        syncJiraButton();
      },
    });
    valueEl.insertAdjacentElement("afterend", cal);
  }

  function startEdit(key) {
    if (key === "priority") return;
    if (key === "effort_fb" || key === "effort_it") return;
    const step = stepByKey(key);
    if (!step) return;
    const host = fieldCell(step);
    if (!host) return;
    if (!host.classList.contains("is-editable")) armEdit(step);
    if (host.classList.contains("is-pending")) return;
    if (editingKey === key) {
      const valueEl = fieldHost(step);
      if (valueEl?.isContentEditable) valueEl.focus();
      return;
    }
    commitEdit();
    const valueEl = fieldHost(step);
    if (!valueEl) return;
    editingKey = key;
    setEnhanceVisible(step, Boolean(step.enhance));
    if (step.choices?.length && step.jiraLookup) {
      renderJiraLookup(step, valueEl);
      return;
    }
    if (step.choices?.length) {
      renderFieldChips(step, valueEl);
      return;
    }
    if (step.jiraLookup) {
      renderJiraLookup(step, valueEl);
      return;
    }
    if (step.date) {
      renderDatePicker(step, valueEl);
      return;
    }
    valueEl.contentEditable = "true";
    valueEl.classList.add("is-editing");
    valueEl.focus();
    const range = document.createRange();
    range.selectNodeContents(valueEl);
    range.collapse(false);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
  }

  async function polishKey(key, btn) {
    const step = stepByKey(key);
    if (!step?.enhance) return;
    const valueEl = fieldHost(step);
    const text = (readValue(valueEl) || values[key] || "").trim();
    if (text) values[key] = text;
    const idle = "mit KI aufwerten";
    if (!text) {
      btn.textContent = "Erst Text eingeben";
      setTimeout(() => {
        btn.textContent = idle;
      }, 1400);
      return;
    }
    btn.disabled = true;
    btn.textContent = "KI arbeitet…";
    try {
      if (typeof window.polishText !== "function") throw new Error("KI fehlt");
      const next = await window.polishText(text, key);
      values[key] = next;
      if (valueEl) {
        valueEl.textContent = next;
        if (editingKey === key) {
          valueEl.contentEditable = "true";
          valueEl.classList.add("is-editing");
        }
      }
      btn.textContent = "Überarbeitet";
      if (key === "description") {
        await fillAutoOverview(true);
      }
      void refreshPriority();
      void refreshKind();
      syncJiraButton();
    } catch {
      btn.textContent = "KI fehlgeschlagen";
    }
    setTimeout(() => {
      btn.textContent = idle;
      btn.disabled = false;
    }, 1600);
  }

  function syncPrompt() {
    const step = currentStep();
    document.body.classList.toggle(
      "field-flow",
      Boolean(step) || clarifyDescription
    );

    if (!step) {
      if (finishVisible()) {
        window.syncTicketInput?.();
        return;
      }
      if (ticketComplete()) {
        setIntro("Bitte alle Felder noch einmal prüfen");
        intro.classList.add("field-prompt-in");
        jiraBtn.hidden = false;
      } else {
        jiraBtn.hidden = true;
        setIntro("Bitte alle offenen Felder im Ticket ausfüllen");
        intro.classList.add("field-prompt-in");
      }
      window.syncTicketInput?.();
      return;
    }

    if (!finishVisible()) jiraBtn.hidden = true;
    revealCurrentField();
    setIntro(step.prompt);
    intro.classList.remove("field-prompt-in");
    void intro.offsetWidth;
    intro.classList.add("field-prompt-in");
    window.syncTicketInput?.();
  }

  window.getTicketStep = currentStep;
  window.ticketSnapshot = function () {
    return {
      title: values.title || "",
      kind: ticketKind(),
      fields: { ...values },
    };
  };

  window.prepareTicketField = function (text) {
    const step = currentStep();
    if (!step) return null;

    ticket.hidden = false;
    document.body.classList.add("ticket-active");
    showAuthor();
    refreshPriority();
    showFiles();

    const valueEl = ensureFieldShell(step);
    if (!valueEl) return null;

    // Skip-Chip: dünne Beschreibung belassen, trotzdem weiter.
    if (
      step.key === "description" &&
      clarifyDescription &&
      String(text || "").trim() === SKIP_THIN
    ) {
      forceThinOk = true;
      clarifyDescription = false;
      const kept = String(values.description || "").trim();
      valueEl.textContent = kept;
      valueEl.classList.remove("ticket-row-value-pending");
      valueEl.classList.add("ticket-row-value-in");
      return valueEl;
    }

    const cell = fieldCell(step);
    cell?.classList.add("is-pending");

    if (step.kind === "headline") {
      headline.hidden = false;
      headline.classList.add("is-pending");
    }

    valueEl.textContent = text;
    valueEl.classList.remove("ticket-row-value-in");
    valueEl.classList.add("ticket-row-value-pending");
    values[step.key] = text;
    return valueEl;
  };

  window.showTicketField = function () {
    const step = currentStep();
    if (!step) return;

    const valueEl = fieldHost(step);
    const cell = fieldCell(step);
    valueEl?.classList.remove("ticket-row-value-pending");
    valueEl?.classList.add("ticket-row-value-in");
    cell?.classList.remove("is-pending");
    cell?.classList.add("is-done");

    if (step.kind === "headline") {
      headline.classList.remove("is-pending");
      headline.classList.add("is-done");
    }

    if (
      step.key === "description" &&
      !forceThinOk &&
      isThinDescription(values.description)
    ) {
      clarifyDescription = true;
      forceThinOk = false;
      cell?.classList.add("is-incomplete");
      armEdit(step);
      void refreshPriority();
      void refreshKind();
      syncPrompt();
      return;
    }

    if (step.key === "description") {
      clarifyDescription = false;
      forceThinOk = false;
      cell?.classList.remove("is-incomplete");
    }

    armEdit(step);
    stepIndex += 1;
    void refreshPriority();
    void refreshKind();
    if (step.key === "description") {
      autoFillBusy = true;
      window.syncTicketInput?.();
      void fillAutoOverview(false)
        .catch(() => {})
        .finally(() => {
          autoFillBusy = false;
          syncPrompt();
        });
      return;
    }
    syncPrompt();
  };

  async function fillAutoField(shell, url, loading, extra, forceOverwrite = false) {
    setIntro(loading);
    window.syncTicketInput?.();
    const fail = `${shell.label} konnte nicht ermittelt werden.`;
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: values.description,
          title: values.title || "",
          ...extra,
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || "KI fehlgeschlagen");
      const text = String(body.text || "").trim();
      if (!text) throw new Error("leer");
      writeAutoField(shell, text, forceOverwrite);
    } catch {
      writeAutoField(shell, fail, forceOverwrite || !values[shell.key]);
    }
  }

  async function fillOverviewFallback(forceOverwrite = false) {
    await fillAutoField(
      BENEFIT_STEP,
      "/api/sessions/benefit",
      "KI ermittelt den Nutzen…",
      {},
      forceOverwrite
    );
    await fillAutoField(
      REASON_STEP,
      "/api/sessions/reason",
      "KI ermittelt die Begründung…",
      { benefit: values.benefit || "" },
      forceOverwrite
    );
    await fillAutoField(
      SOLUTION_STEP,
      "/api/sessions/solution",
      "KI ermittelt die Lösung…",
      { benefit: values.benefit || "", reason: values.reason || "" },
      forceOverwrite
    );
    await fillAutoField(
      RISKS_STEP,
      "/api/sessions/risks",
      "KI recherchiert bekannte Risiken…",
      {
        benefit: values.benefit || "",
        reason: values.reason || "",
        solution: values.solution || "",
      },
      forceOverwrite
    );
  }

  function writeAutoField(shell, text, forceOverwrite = false) {
    const el = ensureFieldShell(shell);
    if (!el) return;
    const existing = String(values[shell.key] || "").trim();
    if (existing && !forceOverwrite && !/konnte nicht ermittelt werden\.?$/i.test(existing)) {
      return;
    }
    const value = String(text || "").trim() || `${shell.label} konnte nicht ermittelt werden.`;
    el.textContent = value;
    values[shell.key] = value;
    const cell = fieldCell(shell);
    el.classList.add("ticket-row-value-in");
    cell?.classList.remove("is-pending");
    cell?.classList.add("is-done");
    armEdit(shell);
  }

  async function fillAutoOverview(forceOverwrite = false) {
    if (!values.description) return;
    const gen = ++overviewGen;
    setIntro("KI recherchiert Risiken und schreibt die Übersicht…");
    window.syncTicketInput?.();
    try {
      const r = await fetch("/api/sessions/overview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: values.description,
          title: values.title || "",
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || "KI fehlgeschlagen");
      if (gen !== overviewGen) return;
      writeAutoField(BENEFIT_STEP, body.benefit, forceOverwrite);
      writeAutoField(REASON_STEP, body.reason, forceOverwrite);
      writeAutoField(SOLUTION_STEP, body.solution, forceOverwrite);
      writeAutoField(RISKS_STEP, body.risks, forceOverwrite);
    } catch {
      if (gen !== overviewGen) return;
      await fillOverviewFallback(forceOverwrite);
    }
    if (gen !== overviewGen) return;
    await refreshKind();
    prepareCostFields();
    if (gen !== overviewGen) return;
    await refreshPriority();
    if (!autoFillBusy) {
      syncPrompt();
    }
  }

  function parsePt(text) {
    const m = String(text || "")
      .replace(",", ".")
      .match(/(\d+(?:\.\d+)?)/);
    return m ? Number(m[1]) : 0;
  }

  function writeCostField(step, text, forceOverwrite = false) {
    const el = ensureFieldShell(step);
    if (!el) return;
    const existing = String(values[step.key] || "").trim();
    if (
      existing &&
      !forceOverwrite &&
      !/konnte nicht ermittelt werden\.?$/i.test(existing)
    ) {
      return;
    }
    const value = String(text || "").trim();
    el.textContent = value;
    if (value) values[step.key] = value;
    else delete values[step.key];
    const cell = fieldCell(step);
    el.classList.add("ticket-row-value-in");
    cell?.classList.remove("is-pending");
    cell?.classList.add("is-done");
    if (step.key !== "effort_fb" && step.key !== "effort_it") armEdit(step);
  }

  function costHintEl() {
    return document.querySelector("#ticket-costs .ticket-section-hint");
  }

  /** Aufwand kommt aus der Sheets-Vorlage, nicht per Zahlentippen. */
  function prepareCostFields() {
    ensureFieldShell(COST_FB_STEP);
    const fbCell = fieldCell(COST_FB_STEP);
    fbCell?.classList.add("is-readonly");
    if (ticketKind() === "it_request") {
      ensureFieldShell(COST_IT_STEP);
      fieldCell(COST_IT_STEP)?.classList.add("is-readonly");
    }
    ensureFieldShell(COST_MONEY_STEP);
    fieldCell(COST_MONEY_STEP)?.classList.add("is-readonly");
    const hintEl = costHintEl();
    if (hintEl && !parsePt(values.effort_fb) && !parsePt(values.effort_it)) {
      hintEl.textContent = "Google Sheet öffnen, ausfüllen, Fenster schließen — Aufwand wird übernommen.";
    }
    showEffortSheetLink(values.effort_sheet_url);
    syncKindFields();
  }

  function showEffortSheetLink(url) {
    const href = String(url || "").trim();
    const anchor = effortSheetLink?.querySelector("a");
    if (!effortSheetLink || !anchor) return;
    if (!href) {
      effortSheetLink.hidden = true;
      return;
    }
    anchor.href = href;
    anchor.textContent = href;
    effortSheetLink.hidden = false;
  }

  function applyEffortSheet(body) {
    writeCostField(COST_FB_STEP, body.effort_fb || "", true);
    if (ticketKind() === "it_request") {
      writeCostField(COST_IT_STEP, body.effort_it || "", true);
    }
    if (body.costs) writeCostField(COST_MONEY_STEP, body.costs, true);
    ["effort_sheet_url", "concept_scs_pt", "concept_cit_pt", "operate_scs_pt", "operate_cit_pt"].forEach(
      (key) => {
        const val = String(body[key] || "").trim();
        if (val) values[key] = val;
        else delete values[key];
      }
    );
    showEffortSheetLink(values.effort_sheet_url);
    const hintEl = costHintEl();
    if (hintEl) {
      hintEl.textContent = body.effort_fb
        ? `Übernommen: ${body.effort_fb}${ticketKind() === "it_request" && body.effort_it ? ` / ${body.effort_it}` : ""}.`
        : "Tabelle gelesen — keine PT-Summen gefunden.";
    }
    void reviewEffort();
    syncJiraButton();
  }

  async function importEffortSheet(url) {
    const href = String(url || "").trim();
    if (!href) throw new Error("Keine Sheet-URL");
    const hintEl = costHintEl();
    if (hintEl) hintEl.textContent = "Übernehme Aufwand…";
    const r = await fetch("/api/sessions/effort-sheet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: href }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail || "Übernahme fehlgeschlagen");
    applyEffortSheet(body);
  }

  async function loadEffortSheetSettings() {
    try {
      const r = await fetch("/api/settings");
      const body = await r.json().catch(() => ({}));
      effortSheetTemplateUrl = String(body.jira?.effortSheetTemplateUrl || "").trim();
      effortSheetOpenUrl = String(body.jira?.effortSheetOpenUrl || effortSheetTemplateUrl).trim();
    } catch {
      effortSheetTemplateUrl = "";
    }
  }

  function openEffortTemplate() {
    const url = effortSheetOpenUrl || effortSheetTemplateUrl;
    if (!url) {
      const hintEl = costHintEl();
      if (hintEl) {
        hintEl.textContent = "Unter Einstellungen die Google-Sheets-Vorlage eintragen.";
      }
      return;
    }
    const popup = window.open(url, "critrEffortSheet", "popup=yes,width=1280,height=800");
    if (!popup) {
      const hintEl = costHintEl();
      if (hintEl) hintEl.textContent = "Popup blockiert — bitte Popups erlauben.";
      return;
    }
    const timer = setInterval(() => {
      if (popup && !popup.closed) return;
      clearInterval(timer);
      importEffortSheet(effortSheetTemplateUrl || url).catch((err) => {
        const hintEl = costHintEl();
        if (hintEl) hintEl.textContent = err.message || "Sheet konnte nicht übernommen werden.";
      });
    }, 250);
  }

  /** KI prüft Nutzer-PT, sucht online und schlägt Spanne + Begründung vor. */
  async function reviewEffort() {
    if (!values.description) return;
    const fbRaw = String(values.effort_fb || "").trim();
    const itRaw = String(values.effort_it || "").trim();
    if (!parsePt(fbRaw) && !parsePt(itRaw)) return;
    if (/konnte nicht ermittelt werden\.?$/i.test(fbRaw)) return;

    const hintEl = costHintEl();
    if (hintEl) {
      hintEl.textContent =
        "KI sucht vergleichbare Projekte und schätzt eine Spanne aus der Beschreibung…";
    }
    try {
      const r = await fetch("/api/sessions/effort", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: values.description,
          title: values.title || "",
          kind: ticketKind(),
          fb: fbRaw,
          it: ticketKind() === "it_request" ? itRaw : "",
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || "Prüfung fehlgeschlagen");
      if (hintEl) {
        hintEl.textContent = body.hint || "Spanne — bitte prüfen";
      }
    } catch {
      if (hintEl) {
        hintEl.textContent = "Prüfung nicht möglich — Angabe bitte selbst gegenprüfen.";
      }
    }
  }

  ticket.addEventListener("click", (event) => {
    const btn = event.target.closest(".ticket-ai");
    if (btn) {
      event.preventDefault();
      event.stopPropagation();
      void polishKey(btn.dataset.enhance, btn);
      return;
    }
    const host = event.target.closest(".is-editable");
    if (!host || host.classList.contains("is-pending")) return;
    if (event.target.closest(".field-edit-chips, .field-edit-lookup, .suggestion, .cal")) return;
    const key = host.dataset.key;
    if (key) startEdit(key);
  });

  ticket.addEventListener("keydown", (event) => {
    if (!editingKey) return;
    if (event.target.closest(".field-edit-lookup, .field-edit-chips, .field-edit-cal, .cal")) {
      return;
    }
    const step = stepByKey(editingKey);
    if (event.key === "Escape") {
      event.preventDefault();
      cancelEdit();
      return;
    }
    if (event.key === "Enter" && !event.shiftKey && !step?.long) {
      event.preventDefault();
      commitEdit();
    }
  });

  document.addEventListener("mousedown", (event) => {
    if (!editingKey) return;
    const step = stepByKey(editingKey);
    if (
      event.target.closest(
        ".is-editing, .field-edit-chips, .field-edit-lookup, .field-edit-cal, .cal, .ticket-ai"
      )
    ) {
      return;
    }
    if (step?.date) {
      cancelEdit();
      return;
    }
    commitEdit();
  });

  const attachments = [];
  let fileSeq = 0;
  const MAX_FILE = 20 * 1024 * 1024;

  function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    const mb = bytes / (1024 * 1024);
    const digits = mb >= 10 ? 0 : 1;
    return `${mb.toFixed(digits).replace(".", ",")} MB`;
  }

  function renderFiles() {
    fileList.innerHTML = attachments
      .map(
        (item) =>
          `<li class="ticket-file" data-id="${esc(item.id)}"><span class="ticket-file-name">${esc(
            item.name
          )}</span><span class="ticket-file-size">${esc(
            item.sizeLabel
          )}</span><button type="button" class="ticket-file-remove" data-remove="${esc(
            item.id
          )}">entfernen</button></li>`
      )
      .join("");
  }

  function showFiles() {
    filesSection.hidden = false;
    renderFiles();
  }

  function addFiles(list) {
    Array.from(list || []).forEach((file) => {
      if (!file) return;
      if (file.size > MAX_FILE) {
        flash(`${file.name} zu groß (max. 20 MB)`, true);
        return;
      }
      const key = `${file.name}:${file.size}:${file.lastModified}`;
      if (attachments.some((item) => item.key === key)) return;
      fileSeq += 1;
      attachments.push({
        id: String(fileSeq),
        key,
        name: file.name,
        sizeLabel: formatSize(file.size),
        file,
      });
    });
    renderFiles();
    fileInput.value = "";
  }

  fileAdd.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => addFiles(fileInput.files));
  fileList.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-remove]");
    if (!btn) return;
    const id = btn.dataset.remove;
    const idx = attachments.findIndex((item) => item.id === id);
    if (idx >= 0) attachments.splice(idx, 1);
    renderFiles();
  });

  syncPrompt();

  (window.whenAuthed || Promise.resolve()).then((user) => {
    window.currentActor = user || window.currentActor;
    const name = String(user?.displayName || "").trim();
    window.currentActorName = name;
    if ((user?.jiraName || name) && !ticket.hidden) showAuthor();
  });

  let publishing = false;

  function flash(message, err) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = message;
    el.classList.toggle("err", Boolean(err));
    el.classList.add("show");
    window.clearTimeout(flash.tid);
    flash.tid = window.setTimeout(() => el.classList.remove("show"), 3200);
  }

  function errorDetail(body) {
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((row) => row.msg || row).join("; ");
    }
    return "Anlage fehlgeschlagen";
  }

  async function createViaLegacyPublish(kind, priority, waitSync = true) {
    const fields = { ...values };
    for (const [key, raw] of Object.entries(fields)) {
      if (isUnknownFieldValue(raw)) delete fields[key];
    }
    const r = await fetch("/api/sessions/publish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: values.title,
        kind,
        priority,
        fields,
        waitSync,
      }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(errorDetail(body));
    return body;
  }

  async function normalizeJiraLookupFields() {
    const targets = [
      ["approver", "user"],
      ["lead", "user"],
      ["process_owner", "user"],
      ["solution_owner", "user"],
      ["it_owner", "user"],
      ["author", "user"],
      ["components", "components"],
    ];
    const failed = [];
    await Promise.all(
      targets.map(async ([key, kind]) => {
        const raw = String(values[key] || labels[key] || "").trim();
        if (!raw || isUnknownFieldValue(raw)) return;
        try {
          const body = await resolveJiraLookup(kind, raw);
          if (body.resolved) {
            const id = body.value || body.resolved;
            const label = body.label || body.resolved;
            setLookupValue(key, id, label);
            const step = stepByKey(key);
            const valueEl = step ? fieldHost(step) : null;
            if (valueEl) valueEl.textContent = label;
            return;
          }
          if (kind === "user") failed.push(key);
        } catch {
          if (kind === "user") failed.push(key);
        }
      })
    );
    if (failed.length) {
      throw new Error(
        "Jira-Zuordnung fehlgeschlagen: " +
          failed.map((key) => stepByKey(key)?.label || key).join(", ")
      );
    }
  }

  function showJiraBadge(key, jiraUrl) {
    const badge = document.getElementById("ticket-jira");
    const badgeKey = document.getElementById("ticket-jira-key");
    if (!key || !badge || !badgeKey) return;
    badge.hidden = false;
    badgeKey.textContent = key;
    if (jiraUrl) {
      badgeKey.href = jiraUrl;
      badgeKey.setAttribute("title", `In Jira öffnen: ${key}`);
    } else {
      badgeKey.removeAttribute("href");
      badgeKey.removeAttribute("title");
    }
  }

  async function pollJiraKey(requestId, attempts = 40) {
    for (let i = 0; i < attempts; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 750));
      try {
        const r = await fetch(`/api/requests/${requestId}`);
        const body = await r.json().catch(() => ({}));
        if (!r.ok) continue;
        const sync = body.sync || {};
        if (sync.externalKey) {
          return {
            jiraKey: sync.externalKey,
            reference: body.reference || sync.externalKey,
            jiraUrl: sync.externalUrl || "",
            syncError: sync.lastError || null,
          };
        }
        if (sync.state === "dead" || sync.state === "failed") {
          return {
            jiraKey: null,
            reference: body.reference || null,
            jiraUrl: "",
            syncError: sync.lastError || "Jira-Anlage fehlgeschlagen",
          };
        }
      } catch {
        /* retry */
      }
    }
    return {
      jiraKey: null,
      reference: null,
      jiraUrl: "",
      syncError: "Jira-Sync dauert zu lange",
    };
  }

  jiraBtn.addEventListener("click", async () => {
    if (publishing || jiraBtn.disabled) return;
    if (!values.title || !values.description) {
      flash("Titel und Beschreibung fehlen.", true);
      return;
    }
    if (attachments.length) {
      flash("Anhänge werden noch nicht nach Jira übertragen — nur lokal sichtbar.", true);
    }
    publishing = true;
    jiraBtn.disabled = true;
    jiraBtn.textContent = "Wird angelegt…";
    const kind = ticketKind() === "it_request" ? "it_request" : "change_request";
    const priority = "medium";
    try {
      await normalizeJiraLookupFields();
      const body = await createViaLegacyPublish(kind, priority, false);
      const localRef = body.reference || body.ticketKey || "lokal";
      showJiraBadge(localRef, "");
      setIntro(`${localRef} lokal angelegt — Jira-Nummer folgt…`);
      flash(`${localRef} lokal angelegt`);
      jiraBtn.textContent = "Jira sync…";

      let key = body.jiraKey || body.externalKey || null;
      let jiraUrl = body.jiraUrl || body.externalUrl || "";
      let syncError = body.syncError || null;
      if (!key && body.requestId) {
        const polled = await pollJiraKey(body.requestId);
        key = polled.jiraKey;
        jiraUrl = polled.jiraUrl;
        syncError = polled.syncError;
        if (polled.reference) showJiraBadge(polled.reference, jiraUrl || "");
      }
      if (!key) {
        publishing = false;
        jiraBtn.disabled = false;
        jiraBtn.textContent = "In Jira Anlegen";
        const err = syncError || "Jira-Anlage fehlgeschlagen";
        setIntro(`${localRef}: ${err}`);
        flash(err, true);
        return;
      }
      showJiraBadge(key, jiraUrl);
      showFinishActions(key, jiraUrl);
      flash(`${key} in Jira angelegt`);
    } catch (err) {
      publishing = false;
      jiraBtn.disabled = false;
      jiraBtn.textContent = "In Jira Anlegen";
      flash(String(err.message || err), true);
    }
  });

  newChangeBtn?.addEventListener("click", () => {
    location.assign("/workspace");
  });

  effortSheetOpen?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    openEffortTemplate();
  });
  void loadEffortSheetSettings();
})();
