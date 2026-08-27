(function () {
  const form = document.getElementById("form");
  const input = document.getElementById("input");
  const send = document.getElementById("send");
  const choiceRow = document.getElementById("choice-row");
  const jiraSuggest = document.getElementById("jira-suggest");
  const enhanceBtn = document.getElementById("ai-enhance");
  const dateWrap = document.getElementById("date-wrap");
  const dateCal = document.getElementById("date-cal");
  if (!form || !input || !send) return;

  let busy = false;
  let multiPicks = [];

  function stepLong() {
    return Boolean(window.getTicketStep?.()?.long);
  }

  function isMultiStep(step) {
    return Boolean(step?.multi);
  }

  function multiKey(item) {
    return String(item?.name || item?.label || "")
      .trim()
      .toLowerCase();
  }

  function multiJoined() {
    return multiPicks.map((item) => item.name || item.label).filter(Boolean).join(", ");
  }

  function hasMultiPick(item) {
    const key = multiKey(item);
    return multiPicks.some((pick) => multiKey(pick) === key);
  }

  function toggleMultiPick(item) {
    const name = String(item.name || item.label || "").trim();
    if (!name) return;
    const key = multiKey(item);
    const idx = multiPicks.findIndex((pick) => multiKey(pick) === key);
    if (idx >= 0) multiPicks.splice(idx, 1);
    else multiPicks.push({ name, label: item.label || name });
    void refreshJiraSuggest();
  }

  async function addMultiFromText(text) {
    const raw = String(text || "").trim();
    if (!raw) return;
    let name = raw;
    let label = raw;
    try {
      const hits = await window.jiraSuggest?.("components", raw);
      const exact = (hits || []).find(
        (item) =>
          item.name === raw ||
          item.label === raw ||
          (item.displayName && item.displayName === raw)
      );
      if (exact) {
        name = exact.name || exact.label;
        label = exact.label || exact.name || name;
      }
    } catch {
      /* Freitext behalten */
    }
    toggleMultiPick({ name, label });
    input.value = "";
    resizeInput();
  }

  function resizeInput() {
    input.style.height = "auto";
    const floor = stepLong() ? 88 : 40;
    const cap = stepLong() ? 220 : 180;
    const next = Math.min(Math.max(input.scrollHeight || floor, floor), cap);
    input.style.height = `${next}px`;
  }

  function setBusy(on) {
    busy = on;
    form.classList.toggle("disabled", on);
    input.disabled = on;
    send.disabled = on;
    if (enhanceBtn) enhanceBtn.disabled = on;
    dateWrap?.classList.toggle("disabled", on);
    if (choiceRow) {
      choiceRow.querySelectorAll("button").forEach((btn) => {
        btn.disabled = on;
      });
    }
    if (jiraSuggest) {
      jiraSuggest.querySelectorAll("button").forEach((btn) => {
        btn.disabled = on;
      });
    }
  }

  const WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
  const MONTHS = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
  ];

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function toIso(year, month, day) {
    return `${year}-${pad(month + 1)}-${pad(day)}`;
  }

  function isoToDe(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || "").trim());
    return m ? `${m[3]}.${m[2]}.${m[1]}` : "";
  }

  function parseIso(value) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || "").trim());
    if (!m) return null;
    const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function mountCalendar(host, opts) {
    if (!host) return;
    const selected = parseIso(opts?.value);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    let cursor = selected
      ? new Date(selected.getFullYear(), selected.getMonth(), 1)
      : new Date(today.getFullYear(), today.getMonth(), 1);
    const yearMin = today.getFullYear() - 5;
    const yearMax = today.getFullYear() + 20;

    function paint() {
      host.replaceChildren();
      host.classList.add("cal");

      const head = document.createElement("div");
      head.className = "cal-head";
      const prev = document.createElement("button");
      prev.type = "button";
      prev.className = "cal-nav";
      prev.setAttribute("aria-label", "Vorheriger Monat");
      prev.textContent = "‹";
      prev.onclick = () => {
        cursor.setMonth(cursor.getMonth() - 1);
        paint();
      };
      const next = document.createElement("button");
      next.type = "button";
      next.className = "cal-nav";
      next.setAttribute("aria-label", "Nächster Monat");
      next.textContent = "›";
      next.onclick = () => {
        cursor.setMonth(cursor.getMonth() + 1);
        paint();
      };

      const title = document.createElement("div");
      title.className = "cal-title";

      const monthSelect = document.createElement("select");
      monthSelect.className = "cal-month";
      monthSelect.setAttribute("aria-label", "Monat");
      MONTHS.forEach((name, idx) => {
        const opt = document.createElement("option");
        opt.value = String(idx);
        opt.textContent = name;
        if (idx === cursor.getMonth()) opt.selected = true;
        monthSelect.appendChild(opt);
      });
      monthSelect.addEventListener("mousedown", (ev) => ev.stopPropagation());
      monthSelect.addEventListener("click", (ev) => ev.stopPropagation());
      monthSelect.addEventListener("change", () => {
        const month = Number.parseInt(monthSelect.value, 10);
        if (!Number.isFinite(month)) return;
        cursor = new Date(cursor.getFullYear(), month, 1);
        paint();
      });

      const yearSelect = document.createElement("select");
      yearSelect.className = "cal-year";
      yearSelect.setAttribute("aria-label", "Jahr");
      for (let y = yearMin; y <= yearMax; y += 1) {
        const opt = document.createElement("option");
        opt.value = String(y);
        opt.textContent = String(y);
        if (y === cursor.getFullYear()) opt.selected = true;
        yearSelect.appendChild(opt);
      }
      yearSelect.addEventListener("mousedown", (ev) => ev.stopPropagation());
      yearSelect.addEventListener("click", (ev) => ev.stopPropagation());
      yearSelect.addEventListener("change", () => {
        const year = Number.parseInt(yearSelect.value, 10);
        if (!Number.isFinite(year)) return;
        cursor = new Date(year, cursor.getMonth(), 1);
        paint();
      });

      title.append(monthSelect, yearSelect);
      head.append(prev, title, next);

      const week = document.createElement("div");
      week.className = "cal-week";
      WEEKDAYS.forEach((name) => {
        const el = document.createElement("span");
        el.textContent = name;
        week.appendChild(el);
      });

      const grid = document.createElement("div");
      grid.className = "cal-grid";
      const year = cursor.getFullYear();
      const month = cursor.getMonth();
      const startPad = (new Date(year, month, 1).getDay() + 6) % 7;
      const count = new Date(year, month + 1, 0).getDate();
      // Immer 6 Wochen → feste Höhe, unabhängig vom Monat
      const rows = 42;

      for (let i = 0; i < rows; i += 1) {
        const dayNum = i - startPad + 1;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "cal-day";
        if (dayNum < 1 || dayNum > count) {
          btn.disabled = true;
          btn.classList.add("is-empty");
          grid.appendChild(btn);
          continue;
        }
        const iso = toIso(year, month, dayNum);
        const date = new Date(year, month, dayNum);
        btn.textContent = String(dayNum);
        btn.dataset.iso = iso;
        if (date.getTime() === today.getTime()) btn.classList.add("is-today");
        if (
          selected &&
          date.getFullYear() === selected.getFullYear() &&
          date.getMonth() === selected.getMonth() &&
          date.getDate() === selected.getDate()
        ) {
          btn.classList.add("is-selected");
        }
        btn.onclick = () => opts?.onPick?.(iso, btn);
        grid.appendChild(btn);
      }

      const todayBtn = document.createElement("button");
      todayBtn.type = "button";
      todayBtn.className = "cal-today";
      todayBtn.textContent = "Heute";
      todayBtn.onclick = () =>
        opts?.onPick?.(
          toIso(today.getFullYear(), today.getMonth(), today.getDate()),
          todayBtn
        );

      host.append(head, week, grid, todayBtn);
    }

    paint();
  }

  window.mountCalendar = mountCalendar;

  function renderChoices(step) {
    if (!choiceRow) return;
    choiceRow.replaceChildren();
    const choices = step?.choices || [];
    if (!choices.length) {
      choiceRow.hidden = true;
      form.classList.remove("hidden");
      return;
    }
    if (step.keepForm) form.classList.remove("hidden");
    else form.classList.add("hidden");
    choiceRow.hidden = false;
    choices.forEach((value) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "suggestion";
      chip.textContent = value;
      chip.onclick = () => void submitAnswer(value, chip);
      choiceRow.appendChild(chip);
    });
  }

  function syncEnhance(step) {
    if (!enhanceBtn) return;
    const on = Boolean(step?.enhance);
    enhanceBtn.hidden = !on;
    form.classList.toggle("has-enhance", on);
    enhanceBtn.textContent = "mit KI aufwerten";
    enhanceBtn.disabled = false;
  }

  function hideJiraSuggest() {
    if (!jiraSuggest) return;
    jiraSuggest.hidden = true;
    jiraSuggest.classList.remove("is-tags-multi");
    jiraSuggest.innerHTML = "";
  }

  let suggestTimer = 0;
  let suggestReq = 0;
  let autoCompleting = false;

  function uniqueMatch(items, query) {
    if (items.length !== 1) return null;
    const item = items[0];
    const q = String(query || "").trim().toLowerCase();
    if (!q) return null;
    const name = String(item.name || "").toLowerCase();
    const display = String(item.displayName || "").toLowerCase();
    const label = String(item.label || "").toLowerCase();
    if (name === q || display === q || label === q) return null;
    const hay = `${display} ${name} ${label}`;
    if (!hay.includes(q) && !display.startsWith(q) && !name.startsWith(q)) return null;
    return item;
  }

  function applyComposerAutocomplete(item, query) {
    const filled = item.label || item.displayName || item.name;
    if (!filled || filled === input.value) return;
    autoCompleting = true;
    const start = query.length;
    input.value = filled;
    resizeInput();
    try {
      input.setSelectionRange(start, filled.length);
    } catch {
      /* ignore */
    }
    autoCompleting = false;
  }

  function renderJiraSuggest(items, query, kind) {
    if (!jiraSuggest) return;
    jiraSuggest.innerHTML = "";
    const step = window.getTicketStep?.();
    const multi = isMultiStep(step) && kind === "components";
    const browseAll =
      kind === "components" ||
      (typeof kind === "string" && kind.startsWith("option:"));
    const showEmpty = Boolean(query) || browseAll;
    if (!query && !browseAll) {
      hideJiraSuggest();
      return;
    }
    if (query && !multi) {
      const only = uniqueMatch(items, query);
      if (only) applyComposerAutocomplete(only, query);
    }
    if (multi && step?.hint) {
      const hint = document.createElement("p");
      hint.className = "field-tags-hint";
      hint.textContent = step.hint;
      jiraSuggest.appendChild(hint);
    }
    if (!items.length) {
      if (!showEmpty) {
        hideJiraSuggest();
        return;
      }
      jiraSuggest.hidden = false;
      const empty = document.createElement("span");
      empty.className = "field-lookup-empty";
      empty.textContent =
        browseAll && !query
          ? kind === "components"
            ? "Keine Stichwörter / Tags geladen"
            : "Keine Optionen aus Jira geladen"
          : "Keine Jira-Treffer";
      jiraSuggest.appendChild(empty);
      return;
    }
    jiraSuggest.hidden = false;
    jiraSuggest.classList.toggle("is-tags-multi", multi);
    const chipHost = multi ? document.createElement("div") : jiraSuggest;
    if (multi) chipHost.className = "field-tags-chips";
    items.forEach((item) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "suggestion";
      chip.textContent = item.label || item.name;
      if (multi) {
        if (hasMultiPick(item)) chip.classList.add("is-selected");
        chip.onclick = () => {
          toggleMultiPick(item);
          renderJiraSuggest(items, query, kind);
        };
      } else {
        if (items.length === 1 && query) chip.classList.add("is-selected");
        chip.onclick = () => void submitAnswer(item.name || item.label, chip);
      }
      chipHost.appendChild(chip);
    });
    if (multi) {
      const go = document.createElement("button");
      go.type = "button";
      go.className = "suggestion go field-tags-go";
      go.textContent = "Weiter";
      go.disabled = multiPicks.length === 0;
      go.title = multiPicks.length
        ? "Auswahl übernehmen"
        : "Mindestens ein Tag wählen";
      go.onclick = () => {
        if (!multiPicks.length) return;
        const joined = multiJoined();
        multiPicks = [];
        void submitAnswer(joined, go);
      };
      const body = document.createElement("div");
      body.className = "field-tags-body";
      const actions = document.createElement("div");
      actions.className = "field-tags-actions";
      actions.appendChild(go);
      body.append(chipHost, actions);
      jiraSuggest.appendChild(body);
    }
  }

  async function refreshJiraSuggest() {
    const step = window.getTicketStep?.();
    if (!step?.jiraLookup || !window.jiraSuggest) {
      hideJiraSuggest();
      return;
    }
    const query = input.value.trim();
    const current = ++suggestReq;
    const items = await window.jiraSuggest(step.jiraLookup, query);
    if (current !== suggestReq) return;
    if (window.getTicketStep?.()?.key !== step.key) return;
    renderJiraSuggest(items, query, step.jiraLookup);
  }

  function syncInput() {
    const step = window.getTicketStep?.();
    if (dateWrap) dateWrap.hidden = true;
    hideJiraSuggest();
    if (!isMultiStep(step)) multiPicks = [];
    if (!step) {
      input.placeholder = "";
      input.setAttribute("aria-label", "Eingabe");
      form.classList.add("hidden");
      syncEnhance(null);
      if (typeof window.ticketIdleUI === "function") {
        window.ticketIdleUI();
      } else if (choiceRow) {
        choiceRow.hidden = true;
      }
      return;
    }
    if (step.date) {
      form.classList.add("hidden");
      if (choiceRow) choiceRow.hidden = true;
      syncEnhance(null);
      if (dateWrap && dateCal) {
        dateWrap.hidden = false;
        mountCalendar(dateCal, {
          onPick: (iso, origin) => {
            const text = isoToDe(iso);
            if (text) void submitAnswer(text, origin);
          },
        });
      }
      return;
    }
    input.placeholder = step.placeholder;
    input.setAttribute("aria-label", step.placeholder);
    input.classList.toggle("is-long", Boolean(step.long));
    if (isMultiStep(step)) {
      if (choiceRow) {
        choiceRow.hidden = true;
        choiceRow.replaceChildren();
      }
      // Stichwörter / Tags: nur Chips, kein Suchfeld.
      if (step.jiraLookup === "components") {
        form.classList.add("hidden");
      } else {
        form.classList.remove("hidden");
      }
      syncEnhance(step);
      void refreshJiraSuggest();
      return;
    }
    renderChoices(step);
    syncEnhance(step);
    if (!step.choices?.length || step.keepForm) form.classList.remove("hidden");
    const lookup = step.jiraLookup || "";
    if (
      lookup === "components" ||
      lookup.startsWith("option:") ||
      (lookup && input.value.trim())
    ) {
      void refreshJiraSuggest();
    }
  }

  function flyFrom(origin, text, anchor, onDone) {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced || !origin || !anchor) {
      onDone();
      return;
    }
    const startBox = origin.getBoundingClientRect();
    const target = anchor.getBoundingClientRect();
    const startX = startBox.left;
    const startY = startBox.top + startBox.height / 2;
    const endX = target.left;
    const endY = target.top + target.height / 2;

    const node = document.createElement("span");
    const step = window.getTicketStep?.();
    node.className =
      step?.kind === "headline"
        ? "title-flight ticket-headline"
        : "title-flight ticket-row-value";
    node.textContent = text;
    node.style.left = `${startX}px`;
    node.style.top = `${startY}px`;
    node.style.setProperty("--dx", `${endX - startX}px`);
    node.style.setProperty("--dy", `${endY - startY}px`);
    document.body.appendChild(node);

    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      node.remove();
      onDone();
    };
    node.addEventListener("animationend", finish, { once: true });
    window.setTimeout(finish, 700);
  }

  async function polishText(text, field) {
    const snap = window.ticketSnapshot?.() || {};
    const title =
      snap.title || document.getElementById("ticket-headline")?.textContent || "";
    const key = field || window.getTicketStep?.()?.key || "description";
    let fields = {};
    if (key !== "description") {
      fields = { ...(snap.fields || {}) };
      if (["benefit", "reason", "solution", "risks"].includes(key)) {
        ["benefit", "reason", "solution", "risks"].forEach((item) => {
          if (item !== key) delete fields[item];
        });
      }
    }
    const r = await fetch("/api/sessions/polish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        title: key === "description" ? "" : title,
        field: key,
        kind: key === "description" ? "" : snap.kind || "",
        fields,
      }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      const detail = body.detail || `Serverfehler ${r.status}`;
      throw new Error(typeof detail === "string" ? detail : "KI nicht erreichbar");
    }
    const next = String(body.text || "").trim();
    if (!next) throw new Error("leere Aufbereitung");
    return next;
  }

  async function polishInField() {
    if (busy || !enhanceBtn) return;
    const text = input.value.trim();
    if (!text) {
      enhanceBtn.textContent = "Erst Text eingeben";
      setTimeout(() => {
        enhanceBtn.textContent = "mit KI aufwerten";
      }, 1400);
      return;
    }

    const idleLabel = "mit KI aufwerten";
    enhanceBtn.disabled = true;
    enhanceBtn.textContent = "KI arbeitet…";
    send.disabled = true;

    try {
      const next = await polishText(text, window.getTicketStep?.()?.key);
      input.value = next;
      input.dispatchEvent(new Event("input"));
      resizeInput();
      input.focus();
      enhanceBtn.textContent = "Überarbeitet";
      setTimeout(() => {
        if (enhanceBtn.textContent === "Überarbeitet") {
          enhanceBtn.textContent = idleLabel;
        }
      }, 1600);
    } catch (err) {
      enhanceBtn.textContent = "KI fehlgeschlagen";
      setTimeout(() => {
        enhanceBtn.textContent = idleLabel;
      }, 2200);
    } finally {
      enhanceBtn.disabled = false;
      send.disabled = false;
    }
  }

  async function submitAnswer(text, origin) {
    if (busy) return;
    const step = window.getTicketStep?.();
    if (!step || typeof window.prepareTicketField !== "function") return;
    if (step.choices?.length && !step.keepForm && !step.choices.includes(text)) return;

    if (step.jiraLookup && window.jiraSuggest && !isMultiStep(step)) {
      const unknown =
        typeof window.isUnknownFieldValue === "function"
          ? window.isUnknownFieldValue(text)
          : /^ich wei[sß]{1,2} es( noch)? nicht$/i.test(String(text || "").trim());
      if (!unknown) {
        try {
          const hits = await window.jiraSuggest(step.jiraLookup, text);
          const exact = hits.find(
            (item) =>
              item.name === text ||
              item.label === text ||
              (item.displayName && item.displayName === text)
          );
          if (exact) text = exact.name;
        } catch {
          /* Freitext */
        }
      }
    }

    setBusy(true);
    hideJiraSuggest();
    multiPicks = [];
    input.value = "";
    resizeInput();

    const anchor = window.prepareTicketField(text);
    if (!anchor) {
      setBusy(false);
      syncInput();
      return;
    }

    flyFrom(origin || input, text, anchor, () => {
      window.showTicketField?.();
      setBusy(false);
      syncInput();
      if (window.getTicketStep?.() && !window.getTicketStep()?.choices) input.focus();
    });
  }

  window.polishText = polishText;
  window.syncTicketInput = syncInput;

  enhanceBtn?.addEventListener("click", (event) => {
    event.preventDefault();
    void polishInField();
  });

  input.addEventListener("input", () => {
    if (autoCompleting) return;
    resizeInput();
    const step = window.getTicketStep?.();
    if (!step?.jiraLookup) {
      hideJiraSuggest();
      return;
    }
    const query = input.value.trim();
    const lookup = step.jiraLookup || "";
    if (!query && lookup !== "components" && !lookup.startsWith("option:")) {
      hideJiraSuggest();
      return;
    }
    window.clearTimeout(suggestTimer);
    suggestTimer = window.setTimeout(() => void refreshJiraSuggest(), 80);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Tab" && !event.shiftKey) {
      const selected = jiraSuggest?.querySelector(".suggestion.is-selected");
      if (selected && !jiraSuggest.hidden) {
        event.preventDefault();
        selected.click();
        return;
      }
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const step = window.getTicketStep?.();
    const text = input.value.trim();
    if (isMultiStep(step)) {
      if (text) {
        void addMultiFromText(text);
        return;
      }
      if (multiPicks.length) {
        const joined = multiJoined();
        multiPicks = [];
        void submitAnswer(joined, input);
      }
      return;
    }
    if (!text) return;
    void submitAnswer(text, input);
  });

  window.exitIntake = function () {};
  window.resizeIntakeField = resizeInput;
  window.openWorkspaceTicket = function () {};

  (window.whenAuthed || Promise.resolve()).then(() => {
    syncInput();
    resizeInput();
    input.focus();
  });
})();
