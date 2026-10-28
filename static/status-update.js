(() => {
  const id =
    (location.pathname.match(/\/status-update\/([0-9a-fA-F-]{36})\/?$/i) || [])[1] ||
    new URLSearchParams(location.search).get("id") ||
    "";
  const board = document.getElementById("su-board");
  const errorEl = document.getElementById("su-error");
  const summaryEl = document.getElementById("su-summary");
  const depsEl = document.getElementById("su-deps");
  const decisionsEl = document.getElementById("su-decisions");
  const risksEl = document.getElementById("su-risks");
  const nextEl = document.getElementById("su-next");
  let detail = null;
  let values = {};
  let updates = [];
  let comments = [];
  let saving = false;
  let viewingId = "";
  let draft = null;
  const saveBtn = document.getElementById("su-save");
  const healthEl = document.getElementById("su-health");
  const healthWrap = document.getElementById("su-health-wrap");
  const HEALTH = new Set(["green", "blue", "yellow", "red", "white", "done"]);
  const frozenEl = document.getElementById("su-frozen");
  const snapEl = document.getElementById("su-snapshots");

  function issueKey(raw) {
    const key = String(raw || "").trim();
    return /^[A-Z][A-Z0-9]+-\d+$/i.test(key) ? key : "";
  }

  function showIssueKey(prefix, key, url) {
    const box = document.getElementById(`${prefix}-key`);
    const link = document.getElementById(`${prefix}-key-link`);
    const sep = document.getElementById(`${prefix}-key-sep`);
    const issue = issueKey(key);
    if (!box || !link) return;
    if (!issue) {
      box.hidden = true;
      if (sep) sep.hidden = true;
      link.textContent = "";
      link.removeAttribute("href");
      return;
    }
    box.hidden = false;
    if (sep) sep.hidden = false;
    link.textContent = issue;
    const raw = String(url || "").trim();
    link.href = !raw || /live\.api\.schwarz/i.test(raw) ? `https://jira.schwarz/browse/${issue}` : raw;
    link.title = `In Jira öffnen: ${issue}`;
  }

  const esc = (s) =>
    String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  function parsePt(text) {
    const m = String(text || "").replace(",", ".").match(/(\d+(?:\.\d+)?)/);
    return m ? Number(m[1]) : 0;
  }

  function parseMoney(text) {
    const raw = String(text || "").replace(/\s/g, "").replace(/€/g, "");
    if (!raw) return 0;
    if (/^\d{1,3}(\.\d{3})+(,\d+)?$/.test(raw)) {
      return Number(raw.replace(/\./g, "").replace(",", ".")) || 0;
    }
    const n = Number(raw.replace(",", "."));
    return Number.isFinite(n) ? n : 0;
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

  function dateIso(raw) {
    const s = String(raw || "").trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    return deToIso(s);
  }

  function showDate(raw) {
    return isoToDe(dateIso(raw)) || String(raw || "").trim();
  }

  function fmtPt(n) {
    const value = Number(n);
    if (!value) return "—";
    return value.toLocaleString("de-DE", { maximumFractionDigits: 2 });
  }

  function fmtEuro(n) {
    if (n == null) return "—";
    return `${Number(n).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;
  }

  function moneyOrNull(raw) {
    const s = String(raw ?? "").trim();
    if (!s || s === "—") return null;
    return parseMoney(s);
  }

  function triple(fb, it, lic) {
    const parts = [fb, it, lic].filter((n) => n != null);
    return { fb, it, lic, sum: parts.length ? parts.reduce((a, b) => a + b, 0) : null };
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

  function scsPlan() {
    const effort = parsePt(values.effort_fb);
    if (effort) return effort;
    return parsePt(values.concept_scs_pt) + parsePt(values.operate_scs_pt);
  }

  function itPlan() {
    const effort = parsePt(values.effort_it);
    if (effort) return effort;
    return parsePt(values.concept_cit_pt) + parsePt(values.operate_cit_pt);
  }

  function people() {
    const named = ptLines(
      [values.concept_scs_pt_detail, values.operate_scs_pt_detail].filter(Boolean).join("; ")
    );
    const rows = named.length ? named : [];
    if (!rows.length && scsPlan()) rows.push({ name: "SCS", plan: scsPlan() });
    if (itPlan()) rows.push({ name: "IT", plan: itPlan() });
    return rows;
  }

  function latest() {
    const list = [...updates].sort((a, b) =>
      String(a.createdAt || "").localeCompare(String(b.createdAt || ""))
    );
    return list.length ? list[list.length - 1] : null;
  }

  function shown() {
    if (viewingId) return updates.find((item) => item.id === viewingId) || latest();
    return draft || latest();
  }

  function stamp(item) {
    const raw = item?.createdAt || item?.reportedOn || "";
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return isoToDe(item?.reportedOn) || "Snapshot";
    return date.toLocaleString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function actualPt(update) {
    const map = {};
    for (const row of update?.milestones || []) {
      if (!row || row.kind !== "pt") continue;
      map[String(row.name || "").toLowerCase()] = parsePt(row.actual);
    }
    return map;
  }

  function rag(planEnd, actualEnd, planPt, actualPt, hasIst) {
    if (!hasIst) return "blue";
    const late = Boolean(planEnd && actualEnd && actualEnd > planEnd);
    const over = planPt > 0 && actualPt > planPt + 0.001;
    return late || over ? "red" : "green";
  }

  function costRag(plan, actual) {
    if (actual.sum == null) return "blue";
    if (plan.sum != null && actual.sum > plan.sum + 0.001) return "red";
    return "green";
  }

  function ragLabel(key) {
    if (key === "red") return "Überzogen";
    if (key === "green") return "Im Plan";
    if (key === "yellow") return "Kritisch";
    if (key === "white") return "On hold";
    if (key === "done") return "Done";
    return "Im Blick behalten";
  }

  function liveStatus() {
    const planEnd = dateIso(values.end_date || values.end);
    const planPt = scsPlan() + itPlan();
    const usedPt = parsePt(read("pt:FB")) + parsePt(read("pt:IT"));
    const hasIst = usedPt > 0 || Boolean(read("euro-sach"));
    const schedule = rag(planEnd, "", planPt, usedPt, hasIst);
    const cost = costTone();
    let overall = "blue";
    if (schedule === "red") overall = "red";
    else if (cost === "yellow") overall = "yellow";
    else if (schedule === "green" || cost === "green") overall = "green";
    return { schedule, cost, overall };
  }

  function collectedMilestones() {
    const miles = [0, 1, 2, 3, 4, 5]
      .map((index) => ({
        kind: "mile",
        label: read(`mile-label-${index}`),
        state: read(`mile-state-${index}`),
      }))
      .filter((row) => row.label || row.state);
    return [
      ...miles,
      { kind: "pt", name: "FB", actual: read("pt:FB") },
      { kind: "pt", name: "IT", actual: read("pt:IT") },
    ];
  }

  let healthTimer = 0;

  function paintPill(pill, key) {
    if (!pill) return;
    pill.className = `stand-pill is-${key}`;
    pill.textContent = ragLabel(key);
  }

  function fieldValue(...keys) {
    for (const key of keys) {
      const text = String(values[key] || "").trim();
      if (text) return text;
    }
    return "";
  }

  function quarterLabel(raw) {
    const iso = dateIso(raw);
    const date = iso ? new Date(`${iso}T12:00:00`) : new Date();
    if (Number.isNaN(date.getTime())) return "";
    const quarter = Math.floor(date.getMonth() / 3) + 1;
    return `Q${quarter}/${date.getFullYear()}`;
  }

  function goalParts() {
    const goal = fieldValue("solution_goals", "problem");
    const benefit = fieldValue("benefit_savings");
    const description = String(detail?.description || "").trim();
    const lead = goal || description;
    const bullets = (benefit || "")
      .split(/\n|•|;/)
      .map((line) => line.replace(/^[-*]\s*/, "").trim())
      .filter((line) => line && line !== lead);
    return { lead, bullets };
  }

  function riskWord(plan, actual) {
    if (!actual) return "—";
    if (plan && actual > plan + 0.001) return "Überzogen";
    if (plan && actual >= plan * 0.8) return "n.i.O";
    return "i.O";
  }

  function costToneFrom(fbPlan, fbIst, itPlanPt, itIst, sachPlan, sachIst) {
    const words = [
      riskWord(fbPlan, fbIst),
      riskWord(itPlanPt, itIst),
      riskWord(sachPlan, sachIst),
    ];
    if (words.includes("Überzogen") || words.includes("n.i.O")) return "yellow";
    if (words.includes("i.O")) return "green";
    return "blue";
  }

  function costTone() {
    return costToneFrom(
      scsPlan(),
      parsePt(read("pt:FB")),
      itPlan(),
      parsePt(read("pt:IT")),
      moneyOrNull(values.material_costs) || 0,
      moneyOrNull(read("euro-sach"))
    );
  }

  function mileRows(now) {
    const saved = (now?.milestones || []).filter((row) => row && row.kind === "mile");
    const rows = saved.map((row) => ({ label: row.label || row.name || "", state: row.state || "" }));
    while (rows.length < 3) rows.push({ label: "", state: "" });
    return rows.slice(0, 6);
  }

  function applyLiveHealth() {
    if (viewingId) return;
    const live = liveStatus();
    paintPill(document.getElementById("su-schedule-pill"), live.schedule);
    paintPill(document.getElementById("su-cost-pill"), costTone());
    paintPill(document.getElementById("su-status-pill"), live.overall);
    if (healthEl?.value === live.overall) return;
    paintHealth(live.overall);
    if (healthEl) healthEl.dataset.dirty = "1";
    window.clearTimeout(healthTimer);
    healthTimer = window.setTimeout(() => void pushHealth(live.overall), 300);
  }

  function panel(title, tone, plan, ist, extra) {
    const lines = plan
      .map(([name, planValue], index) => {
        const istValue = ist[index]?.[1] ?? "";
        return `<div class="su-row${name === "Summe" ? " is-sum" : ""}"><span>${esc(name)}</span><span>${esc(planValue)}</span><span class="su-ist">${istValue}</span></div>`;
      })
      .join("");
    return `<section class="su-panel">
      <header class="su-panel-head">
        <h2>${esc(title)}</h2>
        <span class="stand-pill is-${esc(tone)}">${esc(ragLabel(tone))}</span>
      </header>
      <div class="su-table">
        <div class="su-row su-head"><span></span><span>Plan</span><span>Ist</span></div>
        ${lines}
      </div>
      ${extra || ""}
    </section>`;
  }

  function rows(pairs, html) {
    return pairs
      .map(
        ([name, value]) =>
          `<div class="su-line${name === "Summe" ? " is-sum" : ""}"><span>${esc(name)}</span><span>${
            html ? value : esc(value)
          }</span></div>`
      )
      .join("");
  }

  function field(key, value) {
    const lock = viewingId ? " disabled" : "";
    return `<input class="stand-ist" data-su-key="${esc(key)}" type="text" value="${esc(value || "")}" placeholder="—"${lock} />`;
  }

  function read(key) {
    return board.querySelector(`[data-su-key="${CSS.escape(key)}"]`)?.value.trim() || "";
  }

  function render() {
    if (!board) return;
    let now;
    let crew;
    let actuals;
    let planEnd;
    let actualEnd;
    let planPt;
    let usedPt;
    let planEuro;
    let istEuro;
    let hasIst;
    let schedule;
    let cost;
    let planDates;
    let istDates;
    let reasonLines;
    try {
      now = shown();
      crew = people();
      actuals = actualPt(now);
      planEnd = dateIso(values.end || values.end_date);
      actualEnd = dateIso(now?.actualEnd);
      planPt = crew.reduce((sum, row) => sum + row.plan, 0);
      usedPt = crew.reduce((sum, row) => sum + (actuals[row.name.toLowerCase()] || 0), 0);
      planEuro = triple(
        moneyOrNull(values.costs),
        moneyOrNull(values.it_costs),
        moneyOrNull(values.material_costs)
      );
      istEuro = triple(
        moneyOrNull(now?.costActualFb),
        moneyOrNull(now?.costActualIt),
        moneyOrNull(now?.costActualLicense)
      );
      hasIst = Boolean(now && (actualEnd || dateIso(now.actualStart) || usedPt > 0));
      schedule = rag(planEnd, actualEnd, planPt, usedPt, hasIst);
      cost = costRag(planEuro, istEuro);
      planDates = [
        ["Start", showDate(values.start || values.start_date) || "—"],
        ["Ende", showDate(values.end || values.end_date) || "—"],
        ...crew.map((row) => [row.name, fmtPt(row.plan)]),
      ];
      istDates = [
        ["Start", field("start", showDate(now?.actualStart))],
        ["Ende", field("end", showDate(now?.actualEnd))],
        ...crew.map((row) => [
          row.name,
          field(
            `pt:${row.name}`,
            actuals[row.name.toLowerCase()] ? fmtPt(actuals[row.name.toLowerCase()]) : ""
          ),
        ]),
      ];
      reasonLines = String(now?.scheduleReason || "")
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => `<p>${esc(line)}</p>`)
        .join("");
    } catch (err) {
      if (errorEl) {
        errorEl.hidden = false;
        errorEl.textContent = "Termine/Kosten konnten nicht geladen werden.";
      }
      return;
    }
    const forEl = document.getElementById("su-for");
    const projectName = detail?.title || detail?.steckbriefName || "Projekt";
    if (forEl) forEl.textContent = projectName;
    const sync = detail?.sync || {};
    showIssueKey("su", sync.externalKey || detail?.reference, sync.externalUrl);
    const standEl = document.getElementById("su-stand");
    if (standEl) standEl.textContent = `Stand: ${quarterLabel(values.end_date || values.end) || quarterLabel("")}`;
    const goal = goalParts();
    const goalEl = document.getElementById("su-goal");
    if (goalEl) {
      goalEl.innerHTML = `<h2>Zielsetzung und Campus-Nutzen</h2><p>${esc(goal.lead) || "Noch keine Zielsetzung im Change."}</p>${
        goal.bullets.length
          ? `<ul>${goal.bullets.map((line) => `<li>${esc(line)}</li>`).join("")}</ul>`
          : ""
      }`;
    }
    const peopleEl = document.getElementById("su-people");
    if (peopleEl) {
      const roles = [
        ["Gesamtprojektleiter", fieldValue("change_lead", "lead")],
        ["Genehmiger", fieldValue("approver")],
        ["Verantwortlicher FB", fieldValue("fb_owner")],
        ["Verantwortlicher IT", fieldValue("responsible_sit", "it_owner")],
        ["Process Owner (Betrieb FB)", fieldValue("process_owner")],
        ["Solution Owner (Betrieb IT)", fieldValue("solution_owner")],
      ];
      peopleEl.innerHTML = `<h2>Beteiligung und Tandem</h2><dl class="su-roles">${roles
        .map(
          ([label, name]) =>
            `<div><dt>${esc(label)}</dt><dd>${esc(name || "—")}</dd></div>`
        )
        .join("")}</dl>`;
    }
    const lock = viewingId ? " disabled" : "";
    const miles = mileRows(now);
    const fbPlan = scsPlan();
    const itPlanPt = itPlan();
    const sachPlan = moneyOrNull(values.material_costs);
    const fbIst = actuals.fb || 0;
    const itIst = actuals.it || 0;
    const sachIst = moneyOrNull(now?.costActualLicense);
    const costKey = costToneFrom(fbPlan, fbIst, itPlanPt, itIst, sachPlan || 0, sachIst);
    const planBox = document.getElementById("su-plan");
    if (planBox) {
      planBox.innerHTML = `
        <header class="su-panel-head">
          <h2>Zeitplan</h2>
          <span class="stand-pill is-${esc(schedule)}" id="su-schedule-pill">${esc(ragLabel(schedule))}</span>
        </header>
        <div class="su-miles">
          ${miles
            .map(
              (row, index) => `<label class="su-mile"><input data-su-key="mile-label-${index}" type="text" value="${esc(row.label)}" placeholder="M${index + 1}"${lock} /><input data-su-key="mile-state-${index}" type="text" value="${esc(row.state)}" placeholder="Stand"${lock} /></label>`
            )
            .join("")}
        </div>
        <header class="su-panel-head">
          <h2>Kosten</h2>
          <span class="stand-pill is-${esc(costKey)}" id="su-cost-pill">${esc(ragLabel(costKey))}</span>
        </header>
        <div class="su-table su-cost">
          <div class="su-row su-head"><span></span><span>Plan</span><span>Ist</span><span>Risiko</span></div>
          <div class="su-row"><span>FB</span><span>${esc(fbPlan ? `${fmtPt(fbPlan)} PT` : "—")}</span><span class="su-ist">${field("pt:FB", fbIst ? `${fmtPt(fbIst)} PT` : "")}</span><span>${esc(riskWord(fbPlan, fbIst))}</span></div>
          <div class="su-row"><span>IT</span><span>${esc(itPlanPt ? `${fmtPt(itPlanPt)} PT` : "—")}</span><span class="su-ist">${field("pt:IT", itIst ? `${fmtPt(itIst)} PT` : "")}</span><span>${esc(riskWord(itPlanPt, itIst))}</span></div>
          <div class="su-row"><span>Sachkosten</span><span>${esc(sachPlan ? fmtEuro(sachPlan) : "—")}</span><span class="su-ist">${field("euro-sach", sachIst ? fmtEuro(sachIst) : "")}</span><span>${esc(riskWord(sachPlan || 0, sachIst))}</span></div>
        </div>`;
    }
    if (depsEl && depsEl.dataset.user !== "1" && document.activeElement !== depsEl) {
      depsEl.value = String(now?.scheduleReason || "");
      depsEl.disabled = Boolean(viewingId);
    }
    board.dataset.signature = signature();
    const known = String(values.risks || values.risks_obstacles || "").trim();
    const savedRisk = String(now?.risks || "").trim();
    const frozen = Boolean(viewingId);
    if (summaryEl && summaryEl.dataset.user !== "1" && document.activeElement !== summaryEl) {
      summaryEl.value = String((frozen ? now?.summary : draft?.summary ?? now?.summary) || "");
    }
    if (decisionsEl && decisionsEl.dataset.user !== "1" && document.activeElement !== decisionsEl) {
      decisionsEl.value = String((frozen ? now?.decisions : draft?.decisions ?? now?.decisions) || "");
    }
    if (frozen || draft) {
      if (risksEl && risksEl.dataset.user !== "1") risksEl.value = savedRisk;
      if (nextEl && nextEl.dataset.user !== "1") nextEl.value = String(now?.nextSteps || "");
    } else {
      if (risksEl && document.activeElement !== risksEl && savedRisk && savedRisk !== known) risksEl.value = savedRisk;
      if (nextEl && document.activeElement !== nextEl && String(now?.nextSteps || "").trim()) {
        nextEl.value = String(now.nextSteps);
      }
    }
    if (summaryEl) summaryEl.disabled = frozen;
    if (decisionsEl) decisionsEl.disabled = frozen;
    if (risksEl) risksEl.disabled = frozen;
    if (nextEl) nextEl.disabled = frozen;
    if (saveBtn) saveBtn.disabled = frozen;
    paintHealth(healthKey(now));
    if (frozenEl) {
      frozenEl.hidden = !frozen;
      frozenEl.textContent = frozen ? `Stand vom ${stamp(now)}` : "";
    }
    renderSnapshots();
    paintPill(document.getElementById("su-status-pill"), viewingId ? healthKey(now) : liveStatus().overall);
    fit(decisionsEl);
    fit(risksEl);
    fit(nextEl);
    fit(depsEl);
  }

  function renderSnapshots() {
    if (!snapEl) return;
    const items = [...updates].sort((a, b) => String(b.createdAt || "").localeCompare(String(a.createdAt || "")));
    const buttons = items
      .map((item, index) => {
        const when = new Date(item.createdAt || item.reportedOn || "");
        const day = Number.isNaN(when.getTime())
          ? stamp(item)
          : when.toLocaleDateString("de-DE", { day: "2-digit", month: "short", year: "numeric" });
        const time = Number.isNaN(when.getTime())
          ? ""
          : when.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
        const older = items[index + 1];
        const delta = diffLine(item, older);
        return `<button type="button" class="su-snap${item.id === viewingId ? " is-on" : ""}" data-snap="${esc(item.id)}"><span class="su-snap-when"><span>${esc(day)}</span><span>${esc(time)}</span></span>${delta ? `<span class="su-snap-delta">${esc(delta)}</span>` : ""}</button>`;
      })
      .join("");
    const nowDelta = diffLine(
      {
        actualEnd: dateIso(read("end")),
        costActualFb: read("euro-fb"),
        costActualIt: read("euro-it"),
        costActualLicense: read("euro-license"),
        overallRag: healthEl?.value,
      },
      items[0]
    );
    snapEl.innerHTML = `<p>Verlauf</p><button type="button" class="su-snap su-snap-now${viewingId ? "" : " is-on"}" data-snap=""><span>Aktueller Stand</span>${nowDelta ? `<span class="su-snap-delta">${esc(nowDelta)}</span>` : ""}</button>${
      buttons || `<p class="su-snap-empty">Noch kein Snapshot.</p>`
    }`;
  }

  function diffLine(newer, older) {
    if (!newer || !older) return "";
    const endNow = dateIso(newer.actualEnd);
    const endWas = dateIso(older.actualEnd);
    const bits = [];
    if (endNow && endWas && endNow !== endWas) {
      const days = Math.round((new Date(endNow) - new Date(endWas)) / 86400000);
      const n = Math.abs(days);
      const word = n === 1 ? "Tag" : "Tage";
      bits.push(days > 0 ? `Ende ${n} ${word} später` : `Ende ${n} ${word} früher`);
    }
    const sumOf = (row) =>
      triple(moneyOrNull(row?.costActualFb), moneyOrNull(row?.costActualIt), moneyOrNull(row?.costActualLicense)).sum || 0;
    const costNow = sumOf(newer);
    const costWas = sumOf(older);
    const plan = triple(moneyOrNull(values.costs), moneyOrNull(values.it_costs), moneyOrNull(values.material_costs)).sum;
    if (costNow && plan != null && costNow > plan + 0.5) bits.push("Kosten über Plan");
    else if (Math.abs(costNow - costWas) > 0.5) bits.push(costNow > costWas ? "Kosten höher" : "Kosten niedriger");
    if (newer.overallRag && newer.overallRag !== older.overallRag) bits.push(ragLabel(newer.overallRag));
    return bits.join(", ");
  }

  function rememberDraft() {
    const base = latest() || {};
    const crew = people();
    draft = {
      ...base,
      actualStart: dateIso(read("start")),
      actualEnd: dateIso(read("end")),
      milestones: collectedMilestones(),
      costActualLicense: read("euro-sach"),
      scheduleReason: depsEl?.value || "",
      summary: summaryEl?.value || "",
      decisions: decisionsEl.value,
      risks: risksEl.value,
      nextSteps: nextEl.value,
      overallRag: healthEl?.value || "green",
      _reasonDraft: read("reason"),
    };
  }

  function healthKey(source) {
    const raw = viewingId
      ? source?.overallRag
      : draft?.overallRag || detail?.standHealth?.key || source?.overallRag;
    const key = String(raw || "green").toLowerCase();
    return HEALTH.has(key) ? key : "green";
  }

  function paintHealth(key) {
    const value = HEALTH.has(key) ? key : "green";
    if (healthEl) {
      healthEl.value = value;
      healthEl.disabled = Boolean(viewingId);
    }
    if (healthWrap) healthWrap.dataset.health = value;
  }

  async function pushHealth(key) {
    if (!id || viewingId) return;
    const value = HEALTH.has(key) ? key : "green";
    paintHealth(value);
    try {
      window.opener?.applyStandHealth?.(id, value);
    } catch {
      /* Ticket-Fenster zu */
    }
    await fetch(`/api/requests/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields: { stand_health: value } }),
    });
  }

  function signature() {
    return [...board.querySelectorAll("[data-su-key]")].map((el) => `${el.dataset.suKey}:${el.value}`).join("\n");
  }

  function fit(el) {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }

  async function save() {
    if (!id || saving || viewingId) return;
    saving = true;
    const now = draft || latest();
    const crew = people();
    const milestones = collectedMilestones();
    const scheduleReason = depsEl?.value.trim() || "";
    const actualEnd = dateIso(read("end"));
    const planEnd = dateIso(values.end || values.end_date);
    const planPt = crew.reduce((sum, row) => sum + row.plan, 0);
    const usedPt = milestones.reduce((sum, row) => sum + parsePt(row.actual), 0);
    const istEuro = triple(moneyOrNull(read("euro-fb")), moneyOrNull(read("euro-it")), moneyOrNull(read("euro-license")));
    const planEuro = triple(moneyOrNull(values.costs), moneyOrNull(values.it_costs), moneyOrNull(values.material_costs));
    const payload = {
      reportedOn: new Date().toISOString().slice(0, 10),
      planStart: dateIso(values.start || values.start_date),
      planEnd,
      actualStart: dateIso(read("start")),
      actualEnd,
      milestones,
      costActualFb: "",
      costActualIt: "",
      costActualLicense: read("euro-sach"),
      scheduleReason,
      scheduleRag: rag(planEnd, actualEnd, planPt, usedPt, Boolean(read("start") || read("end") || usedPt)),
      costRag: costRag(planEuro, istEuro),
      decisions: decisionsEl.value.trim(),
      risks: risksEl.value.trim(),
      nextSteps: nextEl.value.trim(),
      overallRag: healthEl?.value || "green",
      summary: summaryEl?.value.trim() || "",
    };
    let response;
    try {
      response = await fetch(`/api/requests/${id}/status-updates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch {
      saving = false;
      errorEl.hidden = false;
      return;
    }
    saving = false;
    if (!response.ok) {
      errorEl.hidden = false;
      return;
    }
    errorEl.hidden = true;
    const saved = await response.json();
    const idx = updates.findIndex((item) => item.id === saved.id);
    if (idx >= 0) updates[idx] = saved;
    else updates.push(saved);
    if (summaryEl) {
      summaryEl.dataset.dirty = "";
      summaryEl.dataset.user = "";
    }
    if (decisionsEl) {
      decisionsEl.dataset.dirty = "";
      decisionsEl.dataset.user = "";
    }
    if (risksEl) risksEl.dataset.dirty = "";
    if (nextEl) nextEl.dataset.dirty = "";
    if (healthEl) healthEl.dataset.dirty = "";
    draft = null;
    viewingId = "";
    render();
  }

  async function fillRisks() {
    const response = await fetch(`/api/requests/${id}/status-risks`, { method: "POST" });
    if (!response.ok || risksEl.dataset.dirty === "1") return;
    const data = await response.json();
    risksEl.value = String(data.risks || "").trim();
    if (risksEl.value) risksEl.dataset.dirty = "1";
    fit(risksEl);
  }

  async function fillNext() {
    const list = [...comments].filter((row) => String(row.body || "").trim().length > 2);
    list.sort((a, b) => String(a.createdAt || "").localeCompare(String(b.createdAt || "")));
    const body = String((list.length ? list[list.length - 1].body : "") || "")
      .replace(/\s+/g, " ")
      .trim();
    const match = body.match(/\b((?:es |man )?muss\b.+)$/i);
    let local = (match ? match[1] : body).trim();
    if (local && local[0] === local[0].toLowerCase()) local = local[0].toUpperCase() + local.slice(1);
    if (local && !/[.!?]$/.test(local)) local += ".";
    if (local) {
      nextEl.value = local;
      fit(nextEl);
    }
    const response = await fetch(`/api/requests/${id}/next-steps`, { method: "POST" });
    if (!response.ok) {
      if (local) nextEl.dataset.dirty = "1";
      return;
    }
    if (nextEl.dataset.dirty === "1") return;
    const data = await response.json();
    const text = String(data.nextSteps || "").trim();
    if (text) {
      nextEl.value = text;
      nextEl.dataset.dirty = "1";
      fit(nextEl);
    }
  }

  for (const el of [depsEl, decisionsEl, risksEl, nextEl]) {
    if (!el) continue;
    el.addEventListener("input", () => {
      el.dataset.dirty = "1";
      el.dataset.user = "1";
      if ((el === decisionsEl || el === summaryEl) && viewingId) {
        viewingId = "";
        if (saveBtn) saveBtn.disabled = false;
        if (frozenEl) frozenEl.hidden = true;
      }
      fit(el);
    });
  }
  saveBtn?.addEventListener("click", () => void save());
  document.getElementById("su-back")?.addEventListener("click", () => {
    if (window.opener && !window.opener.closed) {
      window.close();
      return;
    }
    location.href = id ? `/workspace/${encodeURIComponent(id)}` : "/workspace";
  });
  board.addEventListener("input", () => applyLiveHealth());
  healthEl?.addEventListener("change", () => {
    healthEl.dataset.dirty = "1";
    void pushHealth(healthEl.value);
  });
  snapEl?.addEventListener("click", (ev) => {
    const button = ev.target.closest("[data-snap]");
    if (!button || button.disabled) return;
    const nextId = button.dataset.snap || "";
    if (!viewingId && nextId) rememberDraft();
    viewingId = nextId;
    render();
  });

  async function boot() {
    if (!id) {
      board.textContent = "Kein Ticket.";
      return;
    }
    const response = await fetch(`/api/requests/${id}`);
    if (!response.ok) {
      board.textContent = "Ticket nicht geladen.";
      return;
    }
    detail = await response.json();
    values = Object.fromEntries((detail.fields || []).map((fieldRow) => [fieldRow.key, fieldRow.value || ""]));
    updates = Array.isArray(detail.statusUpdates) ? detail.statusUpdates : [];
    comments = Array.isArray(detail.comments) ? detail.comments : [];
    const lead = document.getElementById("su-lead");
    if (lead) lead.textContent = "Plan, Ist und Freitext zum aktuellen Stand.";
    render();
  }

  void boot();
})();
