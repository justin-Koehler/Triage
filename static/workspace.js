(function () {
  const intro = document.getElementById("intro-prompt");
  const introText = document.getElementById("intro-prompt-text");
  const jiraBtn = document.getElementById("jira-create");
  const jiraCreateTicket = document.getElementById("jira-create-ticket");
  const ticketFinish = document.getElementById("ticket-finish");
  const openJiraLink = document.getElementById("ticket-open-jira");
  const openJiraEnd = document.getElementById("ticket-open-jira-end");
  const newChangeBtn = document.getElementById("ticket-new-change");
  const startChangeBtn = document.getElementById("start-change");
  const aiReviewOk = document.getElementById("ai-review-ok");
  const ticket = document.getElementById("ticket");
  const headline = document.getElementById("ticket-headline");
  const metaRoot = document.getElementById("ticket-meta");
  const priorityEl = document.getElementById("ticket-priority");
  const priorityCell = document.getElementById("ticket-priority-cell");
  const kindEl = document.getElementById("ticket-kind");
  const overview = document.getElementById("ticket-overview");
  const overviewFields = document.getElementById("ticket-overview-fields");
  const overviewMeta = document.getElementById("ticket-overview-meta");
  const overviewAiHint = document.getElementById("overview-ai-hint");
  const AI_REVIEW_HINT = "Bitte alles nochmal überprüfen. KI kann Fehler machen.";
  const context = document.getElementById("ticket-context");
  const contextFields = document.getElementById("ticket-context-fields");
  const costs = document.getElementById("ticket-costs");
  const costFields = document.getElementById("ticket-cost-fields");
  const effortSheetOpen = document.getElementById("effort-sheet-open");
  const statusUpdateOpen = document.getElementById("status-update-open");
  let effortSheetTemplateUrl = "";
  let effortSheetOpenUrl = "";
  const team = document.getElementById("ticket-team");
  const teamFields = document.getElementById("ticket-team-fields");
  const solution = document.getElementById("ticket-solution");
  const solutionFields = document.getElementById("ticket-solution-fields");
  const filesSection = document.getElementById("ticket-files");
  const fileList = document.getElementById("ticket-file-list");
  const fileGallery = document.getElementById("ticket-file-gallery");
  const fileEmpty = document.getElementById("ticket-file-empty");
  const fileAdd = document.getElementById("ticket-file-add");
  const fileInput = document.getElementById("ticket-file-input");
  const fileLightbox = document.getElementById("file-lightbox");
  const fileLightboxImg = document.getElementById("file-lightbox-img");
  const fileLightboxCaption = document.getElementById("file-lightbox-caption");
  const fileLightboxClose = document.getElementById("file-lightbox-close");
  const commentsSection = document.getElementById("ticket-comments");
  const commentStand = document.getElementById("comment-stand");
  const commentAblauf = document.getElementById("comment-ablauf");
  const commentStandMeta = document.getElementById("comment-stand-meta");
  const standSection = document.getElementById("ticket-stand");
  const standForm = document.getElementById("ticket-stand-form");
  const standAdd = document.getElementById("ticket-stand-add");
  const standError = document.getElementById("ticket-stand-error");
  const standPtFields = document.getElementById("stand-pt-fields");
  const commentList = document.getElementById("comment-list");
  const commentCount = document.getElementById("comment-count");
  const commentForm = document.getElementById("comment-form");
  const commentInput = document.getElementById("comment-input");
  const commentSend = document.getElementById("comment-send");
  const commentMention = document.getElementById("comment-mention");
  const commentPreview = document.getElementById("comment-preview");
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
    !context ||
    !contextFields ||
    !costs ||
    !costFields ||
    !team ||
    !teamFields ||
    !solution ||
    !solutionFields ||
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
      choices: ["Weiß ich noch nicht"],
    },
    {
      key: "end",
      prompt: "Wann soll der Change fertig sein?",
      placeholder: "Ende",
      label: "Ende",
      kind: "meta",
      date: true,
      choices: ["Weiß ich noch nicht"],
    },
    {
      key: "components",
      prompt: "Welche Stichwörter / Tags passen?",
      placeholder: "Stichwörter / Tags",
      label: "Stichwörter",
      kind: "meta",
      jiraLookup: "components",
      multi: true,
      optional: true,
      hint:
        "Stichwörter beschreiben Systeme, Themen oder Bereiche — z. B. SAP, Schul-App oder Digitalisierung. Mehrere auswählbar. Leer lassen geht auch.",
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
      key: "nonprofit",
      prompt: "Ist das Projekt gemeinnützig?",
      placeholder: "Gemeinnützig",
      label: "Gemeinnützig",
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
      key: "similar_solution",
      prompt: "Sind dir ähnliche Lösungen bei Schwarz bekannt?",
      placeholder: "Ähnliche Lösung nennen…",
      label: "Bezug",
      kind: "context",
      choices: ["Nein"],
      keepForm: true,
    },
    {
      key: "help_needed",
      prompt: "Benötigst du Unterstützung bei dem Projekt? Wenn ja welche?",
      placeholder: "z. B. Projektmanagement, methodisch oder personell",
      label: "Unterstützung",
      kind: "context",
      choices: ["Projektmanagement", "Methodisch", "Personell"],
      keepForm: true,
    },
    {
      key: "cost_savings",
      prompt: "Welche Kostenersparnis erwartest du?",
      placeholder: "Zahl, z. B. 12000",
      label: "Kostenersparnis",
      kind: "cost",
      optional: true,
      number: true,
      choices: ["Keine"],
      keepForm: true,
    },
    {
      key: "approver",
      prompt: "Wer genehmigt den Change (nach Freigabematrix)?",
      placeholder: "Name suchen…",
      label: "Genehmigung",
      kind: "team",
      jiraLookup: "user",
      choices: ["Ich weiß es nicht"],
      keepForm: true,
    },
    {
      key: "lead",
      prompt: "Wer übernimmt die Gesamtprojektleitung?",
      placeholder: "Gesamtprojektleitung",
      label: "Projektleitung",
      kind: "team",
      jiraLookup: "user",
      choices: ["Ich weiß es noch nicht"],
      keepForm: true,
    },
    {
      key: "it_owner",
      prompt: "Wer ist die verantwortliche Person aus der IT?",
      placeholder: "IT-Verantwortung",
      label: "IT-Verantwortung",
      kind: "team",
      onlyKind: "it_request",
      jiraLookup: "user",
    },
    {
      key: "change_team",
      prompt: "Welche Personen unterstützen bei diesem Projekt?",
      placeholder: "Namen suchen…",
      label: "Change-Team",
      kind: "team",
      optional: true,
      multi: true,
      jiraLookup: "user",
      choices: ["Gar keiner"],
      keepForm: true,
    },
    {
      key: "stakeholder",
      prompt:
        "Wer sind die Stakeholder? z. B. SCS Komplett, Bildungsinstitute oder Einzelpersonen, Geschäftsleitung",
      placeholder: "Stakeholder",
      label: "Stakeholder",
      kind: "team",
      hint: "Beispiele: SCS Komplett, Bildungsinstitute oder Einzelpersonen, Geschäftsleitung",
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
      key: "attachments_ask",
      prompt: "Möchtest du einen Anhang hochladen?",
      placeholder: "Anhang",
      label: "Anhang",
      kind: "files",
      ephemeral: true,
      choices: ["Ja", "Nein"],
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
  };

  const COST_IT_MONEY_STEP = {
    key: "it_costs",
    label: "IT Kosten",
    kind: "cost",
  };

  const COST_MONEY_STEP = {
    key: "costs",
    label: "Kosten",
    kind: "cost",
  };

  const COST_MATERIAL_STEP = {
    key: "material_costs",
    label: "Sachkosten",
    kind: "cost",
  };

  const COST_TOTAL_STEP = {
    key: "total_costs",
    label: "Gesamtsumme",
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
    if (raw === "keine" || raw === "niemand" || raw === "keiner" || raw === "gar keiner" || raw === "gar keine") return true;
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

  function showAiReviewHint() {
    aiReviewPending = true;
    if (overviewAiHint) {
      overview.hidden = false;
      overviewAiHint.hidden = false;
    }
    setIntro(AI_REVIEW_HINT);
    intro.classList.add("field-prompt-in");
    if (aiReviewOk) aiReviewOk.hidden = false;
    window.syncTicketInput?.();
  }

  function confirmAiReview() {
    aiReviewPending = false;
    if (aiReviewOk) aiReviewOk.hidden = true;
    syncPrompt();
  }

  function syncIntroChrome() {
    const kicker = document.getElementById("intro-prompt-kicker");
    const stepEl = document.getElementById("intro-prompt-step");
    if (kicker) kicker.textContent = "Neuer Change";
    if (!stepEl) return;
    const step = currentStep();
    if (!step) {
      stepEl.hidden = true;
      stepEl.textContent = "";
      return;
    }
    const visible = STEPS.filter(stepVisible);
    const idx = visible.findIndex((s) => s.key === step.key);
    stepEl.textContent = idx >= 0 ? `${idx + 1} · ${step.label}` : step.label;
    stepEl.hidden = false;
  }

  function setIntro(text) {
    const raw = String(text || "").trim();
    if (!raw) {
      intro.hidden = true;
      introText.textContent = "";
      return;
    }
    syncIntroChrome();
    introText.textContent = raw;
    intro.hidden = false;
  }

  let stepIndex = 0;
  let intakeStarted = false;
  window.aiReviewPending = function () {
    return aiReviewPending;
  };
  window.intakeIdle = function () {
    return !intakeStarted && !document.body.classList.contains("ticket-active");
  };
  function isCreatingChange() {
    return intakeStarted && !loadedTicket;
  }

  function jiraCreateButtons() {
    return [jiraBtn, jiraCreateTicket].filter(Boolean);
  }

  function hideJiraCreate() {
    jiraCreateButtons().forEach((btn) => {
      btn.hidden = true;
    });
  }

  function showJiraCreate() {
    jiraCreateButtons().forEach((btn) => {
      btn.hidden = false;
    });
  }

  function resetJiraCreate() {
    jiraCreateButtons().forEach((btn) => {
      btn.hidden = true;
      btn.disabled = false;
      btn.textContent = "In Jira Anlegen";
    });
  }

  function setJiraCreateBusy(label) {
    jiraCreateButtons().forEach((btn) => {
      btn.disabled = true;
      btn.textContent = label;
    });
  }

  function setJiraCreateIdle() {
    jiraCreateButtons().forEach((btn) => {
      btn.disabled = false;
      btn.textContent = "In Jira Anlegen";
    });
  }

  function syncTicketModeClass() {
    document.body.classList.toggle("ticket-creating", isCreatingChange());
    document.body.classList.toggle("ticket-open", loadedTicket);
    document.body.classList.toggle(
      "ticket-ready",
      isCreatingChange() &&
        !currentStep() &&
        Boolean(String(values.title || "").trim() && String(values.description || "").trim())
    );
  }
  window.startNewChange = function () {
    intakeStarted = true;
    loadedTicket = false;
    syncedRequestId = null;
    stepIndex = 0;
    autoFillBusy = false;
    aiReviewPending = false;
    revealCostsAfterReview = false;
    document.body.classList.remove("hub-chat-view");
    resetTicketState();
    if (startChangeBtn) startChangeBtn.hidden = true;
    if (aiReviewOk) aiReviewOk.hidden = true;
    if (ticketFinish) ticketFinish.hidden = true;
    if (openJiraEnd) openJiraEnd.hidden = true;
    resetJiraCreate();
    const hub = document.getElementById("hub");
    if (hub) hub.hidden = true;
    ticket.hidden = true;
    document.body.classList.remove("ticket-active");
    syncTicketModeClass();
    syncPrompt();
  };
  let syncedRequestId = null;
  let standUpdates = [];
  const values = {};
  const labels = {};
  const UI_TO_DOMAIN = {
    start: "start_date",
    end: "end_date",
    lead: "change_lead",
    nonprofit: "nonprofit_dss",
    reason: "problem",
    solution: "solution_goals",
    risks: "risks_obstacles",
    benefit: "benefit_savings",
    it_owner: "responsible_sit",
    effort_fb: "concept_scs_pt",
    effort_it: "concept_cit_pt",
    it_costs: "it_costs",
  };
  const DOMAIN_TO_UI = Object.fromEntries(
    Object.entries(UI_TO_DOMAIN).map(([ui, domain]) => [domain, ui])
  );
  let editingKey = null;
  let kindLocked = false;
  let autoFillBusy = false;
  let aiReviewPending = false;
  let revealCostsAfterReview = false;
  let overviewGen = 0;
  let clarifyDescription = false;
  let forceThinOk = false;
  // Geladenes Ticket: Stand, Kommentare und Anhänge hängen nicht am Intake-Fortschritt.
  let loadedTicket = false;
  const jiraUserCache = [];
  const jiraComponentCache = [];
  window.jiraComponentTree = [];
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
    return {
      name,
      label: row.label || name,
      description: row.description || "",
      virtual: Boolean(row.virtual),
      selectable: row.selectable !== false && !row.virtual,
      children: row.children || [],
    };
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
        window.jiraComponentTree = Array.isArray(body.tree) ? body.tree : [];
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

  function filterComponentTree(nodes, query) {
    const needle = String(query || "").trim().toLowerCase();
    if (!needle) return Array.isArray(nodes) ? nodes : [];
    const out = [];
    for (const node of nodes || []) {
      const kids = filterComponentTree(node.children || [], query);
      const blob = `${node.name || ""} ${node.description || ""}`.toLowerCase();
      if (blob.includes(needle) || kids.length) {
        out.push(Object.assign({}, node, { children: kids, open: true }));
      }
    }
    return out;
  }

  window.filterComponentTree = filterComponentTree;
  window.renderComponentTree = function (host, nodes, opts) {
    const options = opts || {};
    const pickedNames = (options.selected || [])
      .map((part) => String(part || "").trim())
      .filter(Boolean);
    const selected = new Set(pickedNames.map((part) => part.toLowerCase()));
    const onToggle = options.onToggle;
    host.classList.add("comp-tree");
    host.replaceChildren();
    if (pickedNames.length) {
      const bar = document.createElement("div");
      bar.className = "comp-tree-picked";
      pickedNames.forEach((name) => {
        const chip = document.createElement("span");
        chip.className = "comp-tree-chip";
        chip.textContent = name;
        bar.appendChild(chip);
      });
      host.appendChild(bar);
    }
    const list = document.createElement("div");
    list.className = "comp-tree-list";
    host.appendChild(list);

    function paint() {
      list.replaceChildren();
      walk(nodes, 0, list, false);
    }

    function walk(items, depth, parent, ancestorOpen) {
      (items || []).forEach((node) => {
        const hasKids = (node.children || []).length > 0;
        if (node.open == null && (ancestorOpen || (depth === 0 && node.name === "SCS - VS"))) {
          node.open = true;
        }
        const open = Boolean(node.open);
        const on = selected.has(String(node.name || "").toLowerCase());
        const line = document.createElement("div");
        line.className =
          "comp-tree-row" +
          (depth === 0 ? " is-root" : "") +
          (hasKids ? " is-folder" : " is-leaf") +
          (on ? " is-on" : "");
        line.style.setProperty("--d", String(depth));
        const chev = document.createElement("button");
        chev.type = "button";
        chev.className = "comp-tree-chev" + (hasKids ? (open ? " is-open" : "") : " is-leaf");
        chev.tabIndex = hasKids ? 0 : -1;
        chev.setAttribute("aria-hidden", hasKids ? "false" : "true");
        if (hasKids) {
          chev.onclick = (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            node.open = !open;
            paint();
          };
        }
        line.appendChild(chev);
        const selectable = node.selectable !== false && !node.virtual;
        if (selectable) {
          const box = document.createElement("button");
          box.type = "button";
          box.className = "comp-tree-check" + (on ? " is-on" : "");
          box.setAttribute("aria-pressed", on ? "true" : "false");
          box.onclick = (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            onToggle?.(node);
          };
          line.appendChild(box);
        } else {
          const skip = document.createElement("span");
          skip.className = "comp-tree-check is-folder";
          line.appendChild(skip);
        }
        const copy = document.createElement("span");
        copy.className = "comp-tree-copy";
        const title = document.createElement("span");
        title.className = "comp-tree-name";
        title.textContent = node.name || "";
        copy.appendChild(title);
        if (node.description) {
          const desc = document.createElement("span");
          desc.className = "comp-tree-desc";
          desc.textContent = node.description;
          copy.appendChild(desc);
        }
        line.appendChild(copy);
        if (selectable) {
          line.classList.add("is-pick");
          line.onclick = (ev) => {
            if (ev.target.closest(".comp-tree-chev")) return;
            onToggle?.(node);
          };
        } else if (hasKids) {
          line.onclick = () => {
            node.open = !open;
            paint();
          };
        }
        parent.appendChild(line);
        if (hasKids && open) walk(node.children, depth + 1, parent, false);
      });
    }

    walk(nodes, 0, list, Boolean(options.query));
  };

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
    if (typeof step.onlyIf === "function" && !step.onlyIf()) return false;
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
    const left = rect.left + rect.width / 2 - drop.offsetWidth / 2;
    drop.style.left = Math.max(8, Math.min(left, window.innerWidth - drop.offsetWidth - 8)) + "px";

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
    if (key === "it_costs") return COST_IT_MONEY_STEP;
    if (key === "costs") return COST_MONEY_STEP;
    if (key === "material_costs") return COST_MATERIAL_STEP;
    if (key === "total_costs") return COST_TOTAL_STEP;
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
    if (autoFillBusy || aiReviewPending) return null;
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
    return STEPS.filter(stepVisible)
      .filter((step) => !step.ephemeral)
      .concat(autoSteps().filter(stepVisible));
  }

  function fieldFilled(step) {
    const raw = String(values[step.key] || "").trim();
    if (!raw) return Boolean(step.optional);
    if (isUnknownFieldValue(raw)) return true;
    return !/konnte nicht ermittelt werden\.?$/i.test(raw);
  }

  function userFieldsDone() {
    if (autoFillBusy || aiReviewPending) return false;
    return STEPS.filter(stepVisible)
      .filter((step) => !step.ephemeral)
      .every(fieldFilled);
  }

  function ticketComplete() {
    if (autoFillBusy || aiReviewPending) return false;
    if (currentStep()) return false;
    return userFieldsDone();
  }

  function finishVisible() {
    return Boolean(ticketFinish && !ticketFinish.hidden);
  }

  function intakeTailOpen() {
    if (loadedTicket) return true;
    if (finishVisible()) return true;
    if (autoFillBusy || aiReviewPending) return false;
    if (stepIndex >= STEPS.length && ticketComplete()) return true;
    return false;
  }

  function intakeKindReached(kind) {
    if (kind === "cost" && revealCostsAfterReview) return true;
    if (intakeTailOpen()) return true;
    const live = currentStep();
    if (live?.kind === kind) return true;
    for (let i = 0; i < STEPS.length; i += 1) {
      const item = STEPS[i];
      if (!stepVisible(item) || item.kind !== kind) continue;
      if (stepIndex > i) return true;
    }
    return false;
  }

  function commentsAllowed() {
    return Boolean(loadedTicket && syncedRequestId && !isCreatingChange());
  }

  function filesAskedYes() {
    return /^ja$/i.test(String(values.attachments_ask || "").trim());
  }

  function syncIntakePanels() {
    const tail = intakeTailOpen();
    if (team) team.hidden = !intakeKindReached("team");
    if (costs) costs.hidden = !intakeKindReached("cost");
    if (solution) {
      solution.hidden =
        ticketKind() !== "it_request" || !intakeKindReached("solution");
    }
    if (context) context.hidden = !intakeKindReached("context");
    if (filesSection) {
      filesSection.hidden = !(loadedTicket || finishVisible() || filesAskedYes());
    }
    if (fieldsRoot) {
      fieldsRoot.hidden = !tail || !fieldsRoot.children.length;
    }
    if (standSection) standSection.hidden = true;
    if (commentsSection) commentsSection.hidden = !commentsAllowed();
    if (commentStand && !commentsAllowed()) {
      commentStand.hidden = true;
    }
  }

  function jiraBrowseUrl(key, url) {
    const raw = String(url || "").trim();
    let issue = String(key || "").trim();
    if (!issue) {
      const found = raw.match(/\/browse\/([A-Z][A-Z0-9]+-\d+)/i);
      issue = found ? found[1] : "";
    }
    if (issue && (!raw || /live\.api\.schwarz/i.test(raw))) {
      return `https://jira.schwarz/browse/${issue}`;
    }
    return raw;
  }

  function bindOpenJira(link, jiraUrl) {
    if (!link) return;
    const url = String(jiraUrl || "").trim();
    if (!url) {
      link.hidden = true;
      link.removeAttribute("href");
      return;
    }
    link.hidden = false;
    link.href = url;
    link.classList.remove("is-disabled");
    link.removeAttribute("aria-disabled");
  }

  function showFinishActions(key, jiraUrl, { newChange = false } = {}) {
    hideJiraCreate();
    const url = jiraBrowseUrl(key, jiraUrl);
    if (newChange) {
      if (ticketFinish) ticketFinish.hidden = false;
      if (newChangeBtn) newChangeBtn.hidden = false;
      bindOpenJira(openJiraLink, url);
      if (openJiraEnd) openJiraEnd.hidden = true;
    } else {
      if (ticketFinish) ticketFinish.hidden = true;
      if (openJiraLink) openJiraLink.hidden = true;
      if (newChangeBtn) newChangeBtn.hidden = true;
      bindOpenJira(openJiraEnd, url);
    }
    setIntro("");
    syncIntakePanels();
  }

  function syncJiraButton() {
    if (finishVisible()) return;
    if (autoFillBusy) {
      hideJiraCreate();
      return;
    }
    const done = ticketComplete();
    if (done) showJiraCreate();
    else hideJiraCreate();
    if (!done) return;
    setIntro("Bitte alle Felder noch einmal prüfen");
    intro.classList.add("field-prompt-in");
  }

  function overviewSteps() {
    return requiredSteps().filter((step) => step.kind === "overview");
  }

  function refreshOverviewChrome() {
    const steps = overviewSteps();
    if (!steps.length) {
      if (overviewMeta) overviewMeta.textContent = "";
      return;
    }
    let filled = 0;
    let thin = 0;
    for (const step of steps) {
      const cell = fieldCell(step);
      const raw = String(values[step.key] || "").trim();
      const ok = fieldFilled(step) && raw && !/konnte nicht ermittelt werden\.?$/i.test(raw);
      if (ok) filled += 1;
      if (cell) {
        cell.classList.toggle("is-empty", !raw);
        if (step.key === "description" && raw && isThinDescription?.(raw)) {
          cell.classList.add("is-incomplete");
          thin += 1;
        } else if (step.key === "description") {
          cell.classList.remove("is-incomplete");
        }
      }
    }
    if (overviewMeta) overviewMeta.textContent = "";
  }

  function ensureFieldShell(step) {
    if (step.ephemeral || step.kind === "files") return null;
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

    if (step.kind === "context") {
      let cell = contextFields.querySelector(`[data-key="${step.key}"]`);
      if (!cell) {
        cell = document.createElement("div");
        cell.className = "ticket-meta-item";
        cell.dataset.key = step.key;
        cell.innerHTML = `<dt>${esc(step.label)}</dt><dd><span id="ticket-${esc(
          step.key
        )}-value" class="ticket-row-value"></span></dd>`;
        contextFields.appendChild(cell);
      }
      cell.hidden = false;
      orderContextFields();
      syncIntakePanels();
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
      refreshOverviewChrome();
      return document.getElementById(`ticket-${step.key}-value`);
    }

    if (step.kind === "team") {
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
      const dt = cell.querySelector("dt");
      if (dt) dt.textContent = step.label;
      cell.hidden = false;
      orderTeamFields();
      syncIntakePanels();
      return document.getElementById(`ticket-${step.key}-value`);
    }

    if (step.kind === "solution") {
      let cell = solutionFields.querySelector(`[data-key="${step.key}"]`);
      if (!cell) {
        cell = document.createElement("div");
        cell.className = "ticket-meta-item";
        cell.dataset.key = step.key;
        cell.innerHTML = `<dt>${esc(step.label)}</dt><dd><span id="ticket-${esc(
          step.key
        )}-value" class="ticket-row-value"></span></dd>`;
        solutionFields.appendChild(cell);
      }
      const dt = cell.querySelector("dt");
      if (dt) dt.textContent = step.label;
      cell.hidden = false;
      orderSolutionFields();
      syncIntakePanels();
      return document.getElementById(`ticket-${step.key}-value`);
    }

    if (step.kind === "cost") {
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
      orderCostFields();
      syncIntakePanels();
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
    syncIntakePanels();
    return document.getElementById(`ticket-${step.key}-value`);
  }

  function revealCurrentField() {
    const step = currentStep();
    if (!step || step.kind === "headline" || step.ephemeral) return;
    ensureFieldShell(step);
  }

  function orderContextFields() {
    ["similar_solution", "help_needed"].forEach((key) => {
      const cell = contextFields.querySelector(`[data-key="${key}"]`);
      if (cell) contextFields.appendChild(cell);
    });
  }

  function orderTeamFields() {
    [
      "lead",
      "approver",
      "it_owner",
      "author",
      "process_owner",
      "solution_owner",
      "change_team",
      "stakeholder",
    ].forEach((key) => {
      const cell = teamFields.querySelector(`[data-key="${key}"]`);
      if (cell) teamFields.appendChild(cell);
    });
  }

  function orderSolutionFields() {
    ["solution_category", "solution_name"].forEach((key) => {
      const cell = solutionFields.querySelector(`[data-key="${key}"]`);
      if (cell) solutionFields.appendChild(cell);
    });
  }

  function orderCostFields() {
    [
      "effort_fb",
      "effort_it",
      "costs",
      "it_costs",
      "material_costs",
      "cost_savings",
      "total_costs",
    ].forEach((key) => {
      const cell = costFields.querySelector(`[data-key="${key}"]`);
      if (cell) costFields.appendChild(cell);
    });
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
    if (step.kind === "context") {
      return contextFields.querySelector(`[data-key="${step.key}"]`);
    }
    if (step.kind === "team") {
      return teamFields.querySelector(`[data-key="${step.key}"]`);
    }
    if (step.kind === "solution") {
      return solutionFields.querySelector(`[data-key="${step.key}"]`);
    }
    if (step.kind === "cost") {
      return costFields.querySelector(`[data-key="${step.key}"]`);
    }
    return fieldsRoot.querySelector(`.ticket-row[data-key="${step.key}"]`);
  }

  function showAuthor({ preferActor = false } = {}) {
    const actor = window.currentActor || {};
    const actorId = String(actor.jiraName || actor.externalSubject || "").trim();
    const actorLabel = String(
      actor.displayName || window.currentActorName || ""
    ).trim();
    const existingId = String(values.author || "").trim();
    const existingLabel = String(labels.author || "").trim();
    let id = existingId;
    let label = existingLabel || existingId;
    if (preferActor || !id) {
      id = actorId || actorLabel || existingId;
      label = actorLabel || actorId || existingLabel || id;
      if (id) setLookupValue("author", id, label || id);
    }
    const el = ensureFieldShell(AUTHOR_STEP);
    if (el && (label || id)) el.textContent = label || id;
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
    if (solution) solution.hidden = true;
  }

  function displayFor(key) {
    return labels[key] || values[key] || "";
  }

  function isTagStep(step) {
    return step?.jiraLookup === "components" || Boolean(step?.multi);
  }

  function tagsFromEl(el) {
    return [...(el?.querySelectorAll(".ticket-tag") || [])]
      .map((chip) => chip.textContent.trim())
      .filter(Boolean)
      .join(", ");
  }

  function writeFieldValue(el, step, raw) {
    if (!el) return;
    const isTags = isTagStep(step);
    if (isTags) {
      const parts = String(raw || "")
        .split(/[,;]/)
        .map((part) => part.trim())
        .filter(Boolean);
      el.textContent = "";
      el.classList.add("ticket-tags");
      parts.forEach((name) => {
        const chip = document.createElement("span");
        chip.className = "ticket-tag";
        chip.textContent = name;
        el.appendChild(chip);
      });
      return;
    }
    el.classList.remove("ticket-tags");
    el.textContent = raw || "";
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

  function persistField(uiKey, raw) {
    if (!syncedRequestId) return;
    if (uiKey === "attachments_ask") return;
    const step = stepByKey(uiKey);
    const domain = UI_TO_DOMAIN[uiKey] || uiKey;
    let value = String(raw ?? "").trim();
    if (step?.date) value = deToIso(value) || value;
    if (uiKey === "priority") return;
    const payload =
      domain === "title" || domain === "description" || domain === "change_lead"
        ? { [domain]: value }
        : { fields: { [domain]: value } };
    void fetch(`/api/requests/${syncedRequestId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(async (r) => {
      if (r.ok) return;
      const body = await r.json().catch(() => ({}));
      flash(
        typeof body.detail === "string" ? body.detail : "Änderung nicht nach Jira geschrieben",
        true
      );
    });
  }

  function cancelEdit() {
    if (!editingKey) return;
    const step = stepByKey(editingKey);
    const valueEl = fieldHost(step);
    if (valueEl) {
      writeFieldValue(valueEl, step, displayFor(editingKey));
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
    } else if (isTagStep(step)) {
      text = displayFor(key) || tagsFromEl(valueEl);
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
        writeFieldValue(valueEl, step, prevLabel || prevName || text);
      } else if (text) {
        setLookupValue(key, text, text);
        writeFieldValue(valueEl, step, text);
      } else {
        delete values[key];
        delete labels[key];
        writeFieldValue(valueEl, step, "");
      }
    } else {
      writeFieldValue(valueEl, step, text);
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
    persistField(key, values[key] || text);
    if (step?.kind === "overview") refreshOverviewChrome();
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
    valueEl.hidden = Boolean(!step.keepForm);
    if (step.keepForm) {
      valueEl.contentEditable = "true";
      valueEl.classList.add("is-editing");
    }
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
        persistField(step.key, value);
      };
      row.appendChild(chip);
    });
    valueEl.insertAdjacentElement("afterend", row);
  }

  function renderJiraLookup(step, valueEl) {
    clearFieldExtras(valueEl);
    const isTags = isTagStep(step);

    // Mehrfachauswahl: User-Chips oder Stichwörter.
    if (isTags) {
      valueEl.hidden = false;
      valueEl.contentEditable = "false";
      valueEl.classList.remove("is-editing");
      writeFieldValue(valueEl, step, displayFor(step.key) || tagsFromEl(valueEl));
      const wrap = document.createElement("div");
      wrap.className = "field-edit-lookup is-tags";
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
            writeFieldValue(valueEl, step, value);
            editingKey = null;
            clearFieldExtras(valueEl);
            void refreshPriority();
            void refreshKind();
            syncJiraButton();
            persistField(step.key, value);
          };
          chips.appendChild(chip);
        });
        wrap.appendChild(chips);
      }
      if (step.hint) {
        const hint = document.createElement("p");
        hint.className = "field-tags-hint";
        hint.textContent = step.hint;
        wrap.appendChild(hint);
      }
      const search = document.createElement("input");
      search.type = "search";
      search.className = "field-lookup-search";
      search.placeholder = step.placeholder || "Suchen…";
      search.autocomplete = "off";
      if (step.jiraLookup === "user") wrap.appendChild(search);
      const list = document.createElement("div");
      list.className = "field-lookup-list";
      wrap.appendChild(list);
      valueEl.insertAdjacentElement("afterend", wrap);

      function selectedParts() {
        return String(values[step.key] || labels[step.key] || "")
          .split(/[,;]/)
          .map((part) => part.trim())
          .filter(Boolean)
          .filter((part) => !isUnknownFieldValue(part));
      }

      function pick(item) {
        const label = item.label || item.displayName || item.name || "";
        const name = item.name || label;
        const current = selectedParts();
        const key = name.toLowerCase();
        const next = current.some((part) => part.toLowerCase() === key || part.toLowerCase() === label.toLowerCase())
          ? current.filter((part) => part.toLowerCase() !== key && part.toLowerCase() !== label.toLowerCase())
          : [...current, name];
        const joined = next.join(", ");
        if (joined) {
          setLookupValue(step.key, joined, joined);
          writeFieldValue(valueEl, step, joined);
        } else {
          delete values[step.key];
          delete labels[step.key];
          writeFieldValue(valueEl, step, "");
        }
        void loadSuggestions(search.value || "").then((items) => {
          if (editingKey !== step.key) return;
          renderList(items);
        });
        syncJiraButton();
        persistField(step.key, joined);
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
        const tree = window.filterComponentTree?.(window.jiraComponentTree, search.value || "") || [];
        if (step.jiraLookup === "components" && tree.length && window.renderComponentTree) {
          list.classList.add("is-tree");
          window.renderComponentTree(list, tree, {
            selected: selectedParts(),
            onToggle: (node) => pick(node),
          });
          return;
        }
        list.classList.remove("is-tree");
        if (!items.length) {
          const empty = document.createElement("span");
          empty.className = "field-lookup-empty";
          empty.textContent =
            step.jiraLookup === "user"
              ? search.value.trim()
                ? "Keine Treffer in Jira"
                : "Name tippen — Jira schlägt vor"
              : "Keine Stichwörter / Tags geladen";
          list.appendChild(empty);
          return;
        }
        const selected = new Set(selectedParts().map((part) => part.toLowerCase()));
        items.forEach((item) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "suggestion field-lookup-item";
          btn.textContent = item.label || item.name;
          const key = String(item.name || item.label || "").toLowerCase();
          const lab = String(item.label || item.displayName || "").toLowerCase();
          if (selected.has(key) || (lab && selected.has(lab))) btn.classList.add("is-selected");
          btn.onclick = (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            pick(item);
          };
          list.appendChild(btn);
        });
      }

      let timer = 0;
      search.addEventListener("input", () => {
        window.clearTimeout(timer);
        const query = search.value;
        timer = window.setTimeout(() => {
          void loadSuggestions(query).then((items) => {
            if (editingKey !== step.key) return;
            renderList(items);
          });
        }, 120);
      });
      void loadSuggestions(step.jiraLookup === "user" ? "" : "").then((items) => {
        if (editingKey !== step.key) return;
        renderList(items);
      });
      if (step.jiraLookup === "user") {
        window.setTimeout(() => search.focus(), 0);
      }
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
    if (key === "it_costs" || key === "material_costs" || key === "total_costs") return;
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
      } else if (["benefit", "reason", "solution", "risks"].includes(key)) {
        showAiReviewHint();
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
    if (window.intakeIdle?.()) {
      document.body.classList.remove("field-flow");
      setIntro("");
      if (startChangeBtn) startChangeBtn.hidden = false;
      if (aiReviewOk) aiReviewOk.hidden = true;
      window.syncTicketInput?.();
      return;
    }
    if (startChangeBtn) startChangeBtn.hidden = true;
    if (aiReviewPending) {
      showAiReviewHint();
      return;
    }
    if (aiReviewOk) aiReviewOk.hidden = true;
    const step = currentStep();
    document.body.classList.toggle(
      "field-flow",
      Boolean(step) || clarifyDescription
    );

    if (!step || step.ephemeral) {
      if (finishVisible()) {
        window.syncTicketInput?.();
        syncIntakePanels();
        syncTicketModeClass();
        return;
      }
      if (ticketComplete()) {
        showJiraCreate();
        setIntro("Bitte alle Felder noch einmal prüfen");
        intro.classList.add("field-prompt-in");
      } else if (step?.ephemeral) {
        hideJiraCreate();
        setIntro(step.prompt);
        intro.classList.remove("field-prompt-in");
        void intro.offsetWidth;
        intro.classList.add("field-prompt-in");
      } else {
        hideJiraCreate();
        if (!step) setIntro("");
      }
      window.syncTicketInput?.();
      syncIntakePanels();
      syncTicketModeClass();
      return;
    }

    if (!finishVisible()) hideJiraCreate();
    if (step.kind === "cost" && !revealCostsAfterReview) {
      revealCostsAfterReview = true;
      prepareCostFields();
      openEffortTemplate();
    }
    revealCurrentField();
    syncIntakePanels();
    setIntro(step.prompt);
    intro.classList.remove("field-prompt-in");
    void intro.offsetWidth;
    intro.classList.add("field-prompt-in");
    window.syncTicketInput?.();
    syncTicketModeClass();
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
    showAuthor({ preferActor: true });
    refreshPriority();
    if (!step.ephemeral) showFiles();
    syncIntakePanels();

    if (step.ephemeral) {
      values[step.key] = text;
      if (step.key === "attachments_ask" && /^ja$/i.test(String(text || "").trim())) {
        if (filesSection) filesSection.hidden = false;
        fileInput?.click();
      }
      return introText;
    }

    const valueEl = ensureFieldShell(step);
    if (!valueEl) return null;

    if (step.number) {
      const raw = String(text || "").trim();
      if (
        !raw ||
        (typeof isUnknownFieldValue === "function" && isUnknownFieldValue(raw))
      ) {
        text = "";
      }
    }

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

    writeFieldValue(valueEl, step, text);
    valueEl.classList.remove("ticket-row-value-in");
    valueEl.classList.add("ticket-row-value-pending");
    values[step.key] = text;
    return valueEl;
  };

  window.showTicketField = function () {
    const step = currentStep();
    if (!step) return;

    if (step.ephemeral) {
      stepIndex += 1;
      syncIntakePanels();
      syncPrompt();
      return;
    }

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
      refreshOverviewChrome();
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
    syncIntakePanels();
    void refreshPriority();
    void refreshKind();
    if (step.kind === "overview") refreshOverviewChrome();
    if (step.key === "description") {
      autoFillBusy = true;
      window.syncTicketInput?.();
      void fillAutoOverview(false)
        .catch(() => {})
        .finally(() => {
          autoFillBusy = false;
          refreshOverviewChrome();
          showAiReviewHint();
          syncIntakePanels();
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
    persistField(shell.key, value);
    if (shell.kind === "overview") refreshOverviewChrome();
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
    showAiReviewHint();
  }

  function parsePt(text) {
    const m = String(text || "")
      .replace(",", ".")
      .match(/(\d+(?:\.\d+)?)/);
    return m ? Number(m[1]) : 0;
  }

    function parseMoney(text) {
    const raw = String(text || "")
      .replace(/\s/g, "")
      .replace(/€/g, "");
    if (!raw) return 0;
    if (/^\d{1,3}(\.\d{3})+(,\d+)?$/.test(raw)) {
      return Number(raw.replace(/\./g, "").replace(",", ".")) || 0;
    }
    const n = Number(raw.replace(",", "."));
    return Number.isFinite(n) ? n : 0;
  }

  function formatMoney(text) {
    const n = parseMoney(text);
    if (!n) return String(text || "").trim();
    return `${n.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;
  }

  function isMoneyCostKey(key) {
    return ["costs", "it_costs", "material_costs", "total_costs"].includes(key);
  }

  function formatPtDisplay(text) {
    const raw = String(text || "").trim();
    if (!raw) return "";
    if (/pt/i.test(raw)) return raw;
    const n = parsePt(raw);
    if (!n) return raw;
    return Number.isInteger(n) ? `${n} PT` : `${String(n).replace(".", ",")} PT`;
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
    let value = String(text || "").trim();
    if (step.key === "effort_fb" || step.key === "effort_it") {
      value = formatPtDisplay(value);
    }
    const shown = isMoneyCostKey(step.key) ? formatMoney(value) : value;
    el.textContent = shown;
    if (value) values[step.key] = value;
    else delete values[step.key];
    const cell = fieldCell(step);
    el.classList.add("ticket-row-value-in");
    cell?.classList.remove("is-pending");
    cell?.classList.add("is-done");
    cell?.classList.add("is-readonly");
  }

  function hydrateCostFields() {
    const fb = values.effort_fb || values.concept_scs_pt || "";
    const it = values.effort_it || values.concept_cit_pt || "";
    const itMoney = values.it_costs || "";
    const money = values.costs || "";
    const material = values.material_costs || "";
    const total = values.total_costs || "";
    const sheet = values.effort_sheet_url || "";
    if (!fb && !it && !itMoney && !money && !material && !total && !sheet) return;
    prepareCostFields();
    if (fb) writeCostField(COST_FB_STEP, fb, true);
    if (it) writeCostField(COST_IT_STEP, it, true);
    if (itMoney) writeCostField(COST_IT_MONEY_STEP, itMoney, true);
    if (money) writeCostField(COST_MONEY_STEP, money, true);
    if (material) writeCostField(COST_MATERIAL_STEP, material, true);
    if (total) writeCostField(COST_TOTAL_STEP, total, true);
    syncEffortOpenLabel();
    const hintEl = costHintEl();
    if (hintEl && (values.effort_fb || values.effort_it)) {
      hintEl.textContent = `Übernommen: SCS ${values.effort_fb || "0 PT"}, CIT ${
        values.effort_it || "0 PT"
      }.`;
    }
  }

  function persistEffortValues() {
    if (!syncedRequestId) return;
    const fields = {};
    [
      "effort_sheet_url",
      "costs",
      "it_costs",
      "material_costs",
      "total_costs",
      "concept_scs_pt",
      "concept_cit_pt",
      "operate_scs_pt",
      "operate_cit_pt",
      "concept_scs_pt_detail",
      "concept_cit_pt_detail",
      "operate_scs_pt_detail",
      "operate_cit_pt_detail",
      "concept_scs_material",
      "concept_cit_material",
      "operate_scs_material",
      "operate_cit_material",
    ].forEach((key) => {
      const val = String(values[key] || "").trim();
      if (!val) return;
      fields[key] = isMoneyCostKey(key) ? String(parseMoney(val) || val) : val;
    });
    if (!fields.concept_scs_pt) {
      const n = parsePt(values.effort_fb);
      if (n) fields.concept_scs_pt = String(n);
    }
    if (!fields.concept_cit_pt) {
      const n = parsePt(values.effort_it);
      if (n) fields.concept_cit_pt = String(n);
    }
    if (!Object.keys(fields).length) return;
    void fetch(`/api/requests/${syncedRequestId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields }),
    });
  }

  function costHintEl() {
    return document.querySelector("#ticket-costs .ticket-section-hint");
  }

  /** Aufwand kommt aus der Sheets-Vorlage, nicht per Zahlentippen. */
  function prepareCostFields() {
    ensureFieldShell(COST_FB_STEP);
    fieldCell(COST_FB_STEP)?.classList.add("is-readonly");
    ensureFieldShell(COST_IT_STEP);
    fieldCell(COST_IT_STEP)?.classList.add("is-readonly");
    ensureFieldShell(COST_IT_MONEY_STEP);
    fieldCell(COST_IT_MONEY_STEP)?.classList.add("is-readonly");
    ensureFieldShell(COST_MONEY_STEP);
    fieldCell(COST_MONEY_STEP)?.classList.add("is-readonly");
    ensureFieldShell(COST_MATERIAL_STEP);
    fieldCell(COST_MATERIAL_STEP)?.classList.add("is-readonly");
    ensureFieldShell(COST_TOTAL_STEP);
    fieldCell(COST_TOTAL_STEP)?.classList.add("is-readonly");
    orderCostFields();
    const hintEl = costHintEl();
    if (hintEl && !parsePt(values.effort_fb)) {
      hintEl.textContent = "Vorlage öffnen, Kalkulation ausfüllen, Fenster schließen.";
    }
    syncEffortOpenLabel();
    syncKindFields();
  }

  function shareIdFromUrl(url) {
    const match = String(url || "").match(/\/aufwand\/([0-9a-fA-F-]{36})/i);
    return match ? match[1] : "";
  }

  function effortFilled() {
    return Boolean(shareIdFromUrl(values.effort_sheet_url) || parsePt(values.effort_fb));
  }

  function syncEffortOpenLabel() {
    if (!effortSheetOpen) return;
    effortSheetOpen.textContent = effortFilled()
      ? "Ausgefülltes Dokument öffnen"
      : "Vorlage öffnen";
  }

  function applyEffortSheet(body) {
    writeCostField(COST_FB_STEP, body.effort_fb || "", true);
    writeCostField(COST_IT_STEP, body.effort_it || "", true);
    writeCostField(COST_IT_MONEY_STEP, body.it_costs || "", true);
    writeCostField(COST_MONEY_STEP, body.costs || "", true);
    writeCostField(COST_MATERIAL_STEP, body.material_costs || "", true);
    writeCostField(COST_TOTAL_STEP, body.total_costs || "", true);
    [
      "effort_sheet_url",
      "concept_scs_pt",
      "concept_cit_pt",
      "operate_scs_pt",
      "operate_cit_pt",
      "concept_scs_pt_detail",
      "concept_cit_pt_detail",
      "operate_scs_pt_detail",
      "operate_cit_pt_detail",
      "concept_scs_material",
      "concept_cit_material",
      "operate_scs_material",
      "operate_cit_material",
      "it_costs",
      "material_costs",
      "total_costs",
      "summe",
    ].forEach((key) => {
      const val = String(body[key] || "").trim();
      if (val) values[key] = val;
      else delete values[key];
    });
    persistEffortValues();
    syncEffortOpenLabel();
    const hintEl = costHintEl();
    if (hintEl) {
      const fb = body.effort_fb || "0 PT";
      const it = body.effort_it || "0 PT";
      hintEl.textContent = `Übernommen: SCS ${fb}, CIT ${it}.`;
    }
    void reviewEffort();
    syncJiraButton();
  }

  async function importEffortSheet(url, ownerId) {
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
    if (ownerId !== undefined && (ownerId || null) !== (syncedRequestId || null)) return;
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

  function isDummyEffortSheet(url) {
    const href = String(url || "").trim();
    return /dummycritraufwand/i.test(href) || href === "/effort-sheet" || href.endsWith("/effort-sheet");
  }

  /** Die Kalkulation gehört zu genau dem Ticket, für das sie geöffnet wurde. */
  async function commitEffortCsv(csv, ownerId, shareId) {
    const hintEl = costHintEl();
    const stillOpen = (ownerId || null) === (syncedRequestId || null);
    if (hintEl && stillOpen) hintEl.textContent = "Übernehme Aufwand…";
    const r = await fetch("/api/sessions/effort-sheet/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        csv,
        share_id: shareId || undefined,
        request_id: ownerId || undefined,
      }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail || "Übernahme fehlgeschlagen");
    if (!stillOpen) {
      flash("Aufwand wurde beim ursprünglichen Change gespeichert.");
      return;
    }
    applyEffortSheet(body);
    if (hintEl && syncedRequestId) {
      hintEl.textContent = "Aufwand gespeichert und nach Jira gestellt.";
    }
  }

  function watchEffortPopup(popup, ownerId, share, url, dummy) {
    const waitHint = document.getElementById("effort-sheet-hint");
    if (waitHint) waitHint.hidden = false;
    let pendingCsv = "";
    const onMsg = (event) => {
      if (event.origin !== location.origin) return;
      if (event.data?.type !== "critr-effort-sheet-v1") return;
      pendingCsv = String(event.data.csv || "");
    };
    window.addEventListener("message", onMsg);
    const timer = setInterval(() => {
      if (popup && !popup.closed) return;
      clearInterval(timer);
      window.removeEventListener("message", onMsg);
      if (waitHint) waitHint.hidden = true;
      const run = pendingCsv.trim()
        ? commitEffortCsv(pendingCsv, ownerId, share)
        : dummy
          ? Promise.resolve()
          : importEffortSheet(effortSheetTemplateUrl || url, ownerId);
      run.catch((err) => {
        const hintEl = costHintEl();
        if (hintEl) hintEl.textContent = err.message || "Sheet konnte nicht übernommen werden.";
      });
    }, 250);
  }
  openEffortTemplate._watchTab = watchEffortPopup;

  function openEffortTemplate() {
    // Ticket und Share beim Öffnen festhalten — ein Ticketwechsel darf nichts verschieben.
    const ownerId = syncedRequestId || null;
    const share = shareIdFromUrl(values.effort_sheet_url);
    const settingsUrl = effortSheetOpenUrl || effortSheetTemplateUrl;
    const dummy = isDummyEffortSheet(effortSheetTemplateUrl) || isDummyEffortSheet(settingsUrl) || !settingsUrl;
    // Titel mitgeben, damit im Sheet steht, zu welchem Change es gehört.
    const forParam = encodeURIComponent(String(values.title || "").trim().slice(0, 90));
    const own = share ? `/effort-sheet?share=${share}` : "/effort-sheet?fresh=1";
    const url = share || dummy ? (forParam ? `${own}&for=${forParam}` : own) : settingsUrl;
    if (!url) {
      const hintEl = costHintEl();
      if (hintEl) {
        hintEl.textContent = "Unter Einstellungen die Google-Sheets-Vorlage eintragen.";
      }
      return;
    }
    const popup = window.open(
      url,
      `critrEffortSheet-${ownerId || "neu"}`,
      "popup=yes,width=980,height=780"
    );
    if (!popup) {
      const hintEl = costHintEl();
      if (hintEl) {
        hintEl.textContent =
          "Popup blockiert — Vorlage per Klick im neuen Tab öffnen.";
      }
      flash("Popup blockiert — Vorlage öffnen?", true, {
        label: "Vorlage öffnen",
        duration: 8000,
        onClick: () => {
          const tab = window.open(url, "_blank", "noopener");
          if (!tab) {
            flash("Bitte Popups erlauben oder den Link unter Einstellungen nutzen.", true);
            return;
          }
          openEffortTemplate._watchTab?.(tab, ownerId, share, url, dummy);
        },
      });
      return;
    }
    watchEffortPopup(popup, ownerId, share, url, dummy);
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
  let remoteAttachments = [];
  let fileSeq = 0;
  const MAX_FILE = 20 * 1024 * 1024;
  const previewUrls = new Map();

  function revokePreview(id) {
    const url = previewUrls.get(id);
    if (url) {
      URL.revokeObjectURL(url);
      previewUrls.delete(id);
    }
  }

  function revokeAllPreviews() {
    for (const id of [...previewUrls.keys()]) revokePreview(id);
  }

  async function ensureRemotePreview(item, { thumb = false } = {}) {
    const key = `${thumb ? "thumb" : "remote"}:${item.id}`;
    if (previewUrls.has(key)) return previewUrls.get(key);
    if (!item.href) return "";
    const href = thumb
      ? `${item.href}${item.href.includes("?") ? "&" : "?"}thumb=1`
      : item.href;
    try {
      const r = await fetch(href, { credentials: "same-origin" });
      if (!r.ok) return "";
      const blob = await r.blob();
      if (!blob || !blob.size) return "";
      const url = URL.createObjectURL(blob);
      previewUrls.set(key, url);
      return url;
    } catch (_) {
      return "";
    }
  }

  function ensureLocalPreview(item) {
    const key = `local:${item.localId || item.id}`;
    if (previewUrls.has(key)) return previewUrls.get(key);
    if (!item.file) return "";
    const url = URL.createObjectURL(item.file);
    previewUrls.set(key, url);
    return url;
  }

  function formatSize(bytes) {
    const n = Number(bytes) || 0;
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
    const mb = n / (1024 * 1024);
    const digits = mb >= 10 ? 0 : 1;
    return `${mb.toFixed(digits).replace(".", ",")} MB`;
  }

  function fileKind(name, mime) {
    const n = String(name || "").toLowerCase();
    const m = String(mime || "").toLowerCase();
    if (m.startsWith("image/") || /\.(png|jpe?g|gif|webp|svg)$/.test(n)) return "image";
    if (m.includes("pdf") || n.endsWith(".pdf")) return "pdf";
    if (
      m.includes("sheet") ||
      m.includes("excel") ||
      m.includes("csv") ||
      /\.(xlsx?|csv|ods)$/.test(n)
    ) {
      return "sheet";
    }
    if (m.includes("word") || /\.(docx?|odt|rtf)$/.test(n)) return "doc";
    if (m.includes("zip") || /\.(zip|rar|7z|tar|gz)$/.test(n)) return "archive";
    return "file";
  }

  function fileKindLabel(kind) {
    return (
      {
        image: "Bild",
        pdf: "PDF",
        sheet: "Tabelle",
        doc: "Dokument",
        archive: "Archiv",
        file: "Datei",
      }[kind] || "Datei"
    );
  }

  function displayFileName(name) {
    const raw = String(name || "").trim() || "Anhang";
    return raw.replace(/\.(xlsx?|csv|ods|docx?|pdf|zip|rar|7z|tar|gz|png|jpe?g|gif|webp|svg)$/i, "");
  }

  function isEffortSheetFile(name, kind) {
    if (kind === "sheet") return true;
    const n = String(name || "").toLowerCase();
    return /kalkulation\.(xlsx?|csv)$/i.test(n) || n.endsWith("-kalkulation.xlsx") || n.endsWith("-kalkulation.csv");
  }

  const SHEETS_ICON_SVG =
    '<svg class="ticket-file-sheets-logo" viewBox="0 0 48 48" aria-hidden="true" focusable="false"><path fill="#0F9D58" d="M8 4h22l10 10v30a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path fill="#87CEAC" d="M30 4v8a2 2 0 0 0 2 2h8"/><path fill="#fff" d="M14 20h20v3H14zm0 6h20v3H14zm0 6h20v3H14zm0 6h12v3H14z"/></svg>';

  function openLightbox(url, caption) {
    if (!fileLightbox || !fileLightboxImg || !url) return;
    fileLightboxImg.src = url;
    fileLightboxImg.alt = caption || "";
    if (fileLightboxCaption) fileLightboxCaption.textContent = caption || "";
    fileLightbox.hidden = false;
  }

  function closeLightbox() {
    if (!fileLightbox) return;
    fileLightbox.hidden = true;
    if (fileLightboxImg) {
      fileLightboxImg.removeAttribute("src");
      fileLightboxImg.alt = "";
    }
    if (fileLightboxCaption) fileLightboxCaption.textContent = "";
  }

  async function resolveAttachmentUrl(item) {
    if (item.previewUrl) return item.previewUrl;
    if (item.source === "local" && item.file) return ensureLocalPreview(item);
    if (item.href) return ensureRemotePreview({ id: item.id, href: item.href });
    return "";
  }

  function renderFiles() {
    if (!fileList) return;
    const remote = (remoteAttachments || []).map((item) => ({
      id: item.id,
      name: item.filename || "Anhang",
      sizeLabel: formatSize(item.size),
      source: "jira",
      author: item.author || "",
      createdAt: item.createdAt || "",
      contentType: item.contentType || "",
      href: syncedRequestId
        ? `/api/requests/${syncedRequestId}/attachments/${encodeURIComponent(item.id)}/content`
        : "",
    }));
    const local = attachments.map((item) => ({
      id: item.id,
      name: item.name,
      sizeLabel: item.sizeLabel,
      source: "local",
      author: "",
      createdAt: "",
      contentType: item.file?.type || "",
      href: "",
      localId: item.id,
      file: item.file,
      previewUrl: ensureLocalPreview(item),
    }));
    const items = [...remote, ...local].map((item) => ({
      ...item,
      kind: fileKind(item.name, item.contentType),
    }));
    if (fileEmpty) fileEmpty.hidden = items.length > 0;
    if (!items.length) {
      fileList.innerHTML = "";
      if (fileGallery) {
        fileGallery.innerHTML = "";
        fileGallery.hidden = true;
      }
      return;
    }

    const images = items.filter((item) => item.kind === "image");
    const others = items.filter((item) => item.kind !== "image");

    if (fileGallery) {
      if (!images.length) {
        fileGallery.innerHTML = "";
        fileGallery.hidden = true;
      } else {
        fileGallery.hidden = false;
        fileGallery.innerHTML = images
          .map((item) => {
            const meta = [item.sizeLabel, item.author, item.source === "jira" ? "Jira" : "Lokal"]
              .filter(Boolean)
              .join(" · ");
            const pid = item.source === "local" ? `local:${item.localId}` : `remote:${item.id}`;
            const thumb = item.previewUrl || "";
            const loading = item.source === "jira" && item.href && !thumb ? " is-loading" : "";
            const action =
              item.source === "local"
                ? `<button type="button" class="ticket-file-remove" data-remove="${esc(
                    item.localId
                  )}">entfernen</button>`
                : `<button type="button" class="ticket-file-open" data-open="${esc(pid)}">öffnen</button>`;
            return `<article class="ticket-file-card" data-preview-id="${esc(pid)}" data-preview-href="${esc(
              item.href || ""
            )}" data-name="${esc(item.name)}">
              <button type="button" class="ticket-file-card-media${loading}" data-open="${esc(pid)}" aria-label="${esc(
              item.name
            )} öffnen">
                <img ${thumb ? `src="${esc(thumb)}"` : ""} alt="" loading="lazy" />
              </button>
              <div class="ticket-file-card-body">
                <div class="ticket-file-card-name" title="${esc(item.name)}">${esc(item.name)}</div>
                <div class="ticket-file-card-meta">${esc(meta)}</div>
              </div>
              <div class="ticket-file-card-actions">${action}</div>
            </article>`;
          })
          .join("");
      }
    }

    fileList.innerHTML = others
      .map((item) => {
        const shown =
          item.kind === "sheet" || isEffortSheetFile(item.name, item.kind)
            ? displayFileName(item.name)
            : item.name;
        const meta = [item.sizeLabel, item.author, item.source === "jira" ? "Jira" : "Lokal"]
          .filter(Boolean)
          .join(" · ");
        const pid = item.source === "local" ? `local:${item.localId}` : `remote:${item.id}`;
        const effort = isEffortSheetFile(item.name, item.kind);
        const icon =
          item.kind === "sheet" || effort
            ? SHEETS_ICON_SVG
            : esc(fileKindLabel(item.kind));
        let action = "";
        if (item.source === "local") {
          action = `<button type="button" class="ticket-file-remove" data-remove="${esc(
            item.localId
          )}">entfernen</button>`;
        } else if (effort) {
          action = `<button type="button" class="ticket-file-open" data-effort-open="1">öffnen</button>`;
        } else if (item.href) {
          action = `<button type="button" class="ticket-file-open" data-download="${esc(
            item.href
          )}" data-name="${esc(item.name)}">öffnen</button>`;
        }
        return `<li class="ticket-file" data-source="${esc(item.source)}" data-kind="${esc(
          effort ? "sheet" : item.kind
        )}">
          <span class="ticket-file-icon" data-kind="${esc(
            effort ? "sheet" : item.kind
          )}">${icon}</span>
          <div class="ticket-file-main">
            <span class="ticket-file-name" title="${esc(item.name)}">${esc(shown)}</span>
            <span class="ticket-file-meta">${esc(meta)}</span>
          </div>
          ${action}
        </li>`;
      })
      .join("");

    // Remote-Bilder als Blob laden
    fileGallery?.querySelectorAll(".ticket-file-card[data-preview-href]").forEach((card) => {
      const href = card.getAttribute("data-preview-href") || "";
      const id = (card.getAttribute("data-preview-id") || "").replace(/^remote:/, "");
      const img = card.querySelector("img");
      const media = card.querySelector(".ticket-file-card-media");
      if (!href || !img || !href.startsWith("/api/")) return;
      if (img.getAttribute("src")?.startsWith("blob:")) return;
      void ensureRemotePreview({ id, href }, { thumb: true }).then((url) => {
        if (!url || !img.isConnected) {
          return ensureRemotePreview({ id, href }).then((full) => {
            if (!full || !img.isConnected) {
              media?.classList.remove("is-loading");
              return;
            }
            img.src = full;
            media?.classList.remove("is-loading");
            card.dataset.blobUrl = full;
          });
        }
        img.src = url;
        media?.classList.remove("is-loading");
        card.dataset.blobUrl = url;
      });
    });
  }

  function showFiles(detail) {
    if (detail && Array.isArray(detail.attachments)) {
      remoteAttachments = detail.attachments;
    }
    renderFiles();
    syncIntakePanels();
  }

  async function uploadAttachmentFile(file) {
    if (!syncedRequestId || !file) return null;
    const body = new FormData();
    body.append("file", file, file.name);
    const r = await fetch(`/api/requests/${syncedRequestId}/attachments`, {
      method: "POST",
      body,
      credentials: "same-origin",
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Anhang-Upload fehlgeschlagen"
      );
    }
    return data;
  }

  async function addFiles(list) {
    const files = Array.from(list || []).filter(Boolean);
    if (!files.length) return;
    const pending = [];
    for (const file of files) {
      if (file.size > MAX_FILE) {
        flash(`${file.name} zu groß (max. 20 MB)`, true);
        continue;
      }
      const key = `${file.name}:${file.size}:${file.lastModified}`;
      if (attachments.some((item) => item.key === key)) continue;
      if (syncedRequestId) {
        pending.push(file);
        continue;
      }
      fileSeq += 1;
      attachments.push({
        id: String(fileSeq),
        key,
        name: file.name,
        sizeLabel: formatSize(file.size),
        file,
      });
    }
    if (fileInput) fileInput.value = "";
    if (!syncedRequestId) {
      renderFiles();
      return;
    }
    if (!pending.length) return;
    flash(
      pending.length === 1
        ? "Anhang wird hochgeladen…"
        : `${pending.length} Anhänge werden hochgeladen…`
    );
    let ok = 0;
    for (const file of pending) {
      try {
        const saved = await uploadAttachmentFile(file);
        if (saved?.id) {
          remoteAttachments = [
            ...(remoteAttachments || []).filter((a) => a.id !== saved.id),
            saved,
          ];
          ok += 1;
        }
      } catch (err) {
        flash(`${file.name}: ${err.message || err}`, true);
      }
    }
    renderFiles();
    if (ok) {
      flash(ok === 1 ? "Anhang gespeichert" : `${ok} Anhänge gespeichert`);
    }
  }

  async function flushLocalAttachments(requestId) {
    const pending = attachments.filter((item) => item.file);
    if (!requestId || !pending.length) return;
    syncedRequestId = requestId;
    const files = pending.map((item) => item.file);
    attachments.length = 0;
    await addFiles(files);
  }

  async function openAttachmentById(previewId) {
    const [source, rawId] = String(previewId || "").split(":");
    if (source === "local") {
      const item = attachments.find((a) => a.id === rawId);
      if (!item) return;
      const url = ensureLocalPreview(item);
      openLightbox(url, item.name);
      return;
    }
    if (source === "remote") {
      const meta = (remoteAttachments || []).find((a) => a.id === rawId);
      const href = syncedRequestId
        ? `/api/requests/${syncedRequestId}/attachments/${encodeURIComponent(rawId)}/content`
        : "";
      // Lightbox: volles Bild, nicht nur Thumbnail
      const url = await ensureRemotePreview({ id: rawId, href }, { thumb: false });
      if (!url) {
        flash("Vorschau konnte nicht geladen werden", true);
        return;
      }
      openLightbox(url, meta?.filename || "Anhang");
    }
  }

  async function downloadAttachment(href, name) {
    try {
      const r = await fetch(href, { credentials: "same-origin" });
      if (!r.ok) throw new Error("Download fehlgeschlagen");
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name || "anhang";
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch (err) {
      flash(String(err.message || err), true);
    }
  }

  fileAdd.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    void addFiles(fileInput.files);
  });
  fileList.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-remove]");
    if (btn) {
      const id = btn.dataset.remove;
      const idx = attachments.findIndex((item) => item.id === id);
      if (idx >= 0) {
        revokePreview(`local:${id}`);
        attachments.splice(idx, 1);
      }
      renderFiles();
      return;
    }
    const effortOpen = event.target.closest("[data-effort-open]");
    if (effortOpen) {
      event.preventDefault();
      openEffortTemplate();
      return;
    }
    const dl = event.target.closest("[data-download]");
    if (dl) {
      event.preventDefault();
      void downloadAttachment(dl.dataset.download, dl.dataset.name || "anhang");
    }
  });
  fileGallery?.addEventListener("click", (event) => {
    const remove = event.target.closest("[data-remove]");
    if (remove) {
      const id = remove.dataset.remove;
      const idx = attachments.findIndex((item) => item.id === id);
      if (idx >= 0) {
        revokePreview(`local:${id}`);
        attachments.splice(idx, 1);
      }
      renderFiles();
      return;
    }
    const open = event.target.closest("[data-open]");
    if (open) {
      event.preventDefault();
      void openAttachmentById(open.dataset.open);
    }
  });
  fileLightboxClose?.addEventListener("click", closeLightbox);
  fileLightbox?.addEventListener("click", (event) => {
    if (event.target === fileLightbox) closeLightbox();
  });
  fileGallery?.addEventListener(
    "error",
    (event) => {
      const img = event.target;
      if (!(img instanceof HTMLImageElement)) return;
      const media = img.closest(".ticket-file-card-media");
      media?.classList.remove("is-loading");
    },
    true
  );

  syncPrompt();

  (window.whenAuthed || Promise.resolve()).then((user) => {
    window.currentActor = user || window.currentActor;
    const name = String(user?.displayName || "").trim();
    window.currentActorName = name;
    if ((user?.jiraName || name) && !ticket.hidden) showAuthor();
  });

  let publishing = false;
  let pendingDelete = null;
  let hubItems = [];
  let hubFocusIndex = -1;
  let liveComments = [];
  let hubView = "list";
  const DRAFT_KEY = "critr-comment-draft-v1";
  const SCROLL_KEY = "critr-scroll-v1";
  const HUB_SCROLL_KEY = "critr-hub-scroll-v1";
  const HUB_VIEW_KEY = "critr-hub-view-v1";
  // Feste Kanban-Spalten (auch leer anzeigen)
  const HUB_STATUS_COLUMNS = [
    "Konzept",
    "IT",
    "Quality Gate",
    "Controlling",
    "In Freigabe",
    "Freigegeben",
  ];

  function flash(message, err, action) {
    const el = document.getElementById("toast");
    const msg = document.getElementById("toast-msg");
    const btn = document.getElementById("toast-action");
    if (!el) return;
    if (msg) msg.textContent = message;
    else el.textContent = message;
    el.classList.toggle("err", Boolean(err));
    el.classList.add("show");
    if (btn) {
      if (action && typeof action.onClick === "function") {
        btn.hidden = false;
        btn.textContent = action.label || "Rückgängig";
        btn.onclick = (event) => {
          event.preventDefault();
          action.onClick();
          el.classList.remove("show");
          btn.hidden = true;
          btn.onclick = null;
        };
      } else {
        btn.hidden = true;
        btn.onclick = null;
      }
    }
    window.clearTimeout(flash.tid);
    const ms = action?.duration || (err ? 4200 : 3200);
    flash.tid = window.setTimeout(() => {
      el.classList.remove("show");
      if (btn) {
        btn.hidden = true;
        btn.onclick = null;
      }
    }, ms);
  }

  function draftStore() {
    try {
      return JSON.parse(localStorage.getItem(DRAFT_KEY) || "{}") || {};
    } catch (_) {
      return {};
    }
  }

  function saveDraft(requestId, text) {
    if (!requestId) return;
    const store = draftStore();
    const body = String(text || "");
    if (!body.trim()) delete store[requestId];
    else store[requestId] = body;
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(store));
    } catch (_) {
      /* ignore */
    }
  }

  function loadDraft(requestId) {
    if (!requestId || !commentInput) return;
    const body = draftStore()[requestId] || "";
    if (commentInput.value !== body) {
      commentInput.value = body;
      updateCommentPreview();
    }
  }

  function saveScrollMemory() {
    const view = document.getElementById("ticket-view");
    const wrap = document.getElementById("table-wrap");
    try {
      if (syncedRequestId && view) {
        sessionStorage.setItem(
          SCROLL_KEY,
          JSON.stringify({ id: syncedRequestId, y: view.scrollTop })
        );
      }
      if (wrap && !document.body.classList.contains("ticket-active")) {
        sessionStorage.setItem(HUB_SCROLL_KEY, String(wrap.scrollTop || 0));
      }
    } catch (_) {
      /* ignore */
    }
  }

  function restoreTicketScroll(requestId) {
    const view = document.getElementById("ticket-view");
    if (!view) return;
    try {
      const raw = JSON.parse(sessionStorage.getItem(SCROLL_KEY) || "null");
      if (raw?.id === requestId) {
        window.requestAnimationFrame(() => {
          view.scrollTop = Number(raw.y) || 0;
        });
      }
    } catch (_) {
      /* ignore */
    }
  }

  function restoreHubScroll() {
    const wrap = document.getElementById("table-wrap");
    if (!wrap) return;
    try {
      const y = Number(sessionStorage.getItem(HUB_SCROLL_KEY) || 0);
      window.requestAnimationFrame(() => {
        wrap.scrollTop = y;
      });
    } catch (_) {
      /* ignore */
    }
  }

  function updateOfflineBanner() {
    const el = document.getElementById("hub-offline");
    if (!el) return;
    el.hidden = navigator.onLine !== false;
  }

  window.addEventListener("online", updateOfflineBanner);
  window.addEventListener("offline", updateOfflineBanner);
  updateOfflineBanner();
  window.addEventListener("beforeunload", saveScrollMemory);

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
    delete fields.attachments_ask;
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
            if (valueEl) writeFieldValue(valueEl, step, label);
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
    const sep = document.getElementById("ticket-eyebrow-sep");
    if (!badge || !badgeKey) return;
    if (!key) {
      badge.hidden = true;
      if (sep) sep.hidden = true;
      badgeKey.textContent = "";
      badgeKey.removeAttribute("href");
      badgeKey.removeAttribute("title");
      return;
    }
    badge.hidden = false;
    if (sep) sep.hidden = false;
    badgeKey.textContent = key;
    const browse = jiraBrowseUrl(key, jiraUrl);
    if (browse) {
      badgeKey.href = browse;
      badgeKey.setAttribute("title", `In Jira öffnen: ${key}`);
    } else {
      badgeKey.removeAttribute("href");
      badgeKey.removeAttribute("title");
    }
  }

  let jiraFollowId = null;
  let jiraFollowGen = 0;

  async function pollJiraKey(requestId, attempts = 40, gen = 0) {
    for (let i = 0; i < attempts; i += 1) {
      if (gen && gen !== jiraFollowGen) {
        return { jiraKey: null, reference: null, jiraUrl: "", syncError: null, cancelled: true };
      }
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
        const err = String(sync.lastError || "").trim();
        const permanent =
          /is required|parsing date|does not exist|could not find usernames|option id/i.test(
            err
          );
        // Endgültig oder klarer Jira-400: nicht bis Timeout warten.
        if (sync.state === "dead" || (err && (permanent || (sync.state === "failed" && i >= 2)))) {
          return {
            jiraKey: null,
            reference: body.reference || null,
            jiraUrl: "",
            syncError: err || "Jira-Anlage fehlgeschlagen",
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

  function followJiraSync(detail) {
    const id = detail?.id;
    if (!id) return;
    const sync = detail.sync || {};
    const key = sync.externalKey || detail.externalKey || "";
    const url = sync.externalUrl || detail.externalUrl || detail.jiraUrl || "";
    if (key) {
      showJiraBadge(key, url);
      jiraFollowId = null;
      return;
    }
    const state = String(sync.state || "").toLowerCase();
    // Kein Sync erwartet / aus — nicht 30s pollen.
    if (state === "disabled" || state === "synced") {
      if (detail.reference) showJiraBadge(detail.reference, "");
      return;
    }
    const localRef = detail.reference || "Ticket";
    showJiraBadge(localRef, "");
    if (state === "dead") {
      if (sync.lastError) flash(String(sync.lastError), true);
      return;
    }
    if (jiraFollowId === id) return; // schon am Nachziehen
    jiraFollowId = id;
    const gen = ++jiraFollowGen;
    setIntro(`${localRef} — Jira sync…`);
    void pollJiraKey(id, 40, gen).then((polled) => {
      if (polled.cancelled || syncedRequestId !== id || gen !== jiraFollowGen) return;
      jiraFollowId = null;
      if (polled.jiraKey) {
        showJiraBadge(polled.jiraKey, polled.jiraUrl || "");
        showFinishActions(polled.jiraKey, polled.jiraUrl || "", { newChange: true });
        flash(`${polled.jiraKey} in Jira angelegt`);
        setIntro(`${polled.jiraKey} in Jira`);
        return;
      }
      if (polled.reference) showJiraBadge(polled.reference, "");
      if (polled.syncError) {
        flash(String(polled.syncError), true);
        setIntro(`${localRef}: ${polled.syncError}`);
      }
    });
  }

  async function publishToJira() {
    if (publishing) return;
    if (!values.title || !values.description) {
      flash("Titel und Beschreibung fehlen.", true);
      return;
    }
    publishing = true;
    setJiraCreateBusy("Wird angelegt…");
    const kind = ticketKind() === "it_request" ? "it_request" : "change_request";
    const priority = "medium";
    try {
      await normalizeJiraLookupFields();
      const body = await createViaLegacyPublish(kind, priority, false);
      const localRef = body.reference || body.ticketKey || "lokal";
      if (body.requestId) syncedRequestId = body.requestId;
      showJiraBadge(localRef, "");
      setIntro(`${localRef} lokal angelegt — Jira-Nummer folgt…`);
      flash(`${localRef} lokal angelegt`);
      setJiraCreateBusy("Jira sync…");

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
        setJiraCreateIdle();
        const err = syncError || "Jira-Anlage fehlgeschlagen";
        setIntro(`${localRef}: ${err}`);
        flash(err, true);
        return;
      }
      if (body.requestId) await flushLocalAttachments(body.requestId);
      showJiraBadge(key, jiraUrl);
      showFinishActions(key, jiraUrl, { newChange: true });
      flash(`${key} in Jira angelegt`);
      publishing = false;
    } catch (err) {
      publishing = false;
      setJiraCreateIdle();
      flash(String(err.message || err), true);
    }
  }

  jiraCreateButtons().forEach((btn) => {
    btn.addEventListener("click", publishToJira);
  });

  aiReviewOk?.addEventListener("click", () => {
    confirmAiReview();
  });

  newChangeBtn?.addEventListener("click", () => {
    location.assign("/workspace");
  });

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatCommentHtml(text) {
    let html = escapeHtml(text);
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, "$1<em>$2</em>");
    html = html.replace(
      /(https?:\/\/[^\s<]+)/g,
      '<a href="$1" target="_blank" rel="noopener">$1</a>'
    );
    html = html.replace(/@([A-Za-zÄÖÜäöüß0-9._-]{2,80})/g, '<span class="comment-at">@$1</span>');
    return html.replace(/\n/g, "<br>");
  }

  function updateCommentPreview() {
    if (!commentPreview || !commentInput) return;
    const raw = commentInput.value.trim();
    if (!raw || !/[*_`@]|https?:\/\//.test(raw)) {
      commentPreview.hidden = true;
      commentPreview.innerHTML = "";
      return;
    }
    commentPreview.hidden = false;
    commentPreview.innerHTML = formatCommentHtml(raw);
  }

  let mentionTimer = 0;
  let mentionStart = -1;

  function hideMentions() {
    if (!commentMention) return;
    commentMention.hidden = true;
    commentMention.replaceChildren();
    mentionStart = -1;
    updateCommentFormHint();
  }

  async function fetchMentions(q) {
    const r = await fetch(`/api/jira/users?q=${encodeURIComponent(q)}&limit=8`);
    if (!r.ok) return [];
    const body = await r.json().catch(() => ({}));
    return body.items || [];
  }

  function insertMention(displayName) {
    if (!commentInput || mentionStart < 0) return;
    const before = commentInput.value.slice(0, mentionStart);
    const after = commentInput.value.slice(commentInput.selectionStart);
    const token = `@${displayName} `;
    commentInput.value = `${before}${token}${after}`;
    const pos = (before + token).length;
    commentInput.setSelectionRange(pos, pos);
    commentInput.focus();
    hideMentions();
    updateCommentPreview();
    updateCommentFormHint();
  }

  function renderMentionList(items) {
    if (!commentMention) return;
    commentMention.replaceChildren();
    if (!items.length) {
      hideMentions();
      return;
    }
    for (const item of items) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "comment-mention-item";
      const avatar = document.createElement("span");
      avatar.className = "comment-mention-avatar";
      const name = item.displayName || item.name || item.label || "?";
      if (item.avatarUrl) {
        const img = document.createElement("img");
        img.src = item.avatarUrl;
        img.alt = "";
        avatar.appendChild(img);
      } else {
        avatar.textContent = commentInitials(name);
      }
      const label = document.createElement("span");
      label.textContent = name;
      btn.append(avatar, label);
      btn.addEventListener("mousedown", (event) => {
        event.preventDefault();
        insertMention(item.displayName || item.name);
      });
      commentMention.appendChild(btn);
    }
    commentMention.hidden = false;
    updateCommentFormHint();
  }

  function onCommentInput() {
    updateCommentPreview();
    updateCommentFormHint();
    if (syncedRequestId && commentInput) saveDraft(syncedRequestId, commentInput.value);
    if (!commentInput) return;
    const value = commentInput.value;
    const caret = commentInput.selectionStart || 0;
    const left = value.slice(0, caret);
    const match = left.match(/@([A-Za-zÄÖÜäöüß0-9._-]{0,40})$/);
    if (!match) {
      hideMentions();
      return;
    }
    mentionStart = caret - match[0].length;
    const q = match[1] || "";
    window.clearTimeout(mentionTimer);
    mentionTimer = window.setTimeout(() => {
      void fetchMentions(q).then(renderMentionList).catch(hideMentions);
    }, 180);
  }

  function commentDayLabel(ms) {
    const d = new Date(ms);
    const today = new Date();
    const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const startThat = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diffDays = Math.round((startToday - startThat) / 86400000);
    if (diffDays === 0) return "Heute";
    if (diffDays === 1) return "Gestern";
    return d.toLocaleDateString("de-DE", {
      weekday: "long",
      day: "numeric",
      month: "long",
    });
  }

  function formatCommentWhen(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const diffMs = Date.now() - d.getTime();
    const mins = Math.round(diffMs / 60000);
    if (mins < 1) return "gerade eben";
    if (mins < 60) return `vor ${mins} Min.`;
    return d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  }

  function commentInitials(name) {
    const parts = String(name || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    if (!parts.length) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  const COMMENT_VISIT_KEY = "critr-comment-visit-v1";
  let commentHintPaste = false;
  const commentFormHint = document.getElementById("comment-form-hint");

  function commentVisitStore() {
    try {
      return JSON.parse(localStorage.getItem(COMMENT_VISIT_KEY) || "{}") || {};
    } catch (_) {
      return {};
    }
  }

  function lastCommentVisit(requestId) {
    if (!requestId) return "";
    return String(commentVisitStore()[requestId] || "");
  }

  function markCommentVisit(requestId) {
    if (!requestId) return;
    const store = commentVisitStore();
    store[requestId] = new Date().toISOString();
    try {
      localStorage.setItem(COMMENT_VISIT_KEY, JSON.stringify(store));
    } catch (_) {
      /* ignore */
    }
  }

  function updateCommentFormHint() {
    if (!commentFormHint) return;
    const bits = [];
    if (!commentMention?.hidden) bits.push("@Mention wählen");
    else if (commentInput && /(?:^|\s)@\w/.test(commentInput.value)) {
      bits.push("@Person erwähnen");
    }
    if (commentHintPaste) bits.push("Screenshot wird angehängt");
    if (!bits.length) {
      commentFormHint.hidden = true;
      commentFormHint.textContent = "";
      return;
    }
    commentFormHint.hidden = false;
    commentFormHint.textContent = bits.join(" · ");
  }

  function paintComments(items) {
    if (!commentList) return;
    liveComments = Array.isArray(items) ? items.slice() : [];
    if (commentCount) {
      commentCount.hidden = true;
      commentCount.textContent = "";
    }
    commentList.replaceChildren();
    if (!liveComments.length) {
      const empty = document.createElement("li");
      empty.className = "comment-empty";
      empty.innerHTML =
        "<strong>Noch keine Kommentare.</strong><span>Notiz unten schreiben — sie erscheint hier und in Jira.</span>";
      commentList.appendChild(empty);
      return;
    }

    const visitAt = lastCommentVisit(syncedRequestId);
    const visitMs = visitAt ? Date.parse(visitAt) : NaN;
    let splitDone = false;
    let lastDay = "";
    let lastAuthor = "";

    for (const c of liveComments) {
      const createdMs = c.createdAt ? Date.parse(c.createdAt) : NaN;
      const dayKey = Number.isFinite(createdMs)
        ? new Date(createdMs).toLocaleDateString("de-DE")
        : "";
      if (dayKey && dayKey !== lastDay) {
        const day = document.createElement("li");
        day.className = "comment-day";
        day.textContent = commentDayLabel(createdMs);
        commentList.appendChild(day);
        lastDay = dayKey;
        lastAuthor = "";
      }
      const isNew =
        Number.isFinite(visitMs) &&
        Number.isFinite(createdMs) &&
        createdMs > visitMs &&
        !c.pending;
      if (isNew && !splitDone) {
        const split = document.createElement("li");
        split.className = "comment-visit-split";
        split.textContent = "Neu seit deinem letzten Besuch";
        commentList.appendChild(split);
        splitDone = true;
        lastAuthor = "";
      }

      const li = document.createElement("li");
      li.className = "comment-item";
      const authorName = c.author || "unbekannt";
      if (authorName === lastAuthor) li.classList.add("is-follow");
      lastAuthor = authorName;
      if (c.pending) li.classList.add("is-pending");
      if (c.failed) li.classList.add("is-failed");
      li.dataset.id = c.id || "";
      const avatar = document.createElement("span");
      avatar.className = "comment-avatar";
      avatar.textContent = commentInitials(c.author);
      avatar.setAttribute("aria-hidden", "true");
      const main = document.createElement("div");
      main.className = "comment-main";
      const meta = document.createElement("div");
      meta.className = "comment-meta";
      const author = document.createElement("strong");
      author.textContent = authorName;
      const right = document.createElement("span");
      right.className = "comment-meta-right";
      const when = document.createElement("time");
      when.className = "comment-when";
      when.dateTime = c.createdAt || "";
      when.textContent = c.pending ? "wird gesendet…" : formatCommentWhen(c.createdAt);
      when.title = c.createdAt ? new Date(c.createdAt).toLocaleString("de-DE") : "";
      right.append(when);
      if (c.failed) {
        const retry = document.createElement("button");
        retry.type = "button";
        retry.className = "comment-retry";
        retry.textContent = "Erneut senden";
        retry.addEventListener("click", () => {
          void retryComment(c);
        });
        right.append(retry);
      } else if (!c.pending && c.id && !String(c.id).startsWith("tmp-")) {
        const del = document.createElement("button");
        del.type = "button";
        del.className = "comment-delete";
        del.textContent = "Löschen";
        del.title = "Kommentar löschen";
        del.setAttribute("aria-label", "Kommentar löschen");
        del.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          scheduleDeleteComment(c);
        });
        right.append(del);
      }
      meta.append(author, right);
      const body = document.createElement("div");
      body.className = "comment-body";
      body.innerHTML = formatCommentHtml(c.body || "");
      main.append(meta, body);
      li.append(avatar, main);
      commentList.appendChild(li);
    }
  }

  async function postCommentForRequest(requestId, body) {
    if (!requestId || !body) return false;
    const r = await fetch(`/api/requests/${requestId}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body }),
    });
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      throw new Error(
        typeof data.detail === "string" ? data.detail : "Kommentar fehlgeschlagen"
      );
    }
    return true;
  }

  function todoLabel(text) {
    return String(text || "")
      .trim()
      .replace(/\s+/g, " ")
      .replace(/[.!?]+$/, "");
  }

  function standNorm(text) {
    return String(text || "")
      .toLowerCase()
      .replace(/[^a-z0-9äöüß]+/g, "");
  }

  function standWithoutTodoEcho(stand) {
    return String(stand || "").trim();
  }

  function appendStandSentence(sentence) {
    if (!commentAblauf) return;
    let add = String(sentence || "").trim().replace(/\s+/g, " ");
    if (!add) return;
    if (!/[.!?]$/.test(add)) add += ".";
    add = add.replace(/^[•\-–*]+\s*/, "");
    const cur = String(commentAblauf.textContent || "").trim();
    if (standNorm(cur).includes(standNorm(add))) return;
    commentAblauf.textContent = cur ? `${cur} ${add}` : add;
    commentAblauf.classList.remove("is-empty");
    if (commentStand) commentStand.hidden = false;
  }

  function standRelativeTime(iso) {
    if (!iso) return "";
    const then = new Date(iso).getTime();
    if (!Number.isFinite(then)) return "";
    const mins = Math.round((Date.now() - then) / 60000);
    if (mins < 1) return "gerade eben";
    if (mins < 60) return `vor ${mins} Min.`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `vor ${hours} Std.`;
    const days = Math.round(hours / 24);
    if (days < 14) return `vor ${days} Tag${days === 1 ? "" : "en"}`;
    return new Date(iso).toLocaleDateString("de-DE", {
      day: "numeric",
      month: "short",
    });
  }

  window.applyStandHealth = function (requestId, key) {
    if (!requestId || requestId !== syncedRequestId || !commentStand) return;
    const value = String(key || "green").toLowerCase();
    commentStand.dataset.health = value;
  };

  function paintStandHealth(detail) {
    if (!commentStand) return;
    const health = detail?.standHealth || {};
    const allowed = new Set(["green", "blue", "yellow", "red", "white", "done"]);
    const key = String(health.key || "green").toLowerCase();
    commentStand.dataset.health = allowed.has(key) ? key : "green";
  }

  function paintStandMeta(_detail, { waiting = false } = {}) {
    if (!commentStandMeta) return;
    commentStandMeta.textContent = waiting ? "wartet auf dich" : "";
    commentStandMeta.removeAttribute("title");
  }

  function renderComments(detail) {
    if (!commentsSection || !commentList) return;
    if (!syncedRequestId) {
      commentsSection.hidden = true;
      if (commentStand) {
        commentStand.hidden = true;
        commentStand.classList.remove("is-waiting");
        delete commentStand.dataset.health;
      }
      if (commentAblauf) {
        commentAblauf.textContent = "";
        commentAblauf.classList.add("is-empty");
      }
      if (commentStandMeta) commentStandMeta.textContent = "";
      if (commentCount) {
        commentCount.hidden = true;
        commentCount.textContent = "";
      }
      return;
    }
    commentsSection.hidden = !commentsAllowed();
    if (!commentsAllowed()) {
      if (commentStand) {
        commentStand.hidden = true;
        commentStand.classList.remove("is-waiting");
        delete commentStand.dataset.health;
      }
      return;
    }
    const ablauf = (detail.commentAblauf || "").trim();
    const statusAblauf = (detail.statusAblauf || "").trim();
    // Gleicher Stand wie in der Liste: Ablauf, sonst Kurzzeile (standSummary).
    const standBody = standWithoutTodoEcho(
      ablauf || statusAblauf || String(detail.standSummary || detail.commentSummary || "").trim()
    );
    const waiting = Boolean(detail.waitingOnMe);
    if (commentStand && commentAblauf) {
      if (intakeTailOpen() && (standBody || syncedRequestId)) {
        commentStand.hidden = false;
        commentAblauf.textContent = standBody;
        commentAblauf.classList.toggle("is-empty", !standBody);
        paintStandHealth(detail);
        paintStandMeta(detail, { waiting });
      } else {
        commentStand.hidden = true;
        commentAblauf.textContent = "";
        commentAblauf.classList.add("is-empty");
        if (commentStandMeta) commentStandMeta.textContent = "";
        commentStand.classList.remove("is-waiting");
        delete commentStand.dataset.health;
      }
    }
    paintComments(detail.comments || []);
  }

  function scheduleDeleteComment(comment) {
    if (!syncedRequestId || !comment?.id) return;
    const requestId = syncedRequestId;
    const snapshot = { ...comment };
    liveComments = liveComments.filter((c) => c.id !== comment.id);
    paintComments(liveComments);
    // Sofort löschen — sonst bringt Reload den Kommentar zurück
    void finalizeDeleteComment(snapshot, requestId);
    if (pendingDelete?.timer) window.clearTimeout(pendingDelete.timer);
    pendingDelete = {
      comment: snapshot,
      requestId,
      undone: false,
      timer: window.setTimeout(() => {
        pendingDelete = null;
      }, 5000),
    };
    flash("Kommentar gelöscht", false, {
      label: "Rückgängig",
      duration: 5000,
      onClick: () => {
        if (pendingDelete?.timer) window.clearTimeout(pendingDelete.timer);
        const snap = pendingDelete?.comment || snapshot;
        const rid = pendingDelete?.requestId || requestId;
        pendingDelete = null;
        if (rid !== syncedRequestId) return;
        if (!liveComments.some((c) => c.id === snap.id || c.body === snap.body)) {
          const tempId = `tmp-restore-${Date.now()}`;
          liveComments = [
            ...liveComments,
            {
              id: tempId,
              author: snap.author || "Du",
              body: snap.body || "",
              createdAt: snap.createdAt || new Date().toISOString(),
              pending: true,
              failed: false,
            },
          ].sort((a, b) =>
            String(a.createdAt || "").localeCompare(String(b.createdAt || ""))
          );
          paintComments(liveComments);
          void postCommentBody(snap.body || "", tempId);
        }
      },
    });
  }

  async function finalizeDeleteComment(comment, requestId) {
    if (!comment?.id || !requestId) return;
    try {
      const r = await fetch(
        `/api/requests/${requestId}/comments/${encodeURIComponent(comment.id)}`,
        { method: "DELETE" }
      );
      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        flash(typeof data.detail === "string" ? data.detail : "Löschen fehlgeschlagen", true);
        if (requestId === syncedRequestId && !liveComments.some((c) => c.id === comment.id)) {
          liveComments.push(comment);
          paintComments(liveComments);
        }
      }
    } catch (err) {
      flash(String(err.message || err), true);
      if (requestId === syncedRequestId && !liveComments.some((c) => c.id === comment.id)) {
        liveComments.push(comment);
        paintComments(liveComments);
      }
    }
  }

  async function retryComment(comment) {
    if (!syncedRequestId || !comment) return;
    liveComments = liveComments.map((c) =>
      c.id === comment.id ? { ...c, pending: true, failed: false } : c
    );
    paintComments(liveComments);
    await postCommentBody(comment.body, comment.id);
  }

  async function postCommentBody(body, tempId) {
    const requestId = syncedRequestId;
    if (!requestId || !body) return;
    try {
      const r = await fetch(`/api/requests/${requestId}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Kommentar fehlgeschlagen"
        );
      }
      if (requestId !== syncedRequestId) return;
      liveComments = liveComments.map((c) =>
        c.id === tempId
          ? {
              id: data.id,
              author: data.author || c.author,
              body: data.body || body,
              createdAt: data.createdAt || c.createdAt,
              pending: false,
              failed: false,
            }
          : c
      );
      paintComments(liveComments);
      applyStandFromPayload(data);
      if (data.standPending) void pollStandUpgrade(requestId);
    } catch (err) {
      if (requestId !== syncedRequestId) return;
      liveComments = liveComments.map((c) =>
        c.id === tempId ? { ...c, pending: false, failed: true } : c
      );
      paintComments(liveComments);
      flash(String(err.message || err), true);
    }
  }

  function applyStandFromPayload(data) {
    if (!commentAblauf) return;
    const ablauf = String(data?.commentAblauf || "").trim();
    if (!ablauf) return;
    if (commentStand) commentStand.hidden = false;
    const cleaned = standWithoutTodoEcho(ablauf);
    commentAblauf.textContent = cleaned || ablauf;
    commentAblauf.classList.toggle("is-empty", !(cleaned || ablauf));
  }

  async function pollStandUpgrade(requestId) {
    for (let i = 0; i < 8; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 700 + i * 200));
      if (requestId !== syncedRequestId) return;
      try {
        const r = await fetch(`/api/requests/${requestId}`);
        if (!r.ok) continue;
        const detail = await r.json();
        if (requestId !== syncedRequestId) return;
        const digest = String(detail.standDigest || "");
        applyStandFromPayload({
          commentAblauf: detail.commentAblauf,
          commentSummary: detail.commentSummary || detail.standSummary,
          standSummary: detail.standSummary,
        });
        // draft:… = Fallback; ohne Prefix = LLM fertig
        if (digest && !digest.startsWith("draft:")) return;
      } catch {
        /* ignore */
      }
    }
  }

  async function submitComment(event) {
    event.preventDefault();
    if (!commentsAllowed() || !syncedRequestId || !commentInput) return;
    const body = commentInput.value.trim();
    if (!body) return;
    const tempId = `tmp-${Date.now()}`;
    const author =
      window.currentActorName ||
      window.currentActor?.displayName ||
      window.currentActor?.jiraName ||
      "Du";
    const optimistic = {
      id: tempId,
      author,
      body,
      createdAt: new Date().toISOString(),
      pending: true,
      failed: false,
    };
    liveComments = [...liveComments, optimistic];
    paintComments(liveComments);
    commentInput.value = "";
    saveDraft(syncedRequestId, "");
    hideMentions();
    updateCommentPreview();
    if (commentSend) commentSend.disabled = true;
    try {
      await postCommentBody(body, tempId);
    } finally {
      if (commentSend) commentSend.disabled = false;
      commentInput?.focus();
    }
  }

  /** Kein Rest vom vorher geöffneten Change — sonst wandern Werte ins falsche Ticket. */
  function resetTicketState() {
    loadedTicket = false;
    for (const key of Object.keys(values)) delete values[key];
    for (const key of Object.keys(labels)) delete labels[key];
    costFields.replaceChildren();
    overviewFields.replaceChildren();
    contextFields.replaceChildren();
    teamFields.replaceChildren();
    solutionFields.replaceChildren();
    metaRoot.querySelectorAll("[data-key]").forEach((cell) => {
      const el = cell.querySelector(".ticket-row-value");
      if (el) writeFieldValue(el, stepByKey(cell.dataset.key), "");
      cell.hidden = true;
    });
    fieldsRoot.querySelectorAll(".ticket-row").forEach((row) => row.remove());
    headline.textContent = "";
    showJiraBadge("");
    attachments.length = 0;
    remoteAttachments = [];
    standUpdates = [];
    if (standForm) {
      standForm.hidden = true;
      standForm.reset();
    }
    if (standError) standError.hidden = true;
    if (effortSheetOpen) effortSheetOpen.textContent = "Vorlage öffnen";
    const hintEl = costHintEl();
    if (hintEl) hintEl.textContent = "Vorlage öffnen, Kalkulation ausfüllen, Fenster schließen.";
  }

  function ptLines(blob) {
    const rows = [];
    const re = /(\d+(?:[.,]\d+)?)\s*PT\s+([^;]+)/gi;
    const text = String(blob || "");
    let match = re.exec(text);
    while (match) {
      const name = match[2].trim();
      if (name) rows.push({ name, plan: parsePt(match[1]) });
      match = re.exec(text);
    }
    const merged = [];
    for (const row of rows) {
      const hit = merged.find((item) => item.name.toLowerCase() === row.name.toLowerCase());
      if (hit) hit.plan += row.plan;
      else merged.push({ ...row });
    }
    return merged;
  }

  function scsPlanPt() {
    const effort = parsePt(values.effort_fb);
    if (effort) return effort;
    return parsePt(values.concept_scs_pt) + parsePt(values.operate_scs_pt);
  }

  function itPlanPt() {
    const effort = parsePt(values.effort_it);
    if (effort) return effort;
    return parsePt(values.concept_cit_pt) + parsePt(values.operate_cit_pt);
  }

  function planPeople() {
    const named = ptLines(
      [values.concept_scs_pt_detail, values.operate_scs_pt_detail].filter(Boolean).join("; ")
    );
    const rows = named.length ? named : [];
    if (!rows.length && scsPlanPt()) rows.push({ name: "SCS", plan: scsPlanPt() });
    if (itPlanPt()) rows.push({ name: "IT", plan: itPlanPt() });
    return rows;
  }

  function fieldDateIso(key) {
    return dateIso(values[key] || values[`${key}_date`] || "");
  }

  function dateIso(raw) {
    const s = String(raw || "").trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    return deToIso(s);
  }

  function showDate(raw) {
    const iso = dateIso(raw);
    if (iso) return isoToDe(iso);
    return String(raw || "").trim();
  }

  function fmtPt(n) {
    const value = Number(n);
    if (!value) return "—";
    return value.toLocaleString("de-DE", { maximumFractionDigits: 2 });
  }

  function moneyOrNull(raw) {
    const s = String(raw ?? "").trim();
    if (!s) return null;
    return parseMoney(s);
  }

  function fmtEuro(n) {
    if (n == null) return "—";
    return `${Number(n).toLocaleString("de-DE", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} €`;
  }

  function moneyTriple(fb, it, lic) {
    const parts = [fb, it, lic].filter((n) => n != null);
    return {
      fb,
      it,
      lic,
      sum: parts.length ? parts.reduce((a, b) => a + b, 0) : null,
    };
  }

  function planMoney() {
    return moneyTriple(
      moneyOrNull(values.costs),
      moneyOrNull(values.it_costs),
      moneyOrNull(values.material_costs)
    );
  }

  function actualMoney(update) {
    if (!update) return moneyTriple(null, null, null);
    return moneyTriple(
      moneyOrNull(update.costActualFb),
      moneyOrNull(update.costActualIt),
      moneyOrNull(update.costActualLicense)
    );
  }

  function sortedStands() {
    return [...standUpdates].sort((a, b) =>
      String(a.reportedOn || a.createdAt || "").localeCompare(
        String(b.reportedOn || b.createdAt || "")
      )
    );
  }

  function latestStand() {
    const list = sortedStands();
    return list.length ? list[list.length - 1] : null;
  }

  function actualPtMap(update) {
    const map = {};
    for (const row of update?.milestones || []) {
      if (!row || row.kind !== "pt") continue;
      const name = String(row.name || "").trim();
      if (!name) continue;
      map[name.toLowerCase()] = parsePt(row.actual);
    }
    return map;
  }

  function computeScheduleRag(planEnd, actualEnd, planPt, actualPt, hasIst) {
    if (!hasIst) return "blue";
    const late = Boolean(planEnd && actualEnd && actualEnd > planEnd);
    const over = planPt > 0 && actualPt > planPt + 0.001;
    return late || over ? "red" : "green";
  }

  function computeCostRag(plan, actual) {
    if (actual.sum == null) return "blue";
    if (plan.sum != null && actual.sum > plan.sum + 0.001) return "red";
    return "green";
  }

  function shownRag(stored, reason, computed) {
    const key = String(stored || "").toLowerCase();
    if (String(reason || "").trim() && (key === "red" || key === "green")) return key;
    return computed;
  }

  function ragLabel(key) {
    if (key === "red") return "Überzogen";
    if (key === "green") return "Im Plan";
    return "Offen";
  }

  function protocolText(update) {
    const reason = String(update.scheduleReason || "").trim();
    if (reason) return reason;
    const bits = (update.milestones || [])
      .filter((row) => row && row.kind === "pt" && String(row.actual || "").trim())
      .map((row) => `${row.name} ${fmtPt(parsePt(row.actual))}`);
    if (!bits.length) return "";
    const date = showDate(update.reportedOn) || "Stand";
    return `PT Stand ${date}: ${bits.join(" · ")}`;
  }

  function standRows(pairs, { html = false } = {}) {
    return pairs
      .map(
        ([name, value]) =>
          `<div class="stand-line${name === "Summe" ? " is-sum" : ""}"><span>${esc(
            name
          )}</span><span>${html ? value : esc(value)}</span></div>`
      )
      .join("");
  }

  function istControl(key, value, mode) {
    const type = mode === "date" ? "date" : "text";
    return `<input class="stand-ist" data-stand-key="${esc(key)}" type="${type}" value="${esc(
      value || ""
    )}" placeholder="—" />`;
  }

  function noteLines() {
    const out = [];
    for (const update of sortedStands()) {
      const reason = String(update.scheduleReason || "").trim();
      if (reason) {
        out.push(...reason.split("\n").map((line) => line.trim()).filter(Boolean));
        continue;
      }
      const line = protocolText(update);
      if (line) out.push(line);
    }
    return out;
  }

  function renderStandBoard() {
    // Changebeschreibung/Entscheidungen/Risiken/Nächste Schritte nur noch in Status update.
  }

  function standField(id) {
    return document.getElementById(id);
  }

  function fillStandFields(latest) {
    const summary = standField("stand-summary");
    const decisions = standField("stand-decisions");
    const risks = standField("stand-risks");
    const next = standField("stand-live-next");
    if (summary && document.activeElement !== summary && summary.dataset.user !== "1") {
      summary.value = String(latest?.summary || "");
    }
    if (decisions && document.activeElement !== decisions && decisions.dataset.user !== "1") {
      decisions.value = String(latest?.decisions || "");
    }
    if (risks && document.activeElement !== risks && risks.dataset.user !== "1") {
      const saved = String(latest?.risks || "").trim();
      const known = String(values.risks || values.risks_obstacles || "").trim();
      if (saved && saved !== known) risks.value = saved;
      else void fillRiskFromStatus();
    }
    if (next && document.activeElement !== next && next.dataset.user !== "1") {
      const saved = String(latest?.nextSteps || "").trim();
      const text = saved || nextFromComments();
      next.placeholder = "";
      if (text) next.value = text;
    }
    for (const field of [summary, decisions, risks, next]) fitStandField(field);
  }

  function nextFromComments() {
    const list = liveComments
      .filter((row) => {
        const body = String(row?.body || "").replace(/\s+/g, " ").trim();
        return body.length > 2;
      })
      .sort((a, b) => String(a.createdAt || "").localeCompare(String(b.createdAt || "")));
    const body = String((list.length ? list[list.length - 1].body : "") || "")
      .replace(/\s+/g, " ")
      .trim();
    if (!body) return "";
    const match = body.match(/\b((?:es |man )?muss\b.+)$/i);
    let text = (match ? match[1] : body).trim();
    if (text[0] && text[0] === text[0].toLowerCase()) text = text[0].toUpperCase() + text.slice(1);
    if (!/[.!?]$/.test(text)) text += ".";
    return text;
  }

  function fitStandField(field) {
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${field.scrollHeight}px`;
  }

  async function saveStandTexts() {
    if (!syncedRequestId || !commentsAllowed()) return;
    const summary = standField("stand-summary")?.value.trim() || "";
    const decisions = standField("stand-decisions")?.value.trim() || "";
    const risks = standField("stand-risks")?.value.trim() || "";
    const nextSteps = standField("stand-live-next")?.value.trim() || "";
    const latest = latestStand();
    const payload = { summary, decisions, risks, nextSteps };
    const response = latest?.id
      ? await fetch(`/api/requests/${syncedRequestId}/status-updates/${latest.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
      : await fetch(`/api/requests/${syncedRequestId}/status-updates`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
    if (!response.ok) return;
    const saved = await response.json();
    const idx = standUpdates.findIndex((item) => item.id === saved.id);
    if (idx >= 0) standUpdates[idx] = saved;
    else standUpdates.push(saved);
  }

  async function fillRiskFromStatus() {
    const box = standField("stand-risks");
    if (!box || !commentsAllowed() || !syncedRequestId) return;
    if (box.dataset.user === "1" || box.dataset.loading === syncedRequestId) return;
    box.dataset.loading = syncedRequestId;
    const ticketId = syncedRequestId;
    try {
      const response = await fetch(`/api/requests/${ticketId}/status-risks`, { method: "POST" });
      if (!response.ok || ticketId !== syncedRequestId || box.dataset.user === "1") return;
      const data = await response.json();
      const text = String(data.risks || "").trim();
      if (!text) return;
      box.value = text;
      fitStandField(box);
      await saveStandTexts();
    } catch {
      /* Feld bleibt leer */
    } finally {
      if (box.dataset.loading === ticketId) delete box.dataset.loading;
    }
  }

  async function fillNextFromTicket() {
    const box = standField("stand-live-next");
    const hint = standField("stand-next-hint");
    if (!box || !commentsAllowed() || !syncedRequestId) return;
    if (!String(box.value || "").trim()) {
      const local = nextFromComments();
      if (local) {
        box.value = local;
        fitStandField(box);
      }
    }
    if (box.dataset.user === "1" || String(latestStand()?.nextSteps || "").trim() || String(box.value || "").trim()) {
      if (hint) hint.hidden = true;
      return;
    }
    if (box.dataset.loading === syncedRequestId) return;
    box.dataset.loading = syncedRequestId;
    const ticketId = syncedRequestId;
    try {
      const response = await fetch(`/api/requests/${ticketId}/next-steps`, { method: "POST" });
      if (!response.ok || ticketId !== syncedRequestId || box.dataset.user === "1") return;
      const data = await response.json();
      const text = String(data.nextSteps || "").trim();
      if (!text || String(latestStand()?.nextSteps || "").trim()) return;
      box.value = text;
      fitStandField(box);
      if (hint) hint.hidden = false;
      await saveStandTexts();
    } catch {
      /* Ticket bleibt ohne Vorschlag */
    } finally {
      if (box.dataset.loading === ticketId) delete box.dataset.loading;
    }
  }

  function fillStandForm(people, latest) {
    if (!standPtFields) return;
    const actuals = actualPtMap(latest);
    standPtFields.innerHTML = people
      .map((row) => {
        const current = actuals[row.name.toLowerCase()];
        const shown = current ? String(current).replace(".", ",") : "";
        return `<label>Ist ${esc(row.name)} PT <input type="text" data-stand-pt="${esc(
          row.name
        )}" inputmode="decimal" value="${esc(shown)}" placeholder="Plan ${esc(fmtPt(row.plan))}" /></label>`;
      })
      .join("");
    const start = document.getElementById("stand-actual-start");
    const end = document.getElementById("stand-actual-end");
    const fb = document.getElementById("stand-cost-fb");
    const it = document.getElementById("stand-cost-it");
    const license = document.getElementById("stand-cost-license");
    if (start) start.value = dateIso(latest?.actualStart);
    if (end) end.value = dateIso(latest?.actualEnd);
    if (fb) fb.value = latest?.costActualFb || "";
    if (it) it.value = latest?.costActualIt || "";
    if (license) license.value = latest?.costActualLicense || "";
    const scheduleSel = document.getElementById("stand-schedule-rag");
    const costSel = document.getElementById("stand-cost-rag");
    if (scheduleSel) scheduleSel.value = "";
    if (costSel) costSel.value = "";
  }

  function applyRequest(detail, { animate = true, skipSyncFollow = false } = {}) {
    if (isCreatingChange()) return;
    resetTicketState();
    syncedRequestId = detail.id || null;
    loadedTicket = Boolean(syncedRequestId);
    const fieldMap = {};
    for (const row of detail.fields || []) {
      if (row?.key) fieldMap[row.key] = row.value || "";
    }
    values.title = detail.title || fieldMap.title || "";
    values.description = detail.description || fieldMap.description || "";
    values.priority = detail.priority || "medium";
    // Zuerst UI-Keys, danach Domain-Keys — Domain gewinnt bei Abweichung (Jira-Sync).
    for (const [key, raw] of Object.entries(fieldMap)) {
      if (!raw || DOMAIN_TO_UI[key]) continue;
      values[key] = raw;
      labels[key] = raw;
    }
    for (const [key, raw] of Object.entries(fieldMap)) {
      if (!raw) continue;
      const ui = DOMAIN_TO_UI[key];
      if (!ui) continue;
      values[key] = raw;
      labels[key] = raw;
      values[ui] = raw;
      labels[ui] = raw;
    }
    if (!String(values.author || "").trim()) {
      const created = String(detail.createdBy || "").trim();
      if (created) {
        values.author = created;
        labels.author = created;
      }
    }
    kindLocked = true;
    setKind(detail.kindLabel || "Change Request", detail.kind || "change_request");
    stepIndex = STEPS.length;
    ticket.hidden = false;
    document.body.classList.add("ticket-active");
    const hub = document.getElementById("hub");
    if (hub) hub.hidden = true;
    paintTicketNav();

    for (const step of requiredSteps()) {
      const shown = step.date
        ? isoToDe(values[step.key]) || displayFor(step.key)
        : displayFor(step.key);
      const el = ensureFieldShell(step);
      if (step.kind === "headline") {
        headline.hidden = false;
        headline.textContent = shown;
        headline.classList.add("is-done");
      } else if (el) {
        writeFieldValue(el, step, shown || "");
        el.classList.add("ticket-row-value-in");
      }
      fieldCell(step)?.classList.add("is-done");
      armEdit(step);
    }
    setPriority(detail.priorityLabel || "Mittel", detail.priority || "medium");
    showAuthor();
    const sync = detail.sync || {};
    const jiraKey = sync.externalKey || detail.externalKey || "";
    const jiraUrl = sync.externalUrl || detail.externalUrl || detail.jiraUrl || "";
    if (jiraKey) {
      showJiraBadge(jiraKey, jiraUrl);
      jiraFollowId = null;
    } else if (!skipSyncFollow) {
      followJiraSync(detail);
    } else if (detail.reference) {
      showJiraBadge(detail.reference, "");
    }
    showFinishActions(jiraKey, jiraUrl, { newChange: false });
    showFiles(detail);
    renderComments(detail);
    standUpdates = Array.isArray(detail.statusUpdates) ? detail.statusUpdates : [];
    renderStandBoard();
    hydrateCostFields();
    loadDraft(syncedRequestId);
    restoreTicketScroll(syncedRequestId);
    refreshOverviewChrome();
    syncIntakePanels();
    hideJiraCreate();
    syncTicketModeClass();
    window.syncTicketInput?.();
  }

  const HUB_CACHE_KEY = "critr-hub-cache-v4";

  function standTooltip(item) {
    const parts = [];
    if (item.waitingOnMe && item.waitingTodo) {
      parts.push("Dein nächster Schritt");
    } else if (item.nextStep) {
      parts.push("Nächster Schritt");
    }
    if (item.statusSummary && item.nextStep && item.statusSummary !== item.nextStep) {
      parts.push(`Stand: ${String(item.statusSummary).trim()}`);
    }
    if (item.standSourceLabel) parts.push(`Quelle: ${item.standSourceLabel}`);
    else if (item.standSource === "comments") parts.push("Quelle: Kommentare");
    else if (item.standSource === "status") parts.push("Quelle: Status");
    else if (item.standSource === "combined") parts.push("Quelle: Status und Kommentare");
    const when = item.activityAt || item.updatedAt;
    if (when) {
      try {
        parts.push(`Aktualisiert ${new Date(when).toLocaleString("de-DE")}`);
      } catch (_) {
        /* ignore */
      }
    }
    return parts.join(" · ");
  }

  function hubCueText(item) {
    const next = String(item?.nextStep || item?.waitingTodo || "")
      .replace(/…+$/g, "")
      .replace(/\.{2,}$/g, "")
      .trim();
    if (next) return next;
    return String(item?.statusSummary || "")
      .replace(/…+$/g, "")
      .replace(/\.{2,}$/g, "")
      .trim();
  }

  function hubCueIsAction(item) {
    return Boolean(item?.waitingOnMe && (item.nextStep || item.waitingTodo));
  }

  function actorNeedles() {
    const actor = window.currentActor || {};
    return [
      actor.displayName,
      actor.jiraName,
      window.currentActorName,
    ]
      .map((s) => String(s || "").trim().toLowerCase())
      .filter((s) => s.length >= 2);
  }

  function isMineHubItem(item) {
    const needles = actorNeedles();
    if (!needles.length || !item) return false;
    const hay = [
      item.assignee,
      item.reporter,
      item.authorsText,
      ...(Array.isArray(item.authors) ? item.authors : []),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    if (!hay) return false;
    return needles.some((n) => hay.includes(n));
  }

  function isHubClosedItem(item) {
    if (item?.completed) return true;
    const st = String(item?.status || item?.localStatus || "")
      .toLowerCase()
      .replace(/\s+/g, " ");
    return (
      st.includes("cancel") ||
      st.includes("abbruch") ||
      st.includes("abgebrochen") ||
      st.includes("ablehn") ||
      st.includes("reject") ||
      st === "closed" ||
      st === "done" ||
      st === "erledigt" ||
      st === "geschlossen"
    );
  }

  function filteredHubItems() {
    const q = String(document.getElementById("hub-search")?.value || "")
      .trim()
      .toLowerCase();
    let list = hubItems.filter((item) => !isHubClosedItem(item));
    if (q) {
      list = list.filter((item) => {
        const authors = Array.isArray(item.authors)
          ? item.authors.join(" ")
          : item.authorsText || "";
        const hay = [
          item.title,
          item.key,
          item.status,
          item.statusSummary,
          item.nextStep,
          item.waitingTodo,
          item.assignee,
          item.reporter,
          authors,
          item.reference,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return hay.includes(q);
      });
    }
    // Neueste zuerst nach Erstellungsdatum
    return [...list].sort((a, b) => {
      const ca = String(a.createdAt || "");
      const cb = String(b.createdAt || "");
      if (ca !== cb) return cb.localeCompare(ca);
      return String(b.key || "").localeCompare(String(a.key || ""));
    });
  }

  function normalizeHubStatus(name) {
    const raw = String(name || "").trim();
    if (!raw) return "Konzept";
    const lower = raw.toLowerCase().replace(/\s+/g, " ");
    const exact = HUB_STATUS_COLUMNS.find((col) => col.toLowerCase() === lower);
    if (exact) return exact;
    if (
      lower.includes("quality") ||
      lower.includes("qg") ||
      lower === "q-gate" ||
      lower.includes("qualität")
    ) {
      return "Quality Gate";
    }
    if (lower.includes("control") || lower.includes("controlling")) {
      return "Controlling";
    }
    if (
      lower.includes("ablehn") ||
      lower.includes("reject") ||
      lower.includes("cancel") ||
      lower.includes("zurückgewiesen")
    ) {
      return null;
    }
    if (
      lower.includes("in freigabe") ||
      lower === "freigabe" ||
      lower.includes("approval") ||
      lower.includes("review freigabe")
    ) {
      return "In Freigabe";
    }
    if (
      lower.startsWith("freigegeben") ||
      lower.includes("freigegeben") ||
      lower === "done" ||
      lower === "closed" ||
      lower === "resolved" ||
      lower === "fertig"
    ) {
      return "Freigegeben";
    }
    if (
      lower === "it" ||
      lower.startsWith("it ") ||
      lower.includes("umsetzung") ||
      lower.includes("in progress") ||
      lower.includes("development") ||
      lower.includes("entwicklung") ||
      lower.includes("implementation")
    ) {
      return "IT";
    }
    if (
      lower.includes("konzept") ||
      lower.includes("steckbrief") ||
      lower.includes("backlog") ||
      lower === "open" ||
      lower === "offen" ||
      lower === "to do" ||
      lower === "todo" ||
      lower.includes("neu") ||
      lower.includes("entwurf") ||
      lower.includes("draft")
    ) {
      return "Konzept";
    }
    return "Konzept";
  }

  function hubStatusColumns(items) {
    const buckets = new Map(HUB_STATUS_COLUMNS.map((col) => [col, []]));
    for (const item of items || []) {
      const status = normalizeHubStatus(item.status);
      if (!status || !buckets.has(status)) continue;
      buckets.get(status).push(item);
    }
    return HUB_STATUS_COLUMNS.map((col) => [col, buckets.get(col) || []]);
  }

  function updateHubBoardScrollHint() {
    const hub = document.getElementById("hub");
    const board = document.getElementById("hub-board");
    const fade = document.getElementById("hub-board-fade");
    const hint = document.getElementById("hub-board-hint");
    if (!board || !fade || !hint) return;
    const onBoard = hub?.dataset.view === "board" && !board.hidden;
    if (!onBoard) {
      fade.classList.remove("is-visible");
      hint.classList.remove("is-visible");
      hint.hidden = true;
      return;
    }
    const canScroll = board.scrollWidth > board.clientWidth + 8;
    const atEnd = board.scrollLeft + board.clientWidth >= board.scrollWidth - 12;
    const show = canScroll && !atEnd;
    fade.classList.toggle("is-visible", show);
    hint.classList.toggle("is-visible", show);
    hint.hidden = !show;
  }


  const HUB_CHAT_SESSION_KEY = "critr-hub-chat-session-v1";
  const TICKET_FROM_KEY = "critr-ticket-from-v1";
  let hubChatSessionId = null;
  let hubChatBusy = false;
  let hubChatAbort = null;
  let hubChatReplace = false;
  let hubChatStick = true;
  let ticketOpenedFrom = "";

  function hubChatThread() {
    return document.getElementById("hub-chat-thread");
  }

  function hubChatSuggest() {
    return document.getElementById("hub-chat-suggest");
  }

  function resizeHubChatInput() {
    const input = document.getElementById("hub-chat-input");
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(160, Math.max(44, input.scrollHeight))}px`;
  }

  function setHubChatSuggestVisible(show) {
    const el = hubChatSuggest();
    if (el) el.hidden = !show;
  }

  function paintHubChatProgress() {}

  function paintHubChatActions() {}

  function clearHubChatActions() {}

  function paintHubChatDraft(body) {
    const card = document.getElementById("hub-chat-draft");
    const title = document.getElementById("hub-chat-draft-title");
    const text = document.getElementById("hub-chat-draft-body");
    const button = document.getElementById("hub-chat-draft-create");
    if (!card || !title || !text || !button) return;
    const draft = body?.createDraft || {};
    const titleText = String(draft.title || "").trim();
    const bits = [
      ["Problem", draft.problem],
      ["Lösung", draft.solution_goals],
      ["Nutzen", draft.benefit_savings],
      ["Start", draft.start_date],
      ["Ende", draft.end_date],
    ].filter(([, value]) => {
      const line = String(value || "").trim();
      return line && line !== titleText;
    });
    const show = Boolean(body?.createAssist) && (titleText || bits.length || body?.createReady);
    card.hidden = !show;
    title.textContent = titleText;
    title.hidden = !titleText;
    text.textContent = bits.map(([label, value]) => `${label}: ${value}`).join("\n");
    text.hidden = !text.textContent;
    button.hidden = !body?.createReady;
    refreshHubChatTurns();
  }

  function applyHubChatPayload(body) {
    const reply = String(body.text || body.duplicatePrompt || "").trim() || "Fertig.";
    const links = [
      ...(Array.isArray(body.links) ? body.links : []),
      ...(Array.isArray(body.duplicateLinks) ? body.duplicateLinks : []),
    ];
    if ((body.type === "navigate" || body.type === "created") && body.url) {
      links.push({
        label: body.reference || body.ticketKey || body.label || "Öffnen",
        url: body.url,
      });
    }
    appendHubChatBubble("assistant", reply, links);
    paintHubChatDraft(body);
    if (body.createAssist === false && !hubChatThread()?.querySelector(".hub-chat-bubble")) {
      setHubChatSuggestVisible(true);
    }
    if (body.hubView === "inbox") {
      openAccountInbox();
    }
    const openId =
      body.requestId ||
      ((body.type === "navigate" || body.type === "created") &&
      body.url &&
      /\/workspace\//.test(body.url)
        ? body.url.split("/workspace/")[1]?.split(/[?#]/)[0]
        : "");
    if (openId) {
      const gaps = Array.isArray(body.gaps) ? body.gaps : [];
      window.setTimeout(() => {
        void openExisting(openId, { animate: true });
        if (gaps.length) {
          const shown = gaps.slice(0, 4).join(", ");
          const more = gaps.length > 4 ? ` (+${gaps.length - 4})` : "";
          setIntro(`Steckbrief ergänzen: ${shown}${more}`);
          intro?.classList.add("field-prompt-in");
          document.querySelectorAll(".ticket-row.is-gap").forEach((el) => el.classList.remove("is-gap"));
          gaps.forEach((label) => {
            const row = [...document.querySelectorAll(".ticket-row")].find((el) =>
              (el.querySelector(".ticket-row-label")?.textContent || "").includes(String(label))
            );
            row?.classList.add("is-gap");
          });
        }
      }, 450);
    }
  }

  function renderHubMarkdown(raw) {
    const esc = String(raw || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    const inline = esc
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(
        /\[([^\]]+)\]\((https?:\/\/[^)\s]+|\/[^)\s]*)\)/g,
        '<a href="$2" target="_blank" rel="noopener">$1</a>'
      );
    const blocks = inline.split(/\n{2,}/);
    return blocks
      .map((block) => {
        const lines = block.split("\n");
        const bullet = lines.every((line) => /^[-*]\s+/.test(line.trim()));
        const numbered = lines.every((line) => /^\d+\.\s+/.test(line.trim()));
        if (bullet && lines.some((line) => line.trim())) {
          const items = lines.map((line) => `<li>${line.trim().replace(/^[-*]\s+/, "")}</li>`).join("");
          return `<ul>${items}</ul>`;
        }
        if (numbered && lines.some((line) => line.trim())) {
          const items = lines
            .map((line) => `<li>${line.trim().replace(/^\d+\.\s+/, "")}</li>`)
            .join("");
          return `<ol>${items}</ol>`;
        }
        return `<p>${lines.join("<br>")}</p>`;
      })
      .join("");
  }

  function hubChatNearBottom(thread) {
    if (!thread) return true;
    return thread.scrollHeight - thread.scrollTop - thread.clientHeight < 80;
  }

  function stickHubChat(thread) {
    if (hubChatStick && thread) thread.scrollTop = thread.scrollHeight;
    const jump = document.getElementById("hub-chat-jump");
    if (jump) jump.hidden = hubChatStick || !thread?.querySelector(".hub-chat-bubble");
  }

  function syncHubChatSend() {
    const send = document.getElementById("hub-chat-send");
    const input = document.getElementById("hub-chat-input");
    const hint = document.getElementById("hub-chat-edit-hint");
    if (!send) return;
    send.classList.toggle("is-stop", hubChatBusy);
    send.disabled = hubChatBusy ? false : !String(input?.value || "").trim();
    send.setAttribute("aria-label", hubChatBusy ? "Stoppen" : "Senden");
    if (hint) hint.hidden = !hubChatReplace;
  }

  function syncHubChatFrame() {
    const panel = document.getElementById("hub-chat-panel");
    const thread = hubChatThread();
    const empty = !thread?.querySelector(".hub-chat-bubble");
    panel?.classList.toggle("is-empty", empty);
    if (empty) hubChatReplace = false;
    syncHubChatSend();
    stickHubChat(thread);
  }

  function refreshHubChatTurns() {
    const thread = hubChatThread();
    if (!thread) return;
    const creating = !document.getElementById("hub-chat-draft")?.hidden;
    thread.querySelectorAll(".hub-chat-turn-tools").forEach((el) => el.remove());
    const assistants = [...thread.querySelectorAll(".hub-chat-bubble.is-assistant")];
    const users = [...thread.querySelectorAll(".hub-chat-bubble.is-user")];
    const lastAssistant = assistants.at(-1);
    const lastUser = users.at(-1);
    for (const row of assistants) {
      const tools = document.createElement("div");
      tools.className = "hub-chat-turn-tools";
      const copy = document.createElement("button");
      copy.type = "button";
      copy.textContent = "Kopieren";
      copy.addEventListener("click", async () => {
        const raw = row.dataset.raw || "";
        try {
          await navigator.clipboard.writeText(raw);
          copy.textContent = "Kopiert";
          window.setTimeout(() => {
            copy.textContent = "Kopieren";
          }, 1200);
        } catch (_) {
          copy.textContent = "Nicht kopiert";
        }
      });
      tools.appendChild(copy);
      if (row === lastAssistant && !creating) {
        const again = document.createElement("button");
        again.type = "button";
        again.textContent = "Neu erzeugen";
        again.addEventListener("click", () => {
          const prompt = lastUser?.dataset.raw || "";
          if (!prompt || hubChatBusy) return;
          row.remove();
          void sendHubChat(prompt, { turn: "regenerate", keepUser: true });
        });
        tools.appendChild(again);
      }
      row.appendChild(tools);
    }
    if (lastUser && !creating) {
      const tools = document.createElement("div");
      tools.className = "hub-chat-turn-tools";
      const edit = document.createElement("button");
      edit.type = "button";
      edit.textContent = "Ändern";
      edit.addEventListener("click", () => {
        const input = document.getElementById("hub-chat-input");
        if (!input || hubChatBusy) return;
        input.value = lastUser.dataset.raw || "";
        hubChatReplace = true;
        resizeHubChatInput();
        syncHubChatSend();
        input.focus();
      });
      tools.appendChild(edit);
      lastUser.appendChild(tools);
    }
  }

  function hubChatLinks(row, links) {
    if (!row || !Array.isArray(links) || !links.length) return;
    const list = document.createElement("div");
    list.className = "hub-chat-links";
    for (const link of links) {
      const url = String(link?.url || "").trim();
      const label = String(link?.label || url).trim();
      if (!url) continue;
      const a = document.createElement("button");
      a.type = "button";
      a.className = "hub-chat-link";
      a.textContent = label;
      a.addEventListener("click", () => {
        if (url.includes("/workspace/")) {
          const id = url.split("/workspace/")[1]?.split(/[?#]/)[0];
          if (id) {
            openTicketFromChat(id);
            return;
          }
        }
        if (url.startsWith("/")) location.assign(url);
        else window.open(url, "_blank", "noopener");
      });
      list.appendChild(a);
    }
    const tools = row.querySelector(".hub-chat-turn-tools");
    if (list.childNodes.length) {
      if (tools) row.insertBefore(list, tools);
      else row.appendChild(list);
    }
  }

  function appendHubChatBubble(role, text, links, { stream = false } = {}) {
    const thread = hubChatThread();
    if (!thread || text == null || text === "") return null;
    const row = document.createElement("div");
    row.className = `hub-chat-bubble is-${role}`;
    row.dataset.raw = String(text);
    const body = document.createElement(role === "assistant" ? "div" : "p");
    if (role === "assistant") {
      body.className = "hub-chat-md";
      body.innerHTML = renderHubMarkdown(text);
    } else {
      body.textContent = text;
    }
    row.appendChild(body);
    thread.appendChild(row);
    if (role === "assistant") hubChatLinks(row, links);
    refreshHubChatTurns();
    syncHubChatFrame();
    stickHubChat(thread);
    return { row, body };
  }

  function startHubChatStreamBubble() {
    const thread = hubChatThread();
    if (!thread) return null;
    const row = document.createElement("div");
    row.className = "hub-chat-bubble is-assistant";
    row.dataset.raw = "";
    const body = document.createElement("div");
    body.className = "hub-chat-md";
    row.appendChild(body);
    thread.appendChild(row);
    syncHubChatFrame();
    stickHubChat(thread);
    return { row, body };
  }

  function paintHubChatStream(bubble) {
    if (!bubble?.body) return;
    bubble.body.innerHTML = renderHubMarkdown(bubble.row?.dataset.raw || "");
  }

  function appendHubChatThinking() {
    const thread = hubChatThread();
    if (!thread) return null;
    const row = document.createElement("div");
    row.className = "hub-chat-bubble is-thinking";
    row.setAttribute("aria-label", "schreibt");
    const dots = document.createElement("span");
    dots.className = "hub-chat-dots";
    dots.setAttribute("aria-hidden", "true");
    dots.innerHTML = "<span></span><span></span><span></span>";
    row.appendChild(dots);
    thread.appendChild(row);
    stickHubChat(thread);
    return row;
  }

  function closeHubChatHistoryMenu() {
    const menu = document.getElementById("hub-chat-history-menu");
    const btn = document.getElementById("hub-chat-history");
    if (menu) menu.hidden = true;
    btn?.setAttribute("aria-expanded", "false");
  }

  async function paintHubChatHistoryMenu() {
    const menu = document.getElementById("hub-chat-history-menu");
    if (!menu) return;
    menu.replaceChildren();
    const empty = document.createElement("p");
    empty.className = "hub-chat-history-empty";
    empty.textContent = "Lade…";
    menu.appendChild(empty);
    try {
      const r = await fetch("/api/sessions/hub-chats?limit=8");
      const body = await r.json().catch(() => ({}));
      menu.replaceChildren();
      const items = Array.isArray(body.items) ? body.items : [];
      if (!items.length) {
        const msg = document.createElement("p");
        msg.className = "hub-chat-history-empty";
        msg.textContent = "Noch keine Chats.";
        menu.appendChild(msg);
        return;
      }
      for (const item of items) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "hub-chat-history-item";
        btn.setAttribute("role", "menuitem");
        if (item.sessionId === hubChatSessionId) btn.classList.add("is-current");
        const title = document.createElement("span");
        title.className = "hub-chat-history-item-title";
        title.textContent = item.preview || "Chat";
        const meta = document.createElement("span");
        meta.className = "hub-chat-history-item-meta";
        meta.textContent = `${item.messages || "?"} Nachrichten`;
        btn.append(title, meta);
        btn.addEventListener("click", () => {
          closeHubChatHistoryMenu();
          void resumeHubChat(item.sessionId);
        });
        menu.appendChild(btn);
      }
    } catch (_) {
      menu.replaceChildren();
      const msg = document.createElement("p");
      msg.className = "hub-chat-history-empty";
      msg.textContent = "Verlauf nicht ladbar.";
      menu.appendChild(msg);
    }
  }

  async function resumeHubChat(sessionId) {
    const id = String(sessionId || "").trim();
    if (!id) return;
    hubChatSessionId = id;
    try {
      localStorage.setItem(HUB_CHAT_SESSION_KEY, id);
    } catch (_) {
      /* ignore */
    }
    const thread = hubChatThread();
    if (thread) {
      thread.replaceChildren();
      thread.dataset.ready = "1";
    }
    clearHubChatActions();
    paintHubChatProgress([]);
    setHubChatSuggestVisible(false);
    try {
      const r = await fetch(`/api/sessions/${id}/history`);
      const body = await r.json().catch(() => ({}));
      if (r.status === 404) {
        clearStaleHubChatSession();
        resetHubChat();
        return;
      }
      if (!r.ok) throw new Error(body.detail || "Verlauf fehlt");
      const messages = Array.isArray(body.messages) ? body.messages : [];
      if (!messages.length) {
        ensureHubChatWelcome();
        return;
      }
      for (const msg of messages) {
        const role = msg.role === "user" ? "user" : "assistant";
        appendHubChatBubble(role, msg.text || "");
      }
      setHubChatSuggestVisible(false);
      refreshHubChatTurns();
      syncHubChatFrame();
    } catch (err) {
      appendHubChatBubble("assistant", String(err.message || err));
      setHubChatSuggestVisible(true);
    }
    document.getElementById("hub-chat-input")?.focus();
  }

  async function ensureHubChatWelcome() {
    const thread = hubChatThread();
    if (!thread || thread.dataset.ready === "1") return;
    thread.dataset.ready = "1";
    let restored = false;
    try {
      const saved = localStorage.getItem(HUB_CHAT_SESSION_KEY);
      if (saved) {
        const r = await fetch(`/api/sessions/${saved}/history`);
        if (r.ok) {
          const body = await r.json().catch(() => ({}));
          const messages = Array.isArray(body.messages) ? body.messages : [];
          if (messages.length) {
            hubChatSessionId = saved;
            for (const msg of messages) {
              const role = msg.role === "user" ? "user" : "assistant";
              appendHubChatBubble(role, msg.text || "");
            }
            restored = true;
            setHubChatSuggestVisible(false);
            clearHubChatActions();
            paintHubChatProgress([]);
          }
        } else if (r.status === 404) {
          clearStaleHubChatSession();
        }
      }
    } catch (_) {
      /* welcome fallback */
    }
    if (restored) {
      refreshHubChatTurns();
      syncHubChatFrame();
      return;
    }
    setHubChatSuggestVisible(true);
    paintHubChatDraft({});
    syncHubChatFrame();
  }

  function resetHubChat() {
    hubChatAbort?.abort();
    hubChatSessionId = null;
    hubChatBusy = false;
    hubChatReplace = false;
    closeHubChatHistoryMenu();
    try {
      localStorage.removeItem(HUB_CHAT_SESSION_KEY);
    } catch (_) {
      /* ignore */
    }
    const thread = hubChatThread();
    if (thread) {
      thread.replaceChildren();
      delete thread.dataset.ready;
    }
    setHubChatSuggestVisible(true);
    paintHubChatDraft({});
    const t = hubChatThread();
    if (t) t.dataset.ready = "1";
    syncHubChatFrame();
    document.getElementById("hub-chat-input")?.focus();
  }

  function clearStaleHubChatSession() {
    hubChatSessionId = null;
    try {
      localStorage.removeItem(HUB_CHAT_SESSION_KEY);
    } catch (_) {
      /* ignore */
    }
  }

  async function createHubChatSession() {
    const r = await fetch("/api/sessions", { method: "POST" });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail || "Chat-Session fehlgeschlagen");
    hubChatSessionId = String(body.sessionId || "");
    if (!hubChatSessionId) throw new Error("Keine Session-ID");
    try {
      localStorage.setItem(HUB_CHAT_SESSION_KEY, hubChatSessionId);
    } catch (_) {
      /* ignore */
    }
    return hubChatSessionId;
  }

  async function ensureHubChatSession({ forceNew = false } = {}) {
    if (forceNew) clearStaleHubChatSession();
    if (hubChatSessionId) return hubChatSessionId;
    try {
      hubChatSessionId = localStorage.getItem(HUB_CHAT_SESSION_KEY) || null;
    } catch (_) {
      hubChatSessionId = null;
    }
    if (hubChatSessionId) {
      // Nach Redeploy/DB-Wechsel kann die ID ungültig sein — kurz prüfen.
      try {
        const check = await fetch(`/api/sessions/${hubChatSessionId}/history`);
        if (check.ok) return hubChatSessionId;
      } catch (_) {
        /* neu anlegen */
      }
      clearStaleHubChatSession();
    }
    return createHubChatSession();
  }

  async function openHubChatStream(sessionId, raw, turn, signal) {
    const client = { mode: "hub" };
    if (turn) client.turn = turn;
    return fetch(`/api/sessions/${sessionId}/message/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ text: raw, client }),
      signal,
    });
  }

  function payloadLinks(body) {
    const links = [
      ...(Array.isArray(body?.links) ? body.links : []),
      ...(Array.isArray(body?.duplicateLinks) ? body.duplicateLinks : []),
    ];
    if ((body?.type === "navigate" || body?.type === "created") && body?.url) {
      links.push({
        label: body.reference || body.ticketKey || body.label || "Öffnen",
        url: body.url,
      });
    }
    return links;
  }

  function openHubChatTarget(body) {
    if (body?.hubView === "inbox") openAccountInbox();
    const openId =
      body?.requestId ||
      ((body?.type === "navigate" || body?.type === "created") &&
      body?.url &&
      /\/workspace\//.test(body.url)
        ? body.url.split("/workspace/")[1]?.split(/[?#]/)[0]
        : "");
    if (openId) window.setTimeout(() => openTicketFromChat(openId), 450);
  }

  async function sendHubChat(text, opts = {}) {
    const raw = String(text || "").trim();
    if (!raw || hubChatBusy) return;
    const replace = hubChatReplace && !opts.keepUser;
    if (replace) {
      const thread = hubChatThread();
      const users = thread ? [...thread.querySelectorAll(".hub-chat-bubble.is-user")] : [];
      const lastUser = users.at(-1);
      let node = lastUser;
      while (node) {
        const next = node.nextElementSibling;
        node.remove();
        node = next;
      }
      hubChatReplace = false;
    }
    hubChatBusy = true;
    hubChatStick = true;
    hubChatAbort = new AbortController();
    const input = document.getElementById("hub-chat-input");
    if (input && !opts.keepUser) {
      input.value = "";
      resizeHubChatInput();
    }
    syncHubChatSend();
    setHubChatSuggestVisible(false);
    if (!opts.keepUser) appendHubChatBubble("user", raw);
    const thinking = appendHubChatThinking();
    let streamBubble = null;
    try {
      const turn = opts.turn || (replace ? "edit" : "");
      let sessionId = await ensureHubChatSession();
      let r = await openHubChatStream(sessionId, raw, turn, hubChatAbort.signal);
      if (r.status === 404) {
        clearStaleHubChatSession();
        sessionId = await ensureHubChatSession({ forceNew: true });
        r = await openHubChatStream(sessionId, raw, turn, hubChatAbort.signal);
      }
      if (!r.ok) {
        thinking?.remove();
        if (r.status === 404) clearStaleHubChatSession();
        const errBody = await r.json().catch(() => ({}));
        const detail = errBody.detail || `Fehler ${r.status}`;
        const msg =
          typeof detail === "string" && /session unbekannt/i.test(detail)
            ? "Chat neu gestartet — bitte noch einmal senden."
            : typeof detail === "string"
              ? detail
              : "Anfrage fehlgeschlagen.";
        appendHubChatBubble("assistant", msg);
        return;
      }
      const reader = r.body?.getReader();
      if (!reader) throw new Error("Kein Stream");
      const decoder = new TextDecoder();
      let buffer = "";
      let sawToken = false;
      let donePayload = null;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n");
        buffer = parts.pop() || "";
        for (const line of parts) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data:")) continue;
          let event;
          try {
            event = JSON.parse(trimmed.slice(5).trim());
          } catch (_) {
            continue;
          }
          if (event.event === "token") {
            if (!sawToken) {
              thinking?.remove();
              streamBubble = startHubChatStreamBubble();
              sawToken = true;
            }
            if (streamBubble?.row) {
              streamBubble.row.dataset.raw += String(event.text || "");
              paintHubChatStream(streamBubble);
              stickHubChat(hubChatThread());
            }
          } else if (event.event === "done") {
            donePayload = event.payload || {};
          }
        }
      }
      thinking?.remove();
      if (sawToken && donePayload) {
        if (streamBubble?.row) {
          const finalText = String(donePayload.text || streamBubble.row.dataset.raw || "").trim();
          streamBubble.row.dataset.raw = finalText;
          paintHubChatStream(streamBubble);
          hubChatLinks(streamBubble.row, payloadLinks(donePayload));
          refreshHubChatTurns();
        }
        paintHubChatDraft(donePayload);
        openHubChatTarget(donePayload);
      } else if (donePayload) {
        streamBubble?.row?.remove();
        applyHubChatPayload(donePayload);
      } else if (!streamBubble?.row?.dataset.raw) {
        appendHubChatBubble("assistant", "Keine Antwort.");
      } else {
        refreshHubChatTurns();
      }
    } catch (err) {
      thinking?.remove();
      if (err?.name === "AbortError") {
        if (streamBubble?.row?.dataset.raw) {
          paintHubChatStream(streamBubble);
          refreshHubChatTurns();
        } else {
          streamBubble?.row?.remove();
        }
        return;
      }
      appendHubChatBubble("assistant", String(err.message || err));
    } finally {
      hubChatBusy = false;
      hubChatAbort = null;
      syncHubChatFrame();
      if (!opts.keepUser) input?.focus();
    }
  }

  function waitingHubItems() {
    return hubItems.filter((item) => item?.waitingOnMe);
  }

  function paintAccountInbox() {
    const badge = document.getElementById("account-inbox-badge");
    const empty = document.getElementById("account-inbox-empty");
    const list = document.getElementById("account-inbox-list");
    const inboxBtn = document.getElementById("account-inbox");
    if (!list) return;
    const waiting = waitingHubItems();
    if (badge) badge.hidden = waiting.length === 0;
    if (inboxBtn) {
      inboxBtn.hidden = waiting.length === 0;
      inboxBtn.setAttribute(
        "aria-label",
        waiting.length ? `Inbox, ${waiting.length} offen` : "Inbox"
      );
      if (waiting.length === 0) {
        const acc = document.getElementById("account");
        const inboxMenu = document.getElementById("account-inbox-menu");
        acc?.classList.remove("is-inbox-open");
        if (inboxMenu) inboxMenu.hidden = true;
        inboxBtn.setAttribute("aria-expanded", "false");
      }
    }
    list.replaceChildren();
    if (empty) empty.hidden = waiting.length > 0;
    for (const item of waiting.slice(0, 12)) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "account-inbox-item";
      btn.setAttribute("role", "menuitem");
      const title = document.createElement("span");
      title.className = "account-inbox-item-title";
      title.textContent = item.title || item.key || item.reference || "Change";
      const meta = document.createElement("span");
      meta.className = "account-inbox-item-meta";
      meta.textContent =
        item.waitingTodo || item.nextStep || item.statusSummary || item.key || "";
      btn.append(title);
      if (meta.textContent) btn.append(meta);
      btn.addEventListener("click", () => {
        const acc = document.getElementById("account");
        acc?.classList.remove("is-inbox-open");
        const menu = document.getElementById("account-inbox-menu");
        if (menu) menu.hidden = true;
        inboxBtn?.setAttribute("aria-expanded", "false");
        void openHubItem(item);
      });
      list.appendChild(btn);
    }
  }

  function openAccountInbox() {
    paintAccountInbox();
    const acc = document.getElementById("account");
    const menu = document.getElementById("account-menu");
    const inboxMenu = document.getElementById("account-inbox-menu");
    const nameBtn = acc?.querySelector(".account-name");
    const inboxBtn = document.getElementById("account-inbox");
    if (!acc || !inboxMenu) return;
    acc.classList.remove("is-open");
    if (menu) menu.hidden = true;
    nameBtn?.setAttribute("aria-expanded", "false");
    acc.classList.add("is-inbox-open");
    inboxMenu.hidden = false;
    inboxBtn?.setAttribute("aria-expanded", "true");
  }

  window.refreshAccountInbox = paintAccountInbox;
  window.openAccountInbox = openAccountInbox;

  function applyHubView(view, { persist = true } = {}) {
    const hub = document.getElementById("hub");
    const board = document.getElementById("hub-board");
    const chat = document.getElementById("hub-chat");
    const listBtn = document.getElementById("hub-view-list");
    const boardBtn = document.getElementById("hub-view-board");
    const chatBtn = document.getElementById("hub-view-chat");
    const reportBtn = document.getElementById("hub-view-report");
    const report = document.getElementById("hub-report");
    const allowed = view === "board" || view === "chat" || view === "report";
    hubView = allowed ? view : "list";
    if (hub) hub.dataset.view = hubView;
    document.body.classList.toggle("hub-chat-view", hubView === "chat");
    if (startChangeBtn && !document.body.classList.contains("ticket-active")) {
      startChangeBtn.hidden = false;
    }
    if (board) board.hidden = hubView !== "board";
    if (chat) chat.hidden = hubView !== "chat";
    if (report) report.hidden = hubView !== "report";
    listBtn?.classList.toggle("is-active", hubView === "list");
    boardBtn?.classList.toggle("is-active", hubView === "board");
    chatBtn?.classList.toggle("is-active", hubView === "chat");
    reportBtn?.classList.toggle("is-active", hubView === "report");
    if (persist) {
      try {
        localStorage.setItem(HUB_VIEW_KEY, hubView);
      } catch (_) {
        /* ignore */
      }
    }
    if (hubView === "chat") {
      ensureHubChatWelcome();
      window.requestAnimationFrame(() => document.getElementById("hub-chat-input")?.focus());
    } else if (hubView === "report") {
      void loadEffortReport();
    } else {
      paintHubItems(hubItems, { keepFocus: true });
      window.requestAnimationFrame(updateHubBoardScrollHint);
    }
    watchEffortReport();
  }

  let effortReport = null;
  let effortReportTimer = 0;
  let reportOwner = "";
  const reportSort = {
    owners: { key: "totalPt", dir: "desc" },
    changes: { key: "totalPt", dir: "desc" },
  };

  function formatPt(value, blankZero) {
    const n = Number(value);
    if (!Number.isFinite(n)) return blankZero ? "—" : "0,0";
    if (blankZero && Math.abs(n) < 0.05) return "—";
    const sign = n < 0 ? "-" : "";
    const abs = Math.abs(n);
    const [whole, frac] = abs.toFixed(1).split(".");
    const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return `${sign}${grouped},${frac}`;
  }

  function toggleReportSort(which, key) {
    const sort = reportSort[which];
    if (!sort || !key) return;
    if (sort.key === key) sort.dir = sort.dir === "desc" ? "asc" : "desc";
    else {
      sort.key = key;
      sort.dir = key === "name" || key === "title" || key === "owner" || key === "statusLabel" ? "asc" : "desc";
    }
    paintEffortReport();
  }

  function sortReportRows(rows, key, dir) {
    const sign = dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = a[key];
      const bv = b[key];
      const an = Number(av);
      const bn = Number(bv);
      const aNum = av !== "" && Number.isFinite(an);
      const bNum = bv !== "" && Number.isFinite(bn);
      if (aNum && bNum) return (an - bn) * sign;
      return String(av || "").localeCompare(String(bv || ""), "de") * sign;
    });
  }

  function markReportSort(tableId, sort) {
    document.querySelectorAll(`#${tableId} th[data-sort]`).forEach((th) => {
      const on = th.dataset.sort === sort.key;
      th.dataset.active = on ? sort.dir : "";
      th.setAttribute("aria-sort", on ? (sort.dir === "asc" ? "ascending" : "descending") : "none");
    });
  }

  function reportQuery() {
    return String(document.getElementById("hub-search")?.value || "")
      .trim()
      .toLowerCase();
  }

  function watchEffortReport() {
    window.clearInterval(effortReportTimer);
    if (hubView !== "report") return;
    effortReportTimer = window.setInterval(() => {
      if (document.hidden || hubView !== "report") return;
      void loadEffortReport({ silent: true });
    }, 20000);
  }

  async function loadEffortReport({ silent = false } = {}) {
    const state = document.getElementById("hub-report-state");
    if (!silent && state) {
      state.hidden = false;
      state.textContent = "Lade Auswertung…";
    }
    try {
      const response = await fetch("/api/requests/evaluation");
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof body.detail === "string" ? body.detail : "Auswertung nicht geladen");
      }
      effortReport = body;
      paintEffortReport();
      if (state) state.hidden = true;
    } catch (err) {
      if (state) {
        state.hidden = false;
        state.textContent = err?.message || "Auswertung nicht geladen";
      }
    }
  }

  function paintEffortReport() {
    const data = effortReport || { totals: {}, owners: [], changes: [] };
    const q = reportQuery();
    const allChanges = data.changes || [];
    const changes = q
      ? allChanges.filter((row) =>
          [row.title, row.owner, row.statusLabel].join(" ").toLowerCase().includes(q)
        )
      : allChanges;
    const matchedOwners = new Set(changes.map((row) => row.owner));
    const owners = sortReportRows(
      q
        ? (data.owners || []).filter(
            (row) => matchedOwners.has(row.name) || String(row.name || "").toLowerCase().includes(q)
          )
        : data.owners || [],
      reportSort.owners.key,
      reportSort.owners.dir
    );
    let visibleChanges = changes;
    if (reportOwner) {
      visibleChanges = visibleChanges.filter((row) => row.owner === reportOwner);
    }
    visibleChanges = sortReportRows(
      visibleChanges,
      reportSort.changes.key,
      reportSort.changes.dir
    );
    const totals = q ? totalsFromOwners(owners) : data.totals || {};
    const kpis = document.getElementById("hub-report-kpis");
    if (kpis) {
      const cards = [
        ["Gesamt-PT IT", formatPt(totals.itPt)],
        ["Betreute Projekte mit IT-PT", String(totals.projects || 0)],
        ["Ø PT pro Verantwortlichem", formatPt(totals.avgPerOwner)],
      ];
      kpis.replaceChildren();
      for (const [label, value] of cards) {
        const card = document.createElement("div");
        card.className = "hub-report-kpi";
        const name = document.createElement("span");
        name.textContent = label;
        const strong = document.createElement("strong");
        strong.textContent = value;
        card.append(name, strong);
        kpis.appendChild(card);
      }
    }
    const ownerBody = document.querySelector("#hub-report-owners tbody");
    markReportSort("hub-report-owners", reportSort.owners);
    if (ownerBody) {
      ownerBody.replaceChildren();
      const sum = {
        projects: 0,
        conceptPt: 0,
        totalPt: 0,
        approvedPt: 0,
        openPt: 0,
        holdPt: 0,
        donePt: 0,
        rejectedPt: 0,
      };
      for (const row of owners) {
        sum.projects += Number(row.projects) || 0;
        for (const key of Object.keys(sum)) {
          if (key === "projects") continue;
          sum[key] += Number(row[key]) || 0;
        }
        ownerBody.appendChild(reportOwnerRow(row));
      }
      const total = document.createElement("tr");
      total.className = "is-sum";
      total.append(
        reportCell("Gesamt"),
        reportCell(String(sum.projects)),
        reportCell(formatPt(sum.conceptPt, true)),
        reportTotalCell(sum.totalPt),
        reportCell(formatPt(sum.approvedPt, true)),
        reportCell(formatPt(sum.openPt, true)),
        reportCell(formatPt(sum.holdPt, true)),
        reportCell(formatPt(sum.donePt, true)),
        reportCell(formatPt(sum.rejectedPt, true))
      );
      ownerBody.appendChild(total);
    }
    const title = document.getElementById("hub-report-changes-title");
    const clear = document.getElementById("hub-report-clear");
    if (title) title.textContent = reportOwner ? reportOwner : "Changes";
    if (clear) clear.hidden = !reportOwner;
    const changeBody = document.querySelector("#hub-report-changes tbody");
    markReportSort("hub-report-changes", reportSort.changes);
    if (changeBody) {
      changeBody.replaceChildren();
      for (const row of visibleChanges) {
        const tr = document.createElement("tr");
        if (row.id) tr.dataset.id = row.id;
        tr.append(
          reportCell(row.title || "Change"),
          reportCell(row.statusLabel || ""),
          reportCell(row.owner || ""),
          reportCell(formatPt(row.conceptPt, true)),
          reportCell(formatPt(row.operatePt, true)),
          reportCell(formatPt(row.totalPt), "is-total")
        );
        if (row.id) {
          tr.addEventListener("click", () => {
            void openHubItem({ requestId: row.id });
          });
        }
        changeBody.appendChild(tr);
      }
    }
  }

  function reportCell(text, className) {
    const td = document.createElement("td");
    const quiet = text === "—";
    td.className = [className, quiet ? "is-quiet" : ""].filter(Boolean).join(" ");
    td.textContent = text;
    return td;
  }

  function reportTotalCell(value) {
    const td = document.createElement("td");
    td.className = "is-total";
    td.textContent = formatPt(value);
    return td;
  }

  function totalsFromOwners(owners) {
    const itPt = owners.reduce((sum, row) => sum + (Number(row.totalPt) || 0), 0);
    const projects = owners.reduce((sum, row) => sum + (Number(row.projects) || 0), 0);
    const named = owners.filter((row) => row.name && row.name !== "Ohne Zuordnung");
    const divisor = named.length || owners.length;
    return {
      itPt,
      projects,
      avgPerOwner: divisor ? itPt / divisor : 0,
    };
  }

  function reportOwnerRow(row) {
    const tr = document.createElement("tr");
    tr.dataset.owner = row.name || "";
    if (reportOwner && reportOwner === row.name) tr.classList.add("is-picked");
    const name = document.createElement("td");
    name.className = "is-name";
    name.textContent = row.name || "";
    tr.append(
      name,
      reportCell(String(row.projects || 0)),
      reportCell(formatPt(row.conceptPt, true)),
      reportTotalCell(row.totalPt),
      reportCell(formatPt(row.approvedPt, true)),
      reportCell(formatPt(row.openPt, true)),
      reportCell(formatPt(row.holdPt, true)),
      reportCell(formatPt(row.donePt, true)),
      reportCell(formatPt(row.rejectedPt, true))
    );
    return tr;
  }

  function paintHubChange(item, { meta } = {}) {
    const wrap = document.createElement("div");
    wrap.className = "row-change";
    const dot = document.createElement("span");
    dot.className = "row-dot";
    const healthKey = String(item?.standHealth?.key || "").toLowerCase();
    if (
      healthKey === "green" ||
      healthKey === "blue" ||
      healthKey === "yellow" ||
      healthKey === "red" ||
      healthKey === "white" ||
      healthKey === "done"
    ) {
      dot.dataset.health = healthKey;
    } else if (item.completed || item.localStatus === "abgeschlossen") {
      dot.dataset.health = "done";
    } else {
      dot.dataset.health = "green";
    }
    dot.setAttribute("aria-hidden", "true");
    if (item.standHealth?.label) dot.title = item.standHealth.label;

    const stack = document.createElement("div");
    stack.className = "row-stack";
    const metaBits = meta === "key" ? [] : [item.status].filter(Boolean);
    if (metaBits.length) {
      const meta = document.createElement("span");
      meta.className = "row-meta";
      meta.textContent = metaBits.join(" · ");
      stack.appendChild(meta);
    }
    const name = document.createElement("span");
    name.className = "row-title";
    name.textContent = item.title || item.key || "Change";
    stack.appendChild(name);
    const cueText = hubCueText(item) || item.statusSummary || "";
    if (cueText) {
      const cue = document.createElement("span");
      cue.className = `row-cue${hubCueIsAction(item) ? " is-next" : ""}`;
      cue.textContent = cueText;
      const tip = standTooltip(item);
      if (tip) cue.title = tip;
      stack.appendChild(cue);
    }
    wrap.append(dot, stack);
    return wrap;
  }

  function paintHubBoard(visible) {
    const board = document.getElementById("hub-board");
    if (!board) return;
    board.replaceChildren();
    const cols = hubStatusColumns(visible);
    if (!cols.length) {
      const empty = document.createElement("p");
      empty.className = "hub-col-empty";
      empty.textContent =
            hubItems.length
              ? "Keine Treffer."
              : "Keine Tickets in Jira.";
      board.appendChild(empty);
      return;
    }
    let flatIndex = 0;
    for (const [status, cards] of cols) {
      const col = document.createElement("section");
      col.className = "hub-col";
      col.dataset.status = status;
      const head = document.createElement("header");
      head.className = "hub-col-head";
      const title = document.createElement("h3");
      title.className = "hub-col-title";
      title.textContent = status;
      const meta = document.createElement("div");
      meta.className = "hub-col-head-meta";
      const count = document.createElement("span");
      count.className = "hub-col-count";
      count.textContent = String(cards.length);
      meta.appendChild(count);
      const mineN = cards.filter((item) => isMineHubItem(item)).length;
      if (mineN) {
        const mine = document.createElement("span");
        mine.className = "hub-col-mine";
        mine.textContent = `${mineN} von dir`;
        meta.appendChild(mine);
      }
      head.append(title, meta);
      const list = document.createElement("div");
      list.className = "hub-col-cards";
      if (!cards.length) {
        const empty = document.createElement("p");
        empty.className = "hub-col-empty";
        empty.textContent = "Nichts hier";
        list.appendChild(empty);
      }
      for (const item of cards) {
        const card = document.createElement("article");
        card.className = "hub-card";
        card.dataset.key = item.key || "";
        card.dataset.index = String(flatIndex);
        card.tabIndex = 0;
        card.setAttribute("role", "button");
        if (item.waitingOnMe) card.classList.add("is-waiting");
        if (flatIndex === hubFocusIndex) card.classList.add("is-hub-focus");

        card.appendChild(paintHubChange(item, { meta: "key" }));

        card.addEventListener("click", (event) => openHubItem(item, event.currentTarget));
        card.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openHubItem(item, card);
          }
        });
        list.appendChild(card);
        flatIndex += 1;
      }
      col.append(head, list);
      board.appendChild(col);
    }
    window.requestAnimationFrame(updateHubBoardScrollHint);
  }

  function paintHubItems(items, { keepFocus = false } = {}) {
    const rows = document.getElementById("rows");
    const state = document.getElementById("state");
    const count = document.getElementById("count");
    const hub = document.getElementById("hub");
    if (!rows) return;
    if (Array.isArray(items)) hubItems = items;
    paintAccountInbox();
    const visible = filteredHubItems();
    const prevKey =
      keepFocus && hubFocusIndex >= 0
        ? (
            hub?.dataset.view === "board"
              ? document.querySelectorAll("#hub-board .hub-card")[hubFocusIndex]
              : rows.querySelectorAll("tr")[hubFocusIndex]
          )?.dataset?.key
        : null;

    rows.replaceChildren();
    visible.forEach((item, index) => {
      const tr = document.createElement("tr");
      tr.dataset.key = item.key || "";
      tr.dataset.index = String(index);
      if (item.waitingOnMe) tr.classList.add("is-waiting");
      const title = document.createElement("td");
      title.appendChild(paintHubChange(item));
      tr.append(title);
      tr.addEventListener("click", (event) => {
        openHubItem(item, event.currentTarget);
      });
      rows.appendChild(tr);
    });

    if (hub?.dataset.view === "board") {
      if (prevKey) {
        const flat = hubStatusColumns(visible).flatMap(([, cards]) => cards);
        hubFocusIndex = flat.findIndex((item) => item.key === prevKey);
      }
      paintHubBoard(visible);
    } else if (prevKey) {
      hubFocusIndex = visible.findIndex((item) => item.key === prevKey);
    }

    if (hubFocusIndex >= visible.length) hubFocusIndex = visible.length - 1;
    setHubFocus(hubFocusIndex, false);
    if (state) {
      state.hidden = hub?.dataset.view === "board" || visible.length > 0;
      state.textContent = visible.length
        ? ""
        : hubItems.length
          ? "Keine Treffer."
          : "Keine Tickets in Jira.";
    }
    if (count) {
      count.textContent = hubItems.length ? `${hubItems.length} Tickets` : "";
    }
  }


  function prefersReducedMotion() {
    return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  }

  async function openHubItem(item) {
    if (isCreatingChange()) {
      const ok = window.confirm(
        "Du legst gerade einen neuen Change an. Entwurf verwerfen und dieses Ticket öffnen?"
      );
      if (!ok) return;
      intakeStarted = false;
      publishing = false;
      autoFillBusy = false;
      aiReviewPending = false;
      resetTicketState();
      document.body.classList.remove("ticket-creating", "field-flow");
    }
    if (!item || openHubItem._busy) return;
    openHubItem._busy = true;
    try {
      rememberTicketFrom("");
      if (syncedRequestId) markCommentVisit(syncedRequestId);
      saveScrollMemory();
      const hub = document.getElementById("hub");
      if (hub) hub.hidden = true;
      document.body.classList.remove("is-opening-ticket");
      if (item.requestId) {
        history.replaceState({}, "", `/workspace/${item.requestId}`);
        await openExisting(item.requestId, {
          skipHubExit: true,
          deferHideHub: true,
          animate: false,
        });
      } else {
        await openJiraTicket(item.key, {
          skipHubExit: true,
          deferHideHub: true,
          animate: false,
        });
      }
    } finally {
      openHubItem._busy = false;
    }
  }

  function currentHubTicketIndex() {
    const list = filteredHubItems();
    const jiraKey = document.getElementById("ticket-jira-key")?.textContent?.trim() || "";
    return list.findIndex(
      (item) =>
        (syncedRequestId && item.requestId === syncedRequestId) ||
        (jiraKey && item.key === jiraKey)
    );
  }

  function openTicketSibling(delta) {
    if (isCreatingChange()) return;
    const list = filteredHubItems();
    if (!list.length) return;
    let idx = currentHubTicketIndex();
    if (idx < 0) idx = 0;
    const next = list[idx + delta];
    if (!next) return;
    openHubItem(next);
  }

  function setHubFocus(index, scrollIntoView) {
    const hub = document.getElementById("hub");
    const onBoard = hub?.dataset.view === "board";
    const list = onBoard
      ? [...(document.querySelectorAll("#hub-board .hub-card") || [])]
      : [...(document.getElementById("rows")?.querySelectorAll("tr") || [])];
    list.forEach((el) => el.classList.remove("is-hub-focus"));
    if (index < 0 || index >= list.length) {
      hubFocusIndex = -1;
      return;
    }
    hubFocusIndex = index;
    const el = list[index];
    el.classList.add("is-hub-focus");
    if (scrollIntoView) el.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  function focusedHubItems() {
    if (hubView === "board") {
      return hubStatusColumns(filteredHubItems()).flatMap(([, cards]) => cards);
    }
    return filteredHubItems();
  }

  function setHubSync(text, state) {
    const hubSync = document.getElementById("hub-sync");
    if (!hubSync) return;
    hubSync.hidden = false;
    hubSync.textContent = text;
    hubSync.dataset.state = state || "";
    if (state === "ok") {
      window.clearTimeout(setHubSync.hideTid);
      setHubSync.hideTid = window.setTimeout(() => {
        if (hubSync.dataset.state === "ok") hubSync.textContent = "Aktuell";
      }, 2200);
    }
  }

  function softRefreshOpenTicket(requestId, delays = [1200, 3500, 8000]) {
    if (!requestId) return;
    for (const ms of delays) {
      window.setTimeout(() => {
        if (syncedRequestId !== requestId) return;
        // Während Inline-Edit nicht neu laden — sonst geht die Eingabe verloren.
        if (editingKey) return;
        void fetch(`/api/requests/${encodeURIComponent(requestId)}`)
          .then(async (r) => {
            if (!r.ok || syncedRequestId !== requestId || editingKey) return;
            // Kein erneutes Sync-Polling — sonst starten mehrere Follows parallel.
            applyRequest(await r.json(), { animate: false, skipSyncFollow: true });
          })
          .catch(() => {
            /* lokaler Stand bleibt */
          });
      }, ms);
    }
  }

  async function fetchHubIssues(retries = 2) {
    let lastErr;
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const r = await fetch("/api/jira/issues?limit=50");
        const body = await r.json().catch(() => ({}));
        if (!r.ok) {
          throw new Error(
            typeof body.detail === "string" ? body.detail : "Jira nicht erreichbar"
          );
        }
        return body;
      } catch (err) {
        lastErr = err;
        if (attempt < retries) {
          await new Promise((resolve) =>
            window.setTimeout(resolve, 500 * (attempt + 1))
          );
        }
      }
    }
    throw lastErr || new Error("Jira nicht erreichbar");
  }

  async function loadHub() {
    const hub = document.getElementById("hub");
    const rows = document.getElementById("rows");
    const state = document.getElementById("state");
    if (!hub || !rows) return;
    if (intakeStarted || document.body.classList.contains("ticket-active")) return;
    hub.hidden = false;
    updateOfflineBanner();

    let painted = false;
    try {
      const cached = JSON.parse(sessionStorage.getItem(HUB_CACHE_KEY) || "null");
      if (Array.isArray(cached?.items) && cached.items.length) {
        paintHubItems(cached.items);
        painted = true;
        setHubSync("gerade aktualisiert…", "busy");
        restoreHubScroll();
      }
    } catch (_) {
      /* ignore */
    }

    if (!painted && state) {
      state.hidden = false;
      state.textContent = "Lade Tickets…";
    }

    if (navigator.onLine === false) {
      if (!painted && state) {
        state.hidden = false;
        state.textContent = "Offline — zwischengespeicherte Tickets nicht verfügbar.";
      }
      setHubSync("Offline", "err");
      return;
    }

    try {
      const body = await fetchHubIssues(2);
      const items = body.items || [];
      paintHubItems(items);
      restoreHubScroll();
      try {
        sessionStorage.setItem(
          HUB_CACHE_KEY,
          JSON.stringify({ items, at: Date.now() })
        );
      } catch (_) {
        /* ignore */
      }
      setHubSync("gerade aktualisiert", "ok");
      if (intakeStarted || document.body.classList.contains("ticket-active")) {
        hub.hidden = true;
        return;
      }
      // Abgleich nur anstoßen — Antwort nicht abwarten (blockiert sonst Ticket-Öffnen).
      void fetch("/api/jira/issues?limit=50&sync=1").catch(() => {});
      // Nach Hintergrund-Sync Hub einmal nachziehen, damit Kommentare/Stand stimmen.
      window.setTimeout(() => {
        if (intakeStarted || document.body.classList.contains("ticket-active")) return;
        void fetchHubIssues(1)
          .then((fresh) => {
            if (intakeStarted || document.body.classList.contains("ticket-active")) {
              return;
            }
            const next = fresh.items || [];
            paintHubItems(next);
            try {
              sessionStorage.setItem(
                HUB_CACHE_KEY,
                JSON.stringify({ items: next, at: Date.now() })
              );
            } catch (_) {
              /* ignore */
            }
            setHubSync("gerade aktualisiert", "ok");
          })
          .catch(() => {});
      }, 6500);
    } catch (err) {
      if (!painted && state) {
        state.hidden = false;
        state.textContent = String(err.message || err);
      }
      setHubSync("Laden fehlgeschlagen", "err");
    }
  }

  async function openJiraTicket(key, { skipHubExit = false, deferHideHub = false, animate = true } = {}) {
    if (isCreatingChange()) return;
    if (!deferHideHub) {
      const hub = document.getElementById("hub");
      if (hub) hub.hidden = true;
    }
    const r = await fetch(`/api/jira/issues/${encodeURIComponent(key)}/import`, {
      method: "POST",
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      flash(
        typeof body.detail === "string" ? body.detail : "Import fehlgeschlagen",
        true
      );
      return;
    }
    history.replaceState({}, "", `/workspace/${body.id}`);
    applyRequest(body, { animate });
    if (body.enrichPending && body.id) softRefreshOpenTicket(body.id);
  }

  function paintTicketNav() {
    const ctx = document.getElementById("ticket-nav-context");
    if (!ctx) return;
    if (ticketOpenedFrom === "chat") {
      ctx.hidden = false;
      ctx.textContent = "Aus dem Chat";
    } else {
      ctx.hidden = true;
      ctx.textContent = "";
    }
  }

  function rememberTicketFrom(from) {
    ticketOpenedFrom = from === "chat" ? "chat" : "";
    try {
      if (ticketOpenedFrom) sessionStorage.setItem(TICKET_FROM_KEY, ticketOpenedFrom);
      else sessionStorage.removeItem(TICKET_FROM_KEY);
    } catch (_) {
      /* ignore */
    }
  }

  function openTicketFromChat(id) {
    if (!id) return;
    rememberTicketFrom("chat");
    void openExisting(id, { animate: true, from: "chat" });
  }

  async function openExisting(
    slug,
    { skipHubExit = false, deferHideHub = false, animate = true, from = "" } = {}
  ) {
    if (isCreatingChange()) return;
    if (from === "chat") rememberTicketFrom("chat");
    else if (!ticketOpenedFrom) {
      try {
        ticketOpenedFrom = sessionStorage.getItem(TICKET_FROM_KEY) || "";
      } catch (_) {
        ticketOpenedFrom = "";
      }
    }
    if (!deferHideHub) {
      const hub = document.getElementById("hub");
      if (hub) hub.hidden = true;
    }
    const local = await fetch(`/api/requests/${encodeURIComponent(slug)}`);
    if (local.ok) {
      const detail = await local.json();
      applyRequest(detail, { animate });
      const sync = detail.sync || {};
      const ref = String(detail.reference || "").trim();
      const jiraKey =
        sync.externalKey ||
        detail.externalKey ||
        (/^[A-Z][A-Z0-9]+-\d+$/i.test(ref) ? ref : "");
      const requestId = detail.id || slug;
      // Jira-Nachzug im Hintergrund — Ticket sofort zeigen, nicht auf Import warten.
      if (jiraKey) {
        void fetch(`/api/jira/issues/${encodeURIComponent(jiraKey)}/import`, {
          method: "POST",
        })
          .then(async (r) => {
            if (!r.ok || syncedRequestId !== requestId) return;
            const body = await r.json();
            if (!editingKey) applyRequest(body, { animate: false });
            // Enrich (Kommentare/Anhänge) kommt verzögert — mehrfach nachladen.
            softRefreshOpenTicket(requestId);
          })
          .catch(() => {
            softRefreshOpenTicket(requestId, [2500, 7000]);
          });
      }
      return;
    }
    await openJiraTicket(slug, { skipHubExit: true, deferHideHub, animate });
  }

  function bootWorkspace() {
    const parts = location.pathname.split("/").filter(Boolean);
    const slug = parts[0] === "workspace" ? parts[1] : null;
    if (slug) {
      try {
        ticketOpenedFrom = sessionStorage.getItem(TICKET_FROM_KEY) || "";
      } catch (_) {
        ticketOpenedFrom = "";
      }
      void openExisting(slug);
      return;
    }
    void loadHub();
  }

  function backToHub() {
    if (syncedRequestId) markCommentVisit(syncedRequestId);
    saveScrollMemory();
    saveDraft(syncedRequestId, commentInput?.value || "");
    const fromChat = ticketOpenedFrom === "chat";
    rememberTicketFrom("");
    if (fromChat) {
      try {
        localStorage.setItem(HUB_VIEW_KEY, "chat");
      } catch (_) {
        /* ignore */
      }
    }
    history.replaceState({}, "", "/workspace");
    location.assign("/workspace");
  }

  function isTypingTarget(el) {
    if (!el) return false;
    const tag = String(el.tagName || "").toLowerCase();
    return (
      tag === "input" ||
      tag === "textarea" ||
      tag === "select" ||
      el.isContentEditable
    );
  }

  document.addEventListener("keydown", (event) => {
    const hubVisible =
      !document.body.classList.contains("ticket-active") &&
      !document.getElementById("hub")?.hidden;
    const typing = isTypingTarget(event.target);

    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      if (commentInput && document.activeElement === commentInput) {
        event.preventDefault();
        commentForm?.requestSubmit();
      }
      return;
    }

    if (event.key === "Escape") {
      if (fileLightbox && !fileLightbox.hidden) {
        event.preventDefault();
        closeLightbox();
        return;
      }
      if (!commentMention?.hidden) {
        hideMentions();
        return;
      }
      if (document.body.classList.contains("ticket-active")) {
        event.preventDefault();
        backToHub();
      }
      return;
    }

    if (typing) return;

    if (event.key === "/" && hubVisible) {
      event.preventDefault();
      document.getElementById("hub-search")?.focus();
      return;
    }

    if (
      event.key === "c" &&
      document.body.classList.contains("ticket-active") &&
      commentsAllowed()
    ) {
      event.preventDefault();
      commentInput?.focus();
      return;
    }

    if (
      document.body.classList.contains("ticket-active") &&
      !isCreatingChange() &&
      (event.key === "j" || event.key === "k")
    ) {
      event.preventDefault();
      openTicketSibling(event.key === "j" ? 1 : -1);
      return;
    }

    if (!hubVisible) return;

    if (event.key === "v") {
      event.preventDefault();
      applyHubView(hubView === "board" ? "list" : "board");
      return;
    }

    const visible = focusedHubItems();
    if (event.key === "j" || event.key === "ArrowDown") {
      event.preventDefault();
      setHubFocus(Math.min((hubFocusIndex < 0 ? -1 : hubFocusIndex) + 1, visible.length - 1), true);
    } else if (event.key === "k" || event.key === "ArrowUp") {
      event.preventDefault();
      setHubFocus(Math.max((hubFocusIndex < 0 ? 0 : hubFocusIndex) - 1, 0), true);
    } else if (event.key === "Enter" && hubFocusIndex >= 0) {
      event.preventDefault();
      openHubItem(visible[hubFocusIndex]);
    }
  });

  document.getElementById("ticket-back")?.addEventListener("click", () => {
    backToHub();
  });
  document.getElementById("hub-view-list")?.addEventListener("click", () => {
    applyHubView("list");
  });
  document.getElementById("hub-view-board")?.addEventListener("click", () => {
    applyHubView("board");
  });
  document.getElementById("hub-view-chat")?.addEventListener("click", () => {
    applyHubView("chat");
  });
  document.getElementById("hub-view-report")?.addEventListener("click", () => {
    applyHubView("report");
  });
  document.getElementById("hub-report-owners")?.addEventListener("click", (event) => {
    const th = event.target.closest("th[data-sort]");
    if (th) {
      toggleReportSort("owners", th.dataset.sort);
      return;
    }
    const tr = event.target.closest("tbody tr[data-owner]");
    if (!tr) return;
    reportOwner = reportOwner === tr.dataset.owner ? "" : tr.dataset.owner;
    paintEffortReport();
  });
  document.getElementById("hub-report-changes")?.addEventListener("click", (event) => {
    const th = event.target.closest("th[data-sort]");
    if (!th) return;
    toggleReportSort("changes", th.dataset.sort);
  });
  document.getElementById("hub-report-clear")?.addEventListener("click", () => {
    reportOwner = "";
    paintEffortReport();
  });
  document.getElementById("hub-chat-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    if (hubChatBusy) {
      hubChatAbort?.abort();
      return;
    }
    const input = document.getElementById("hub-chat-input");
    void sendHubChat(input?.value || "");
  });
  document.getElementById("hub-chat-input")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      document.getElementById("hub-chat-form")?.requestSubmit();
    }
  });
  document.getElementById("hub-chat-input")?.addEventListener("input", () => {
    resizeHubChatInput();
    syncHubChatSend();
  });
  document.getElementById("hub-chat-thread")?.addEventListener("scroll", () => {
    const thread = hubChatThread();
    hubChatStick = hubChatNearBottom(thread);
    const jump = document.getElementById("hub-chat-jump");
    if (jump) {
      jump.hidden = hubChatStick || !thread?.querySelector(".hub-chat-bubble.is-user, .hub-chat-bubble.is-assistant");
    }
  });
  document.getElementById("hub-chat-jump")?.addEventListener("click", () => {
    hubChatStick = true;
    stickHubChat(hubChatThread());
  });
  document.getElementById("hub-chat-draft-create")?.addEventListener("click", () => {
    void sendHubChat("Change anlegen");
  });
  document.getElementById("hub-chat-suggest")?.addEventListener("click", (event) => {
    const chip = event.target?.closest?.(".hub-chat-chip");
    if (!chip) return;
    const prompt = String(chip.getAttribute("data-prompt") || chip.textContent || "").trim();
    if (prompt) void sendHubChat(prompt);
  });
  document.getElementById("hub-chat-reset")?.addEventListener("click", () => {
    resetHubChat();
  });
  document.getElementById("hub-chat-history")?.addEventListener("click", (event) => {
    event.stopPropagation();
    const menu = document.getElementById("hub-chat-history-menu");
    const btn = document.getElementById("hub-chat-history");
    if (!menu) return;
    const open = menu.hidden;
    closeHubChatHistoryMenu();
    if (open) {
      menu.hidden = false;
      btn?.setAttribute("aria-expanded", "true");
      void paintHubChatHistoryMenu();
    }
  });
  document.addEventListener("click", () => closeHubChatHistoryMenu());
  document.getElementById("hub-chat-history-menu")?.addEventListener("click", (event) => {
    event.stopPropagation();
  });
  resizeHubChatInput();

  document.getElementById("hub-board")?.addEventListener(
    "scroll",
    () => updateHubBoardScrollHint(),
    { passive: true }
  );
  window.addEventListener("resize", () => updateHubBoardScrollHint());
  try {
    const saved = localStorage.getItem(HUB_VIEW_KEY);
    if (saved === "board" || saved === "list" || saved === "chat" || saved === "report")
      applyHubView(saved, { persist: false });
    else applyHubView("chat", { persist: false });
  } catch (_) {
    applyHubView("chat", { persist: false });
  }

  document.getElementById("hub-search")?.addEventListener("input", () => {
    if (hubView === "report") {
      paintEffortReport();
      return;
    }
    paintHubItems(hubItems);
    window.clearTimeout(filteredHubItems.searchTid);
    filteredHubItems.searchTid = window.setTimeout(() => {
      const q = String(document.getElementById("hub-search")?.value || "").trim();
      if (intakeStarted || document.body.classList.contains("ticket-active")) return;
      const url = q
        ? `/api/jira/issues?limit=50&q=${encodeURIComponent(q.slice(0, 80))}`
        : "/api/jira/issues?limit=50";
      void fetch(url)
        .then(async (r) => {
          const body = await r.json().catch(() => ({}));
          if (!r.ok) return;
          paintHubItems(body.items || []);
          try {
            if (!q) {
              sessionStorage.setItem(
                HUB_CACHE_KEY,
                JSON.stringify({ items: body.items || [], at: Date.now() })
              );
            }
          } catch (_) {
            /* ignore */
          }
        })
        .catch(() => {
          /* lokale Filterung bleibt */
        });
    }, 280);
  });

  commentInput?.addEventListener("paste", (event) => {
    const files = [...(event.clipboardData?.files || [])].filter((f) =>
      String(f.type || "").startsWith("image/")
    );
    if (!files.length) return;
    event.preventDefault();
    const stamped = files.map((file, i) => {
      const name = file.name && file.name !== "image.png"
        ? file.name
        : `screenshot-${Date.now()}-${i + 1}.png`;
      return new File([file], name, { type: file.type || "image/png" });
    });
    void addFiles(stamped);
    filesSection.hidden = false;
    commentHintPaste = true;
    updateCommentFormHint();
    window.setTimeout(() => {
      commentHintPaste = false;
      updateCommentFormHint();
    }, 4000);
    flash(`${stamped.length} Screenshot${stamped.length === 1 ? "" : "s"} angehängt`);
  });

  bootWorkspace();
  commentForm?.addEventListener("submit", (event) => {
    void submitComment(event);
  });
  commentInput?.addEventListener("input", onCommentInput);
  commentInput?.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideMentions();
  });
  commentInput?.addEventListener("blur", () => {
    window.setTimeout(hideMentions, 120);
  });
  effortSheetOpen?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    openEffortTemplate();
  });
  statusUpdateOpen?.addEventListener("click", (event) => {
    event.preventDefault();
    if (!syncedRequestId) return;
    location.assign(`/status-update/${encodeURIComponent(syncedRequestId)}`);
  });
  void loadEffortSheetSettings();
})();
