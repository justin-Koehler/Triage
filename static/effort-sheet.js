(function () {
  const TYPE = "critr-effort-sheet-v1";
  const PARAMS = new URLSearchParams(location.search);
  const SHARE =
    PARAMS.get("share") ||
    (location.pathname.match(/\/aufwand\/([0-9a-fA-F-]{36})/i) || [])[1] ||
    "";
  const host = document.getElementById("kalk");
  if (!host) return;

  // Zeigt, zu welchem Change diese Kalkulation gehört.
  const forEl = document.getElementById("kalk-for");
  const forTitle = String(PARAMS.get("for") || "").trim();
  if (forEl && forTitle) forEl.textContent = forTitle;

  function showIssueKey(key, url) {
    const box = document.getElementById("kalk-key");
    const link = document.getElementById("kalk-key-link");
    const sep = document.getElementById("kalk-key-sep");
    const issue = String(key || "").trim();
    if (!box || !link) return;
    if (!/^[A-Z][A-Z0-9]+-\d+$/i.test(issue)) {
      box.hidden = true;
      if (sep) sep.hidden = true;
      return;
    }
    box.hidden = false;
    if (sep) sep.hidden = false;
    link.textContent = issue;
    const raw = String(url || "").trim();
    link.href = !raw || /live\.api\.schwarz/i.test(raw) ? `https://jira.schwarz/browse/${issue}` : raw;
    link.title = `In Jira öffnen: ${issue}`;
  }

  showIssueKey(PARAMS.get("key"), "");

  const HOURS_PER_PT = 8;
  const MINUTES_PER_PT = HOURS_PER_PT * 60;
  const USD_PER_EUR_FALLBACK = 1.1234;
  let usdPerEur = USD_PER_EUR_FALLBACK;
  const SCS_RATE = 750;
  const CIT_RATE = 665;
  const CIT_OH = 0.1544;
  const CIT_PROFIT = 0.05;
  const EMPTY = 4;

  const SCS_TITLE = "Kalkulation SCS";
  const SCS_EXTRA = "inklusive weiterer Schwarzfirmen";
  const CIT_TITLE = "Kalkulation IT";

  const BLOCKS = [
    {
      id: "concept-scs",
      phase: "konzeption",
      rolle: "scs",
      title: "Konzeption & Einführung — SCS",
      hint: "",
      rate: SCS_RATE,
      cit: false,
    },
    {
      id: "concept-cit",
      phase: "konzeption",
      rolle: "cit",
      title: "Konzeption & Einführung — CIT",
      hint: "Nur von CIT auszufüllen.",
      rate: CIT_RATE,
      cit: true,
    },
    {
      id: "operate-scs",
      phase: "betrieb",
      rolle: "scs",
      title: "Betrieb — SCS",
      hint: "",
      rate: SCS_RATE,
      cit: false,
    },
    {
      id: "operate-cit",
      phase: "betrieb",
      rolle: "cit",
      title: "Betrieb — CIT",
      hint: "Nur von CIT auszufüllen.",
      rate: CIT_RATE,
      cit: true,
    },
  ];

  function parseNum(text) {
    const match = String(text || "")
      .replace(/\s/g, "")
      .replace(",", ".")
      .match(/-?\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : 0;
  }

  function formatPt(n) {
    const rounded = Math.round((Number(n) + Number.EPSILON) * 100) / 100;
    return rounded
      .toFixed(2)
      .replace(".", ",")
      .replace(/,00$/, "")
      .replace(/,(\d)0$/, ",$1");
  }

  function perPt(unit) {
    if (unit === "min") return MINUTES_PER_PT;
    if (unit === "h") return HOURS_PER_PT;
    return 1;
  }

  function lineMoney(tr) {
    const n = parseNum(lineValues(tr).menge);
    return tr.querySelector("[data-ccy]")?.value === "usd" ? n / usdPerEur : n;
  }

  function linePt(tr) {
    const n = parseNum(lineValues(tr).menge);
    const unit = tr.querySelector("[data-unit]")?.value || "pt";
    return unit === "pt" ? n : n / perPt(unit);
  }

  function settleUnits(root) {
    const boxes =
      root?.classList?.contains("kalk-qty")
        ? [root]
        : [...(root || host).querySelectorAll(".kalk-qty")];
    boxes.forEach((qty) => {
      const unit = qty.querySelector("[data-unit]");
      const cell = qty.querySelector("[data-col=menge]");
      if (!unit || unit.value === "pt" || !cell) return;
      const raw = cell.innerText.trim();
      if (!raw) return;
      cell.textContent = formatPt(parseNum(raw) / perPt(unit.value));
      unit.value = "pt";
    });
  }

  function settleCurrency(root) {
    const boxes =
      root?.classList?.contains("kalk-qty")
        ? [root]
        : [...(root || host).querySelectorAll(".kalk-qty")];
    boxes.forEach((qty) => {
      const ccy = qty.querySelector("[data-ccy]");
      const cell = qty.querySelector("[data-col=menge]");
      if (!ccy || ccy.value !== "usd" || !cell) return;
      const raw = cell.innerText.trim();
      if (!raw) return;
      cell.textContent = formatMoney(parseNum(raw) / usdPerEur);
      ccy.value = "eur";
    });
  }

  function csvCell(value) {
    const text = String(value ?? "");
    if (/[";\n]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
    return text;
  }

  function de(value, digits = 2) {
    return Number(value || 0).toFixed(digits).replace(".", ",");
  }

  function parseCsv(text) {
    const blob = String(text || "").replace(/^\uFEFF/, "");
    const sample = blob.slice(0, 400);
    const delim = (sample.match(/;/g) || []).length >= (sample.match(/,/g) || []).length ? ";" : ",";
    return blob
      .trim()
      .split(/\r?\n/)
      .filter((line) => line.length)
      .map((line) => {
        const out = [];
        let cur = "";
        let quoted = false;
        for (let i = 0; i < line.length; i += 1) {
          const ch = line[i];
          if (quoted) {
            if (ch === '"' && line[i + 1] === '"') {
              cur += '"';
              i += 1;
            } else if (ch === '"') quoted = false;
            else cur += ch;
          } else if (ch === '"') quoted = true;
          else if (ch === delim) {
            out.push(cur);
            cur = "";
          } else cur += ch;
        }
        out.push(cur);
        return out;
      });
  }

  function formatMoney(n) {
    const rounded = Math.round((Number(n) + Number.EPSILON) * 100) / 100;
    return rounded.toFixed(2).replace(".", ",");
  }

  function euro(n) {
    return `${formatMoney(n)} €`;
  }

  function moneyTitle() {
    return `Ohne Wahl sind es Euro. 1 € = ${usdPerEur.toFixed(4).replace(".", ",")} $.`;
  }

  function rowsOf(block, art) {
    return [...block.querySelectorAll(`tbody[data-art="${art}"] tr`)];
  }

  function lineValues(tr) {
    const cells = [...tr.querySelectorAll("[data-col]")];
    return {
      menge: cells.find((c) => c.dataset.col === "menge")?.innerText.trim() || "",
      beschreibung: cells.find((c) => c.dataset.col === "beschreibung")?.innerText.trim() || "",
    };
  }

  function bruttoFor(block, spec) {
    const pt = rowsOf(block, "pt").reduce((sum, tr) => sum + linePt(tr), 0);
    const sach = rowsOf(block, "sach").reduce((sum, tr) => sum + lineMoney(tr), 0);
    let labor = pt * spec.rate;
    if (spec.cit) labor = labor * (1 + CIT_OH) * (1 + CIT_PROFIT);
    return { pt, sach, brutto: labor + sach };
  }

  function renderTotals() {
    BLOCKS.forEach((spec) => {
      const block = host.querySelector(`[data-block="${spec.id}"]`);
      if (!block) return;
      const { pt, sach, brutto } = bruttoFor(block, spec);
      block.querySelector("[data-total=pt]").textContent = String(pt || 0).replace(".", ",");
      block.querySelector("[data-total=sach]").textContent = euro(sach);
      block.querySelector("[data-total=brutto]").textContent = euro(brutto);
    });
  }

  function row(cols) {
    return cols.map(csvCell).join(";");
  }

  function padLines(values) {
    const filled = values.filter((v) => v.menge || v.beschreibung);
    while (filled.length < EMPTY) filled.push({ menge: "", beschreibung: "" });
    return filled;
  }

  function toCsv() {
    const lines = [];
    BLOCKS.forEach((spec, index) => {
      const block = host.querySelector(`[data-block="${spec.id}"]`);
      if (!block) return;
      const { pt, sach, brutto } = bruttoFor(block, spec);
      const laborNet = pt * spec.rate;
      const oh = spec.cit ? laborNet * CIT_OH : 0;
      const profit = spec.cit ? (laborNet + oh) * CIT_PROFIT : 0;
      const phaseTitle =
        spec.phase === "betrieb" ? "Betrieb" : "Konzeption & Einführung";
      if (index === 0 || spec.phase === "betrieb") lines.push(row([phaseTitle, "", "", ""]));
      lines.push(
        row([spec.cit ? CIT_TITLE : `${SCS_TITLE} ${SCS_EXTRA}`, "", "", ""])
      );
      lines.push(row(["", "", "", ""]));
      lines.push(row([pt || "", "Gesamt Personentage", "", ""]));
      lines.push(row(["", "", "", ""]));
      lines.push(row(["Personentage", "Aufschlüsselung / Beschreibung", "", ""]));
      padLines(rowsOf(block, "pt").map((tr) => {
        const item = lineValues(tr);
        const unit = tr.querySelector("[data-unit]")?.value;
        if (unit && unit !== "pt" && item.menge) {
          item.menge = formatPt(parseNum(item.menge) / perPt(unit));
        }
        return item;
      })).forEach((item) => {
        lines.push(row([item.menge, item.beschreibung, "", ""]));
      });
      lines.push(row(["", "", "", ""]));
      lines.push(row(["Sach-/Lizenzkosten", "Aufschlüsselung / Beschreibung", "", ""]));
      padLines(rowsOf(block, "sach").map((tr) => {
        const item = lineValues(tr);
        if (tr.querySelector("[data-ccy]")?.value === "usd" && item.menge) {
          item.menge = formatMoney(parseNum(item.menge) / usdPerEur);
        }
        return item;
      })).forEach((item) => {
        lines.push(row([item.menge, item.beschreibung, "", ""]));
      });
      lines.push(row(["", "", "", ""]));
      if (spec.cit) {
        lines.push(row(["Kosten-Kalkulation IT", "Sätze", "Teilsummen", "Berechnungen"]));
        lines.push(row(["Tagessatz PT", `${de(CIT_RATE)} €`, "", ""]));
        lines.push(row(["Freigegebene PT", String(pt || ""), "", ""]));
        lines.push(row(["Gesamt Personentage", "", "", `${de(laborNet)} €`]));
        lines.push(row(["+ Gemeinkosten %", "15,44", "", `${de(oh)} €`]));
        lines.push(row(["+ Gewinnzuschlag %", "5,00", "", `${de(profit)} €`]));
        lines.push(row(["Summe Sachkosten", "", "", `${de(sach)} €`]));
        lines.push(row(["Gesamtsumme", "", "", `${de(brutto)} €`]));
      } else {
        lines.push(row(["Kosten-Kalkulation", "Sätze", "Teilsummen", "Berechnungen"]));
        lines.push(row(["Tarifsatz (SCS)", "750,00", "", `${de(laborNet)} €`]));
        lines.push(row(["+ Sach-/Lizenzkosten", de(sach), "", `${de(sach)} €`]));
        lines.push(row(["+ Sonstiges", "0,00", "", "0,00 €"]));
        lines.push(row(["Gesamtsumme", "", "", `${de(brutto)} €`]));
      }
      lines.push(row(["", "", "", ""]));
    });
    return `\uFEFF${lines.join("\r\n")}`;
  }

  let dirty = false;
  let saveTimer = 0;
  let saving = false;

  async function persistShare(csv) {
    if (!SHARE) return;
    try {
      const r = await fetch(`/aufwand/${SHARE}`, {
        method: "PUT",
        headers: { "Content-Type": "text/csv; charset=utf-8" },
        body: csv,
      });
      if (!r.ok) throw new Error("save failed");
    } catch (_) {
      /* offline / kurzzeitig — nächster flush versucht erneut */
      dirty = true;
    }
  }

  function flush() {
    renderTotals();
    if (!dirty) return;
    const csv = toCsv();
    if (window.opener && !window.opener.closed) {
      window.opener.postMessage({ type: TYPE, csv }, window.location.origin);
    }
    if (!SHARE) {
      dirty = false;
      return;
    }
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => {
      if (saving) return;
      saving = true;
      dirty = false;
      void persistShare(csv).finally(() => {
        saving = false;
      });
    }, 700);
  }

  function addLine(tbody, values) {
    const tr = document.createElement("tr");
    const menge = values?.menge || "";
    if (tbody.dataset.art === "pt") {
      tr.innerHTML =
        `<td class="kalk-qty">` +
        `<span contenteditable="true" data-col="menge">${menge}</span>` +
        `<select data-unit aria-label="Einheit" title="Ohne Wahl sind es Personentage. 1 PT = 8 Stunden.">` +
        `<option value="pt" selected>PT</option>` +
        `<option value="h">h</option>` +
        `<option value="min">min</option>` +
        `</select></td>` +
        `<td contenteditable="true" data-col="beschreibung">${values?.beschreibung || ""}</td>`;
    } else {
      tr.innerHTML =
        `<td class="kalk-qty">` +
        `<span contenteditable="true" data-col="menge">${menge}</span>` +
        `<select data-ccy aria-label="Währung" title="${moneyTitle()}">` +
        `<option value="eur" selected>€</option>` +
        `<option value="usd">$</option>` +
        `</select></td>` +
        `<td contenteditable="true" data-col="beschreibung">${values?.beschreibung || ""}</td>`;
    }
    tbody.appendChild(tr);
  }

  function table(art, qtyLabel) {
    const wrap = document.createElement("div");
    wrap.className = art === "pt" ? "kalk-table is-pt" : "kalk-table is-money";
    wrap.innerHTML =
      `<table><thead><tr><th>${qtyLabel}</th><th>Aufschlüsselung / Beschreibung</th></tr></thead>` +
      `<tbody data-art="${art}"></tbody>` +
      `<tfoot><tr><td colspan="2"><button type="button" class="kalk-add" data-add="${art}">+ Zeile hinzufügen</button></td></tr></tfoot></table>`;
    return wrap;
  }

  function paint(data) {
    host.innerHTML = "";
    BLOCKS.forEach((spec) => {
      const section = document.createElement("section");
      section.className = `kalk-block ${spec.cit ? "is-cit" : "is-scs"}`;
      section.dataset.block = spec.id;
      const phase = spec.phase === "betrieb" ? "Betrieb" : "Konzeption & Einführung";
      const title = spec.cit
        ? CIT_TITLE
        : `${SCS_TITLE} <span class="kalk-plus">${SCS_EXTRA}</span>`;
      section.innerHTML =
        `<header>` +
        `<div class="kalk-head"><p class="kalk-phase">${phase}</p><h2>${title}</h2></div>` +
        `<span class="kalk-badge">${spec.cit ? "CIT" : "SCS"}</span>` +
        `</header>` +
        `<p class="kalk-rate">${spec.hint ? `${spec.hint}<br>` : ""}Satz ${spec.rate.toLocaleString("de-DE")} € / PT` +
        (spec.cit ? ` · Gemeinkosten ${(CIT_OH * 100).toLocaleString("de-DE")} % · Gewinn ${(CIT_PROFIT * 100).toLocaleString("de-DE")} %` : "") +
        `</p>`;
      const pt = table("pt", "Personentage");
      const sach = table("sach", "Sach-/Lizenzkosten");
      section.appendChild(pt);
      section.appendChild(sach);
      const foot = document.createElement("dl");
      foot.className = "kalk-totals";
      foot.innerHTML =
        `<div><dt>Gesamt Personentage</dt><dd data-total="pt">0</dd></div>` +
        `<div><dt>Summe Sachkosten</dt><dd data-total="sach">0,00 €</dd></div>` +
        `<div class="is-sum"><dt>Gesamtsumme</dt><dd data-total="brutto">0,00 €</dd></div>`;
      section.appendChild(foot);
      host.appendChild(section);
      const ptBody = pt.querySelector("tbody");
      const sachBody = sach.querySelector("tbody");
      const seeded = (data[spec.id] || { pt: [], sach: [] });
      const ptRows = seeded.pt.length ? seeded.pt : Array.from({ length: EMPTY }, () => ({}));
      const sachRows = seeded.sach.length ? seeded.sach : Array.from({ length: EMPTY }, () => ({}));
      ptRows.forEach((row) => addLine(ptBody, row));
      sachRows.forEach((row) => addLine(sachBody, row));
    });
    renderTotals();
  }

  function emptyData() {
    const data = {};
    BLOCKS.forEach((spec) => {
      data[spec.id] = { pt: [], sach: [] };
    });
    return data;
  }

  function fromCsv(text) {
    const rows = parseCsv(text);
    const head = (rows[0] || []).map((h) => h.toLowerCase());
    const data = emptyData();
    if (head.includes("art") && head.includes("phase")) {
      const idx = Object.fromEntries(head.map((name, i) => [name, i]));
      rows.slice(1).forEach((row) => {
        const phase = String(row[idx.phase] || "").toLowerCase();
        const rolle = String(row[idx.rolle] || "").toLowerCase();
        const art = String(row[idx.art] || "").toLowerCase();
        const spec = BLOCKS.find((b) => phase.includes(b.phase.slice(0, 7)) && rolle.includes(b.rolle));
        if (!spec || (art !== "pt" && art !== "sach")) return;
        data[spec.id][art].push({
          menge: row[idx.menge] || "",
          beschreibung: row[idx.beschreibung] || "",
        });
      });
      return data;
    }
    const blob = rows.map((r) => r.join(" ")).join(" ").toLowerCase();
    if (!blob.includes("kalkulation") || !blob.includes("personentage")) return null;
    let phase = "konzeption";
    let rolle = "scs";
    let mode = "";
    const skip = /^(personentage|sach-|kosten-kalkulation|gesamt|tarifsatz|tagessatz|freigegebene|summe |gemeinkosten|gewinn|sachkosten summe|\+ )/i;
    rows.forEach((cols) => {
      const first = String(cols[0] || "").trim();
      const joined = cols.join(" ").toLowerCase();
      if (/betriebs-phase|^betrieb\b/i.test(joined)) phase = "betrieb";
      else if (/konzeption/i.test(joined)) phase = "konzeption";
      if (/^kalkulation it/i.test(first)) {
        rolle = "cit";
        return;
      }
      if (/^kalkulation scs/i.test(first)) {
        rolle = "scs";
        return;
      }
      if (/^personentage/i.test(first)) {
        mode = "pt";
        return;
      }
      if (/^sach-?\/?lizenz/i.test(first)) {
        mode = "sach";
        return;
      }
      if (/^kosten-kalkulation/i.test(first) || /^(tarifsatz|tagessatz pt)/i.test(first)) {
        mode = "calc";
        return;
      }
      if (mode !== "pt" && mode !== "sach") return;
      if (!first && !cols[1]) return;
      if (skip.test(first) || /bitte trage|^gesamt(summe|[- ]?pt| personentage)/i.test(cols[1] || "")) return;
      const spec = BLOCKS.find((b) => b.phase === phase && b.rolle === rolle);
      if (!spec) return;
      data[spec.id][mode].push({ menge: first, beschreibung: cols[1] || "" });
    });
    return data;
  }

  host.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-add]");
    if (!btn) return;
    const tbody = btn.closest("table")?.querySelector(`tbody[data-art="${btn.dataset.add}"]`);
    if (!tbody) return;
    addLine(tbody, {});
    tbody.querySelector("tr:last-child [data-col=menge]")?.focus();
    dirty = true;
    flush();
  });

  function leaveMinuteFields(target) {
    let changed = false;
    host.querySelectorAll(".kalk-qty").forEach((qty) => {
      if (target && qty.contains(target)) return;
      const unit = qty.querySelector("[data-unit]");
      const cell = qty.querySelector("[data-col=menge]");
      const ccy = qty.querySelector("[data-ccy]");
      if (!cell?.innerText.trim()) return;
      if (unit?.value === "pt" && ccy?.value !== "usd") return;
      if (!unit && ccy?.value !== "usd") return;
      const before = cell.textContent;
      if (unit && unit.value !== "pt") settleUnits(qty);
      if (ccy?.value === "usd") settleCurrency(qty);
      if (cell.textContent !== before) changed = true;
    });
    if (!changed) return;
    dirty = true;
    renderTotals();
    flush();
  }

  host.addEventListener("focusout", (event) => {
    const qty = event.target.closest(".kalk-qty");
    if (!qty || (event.relatedTarget && qty.contains(event.relatedTarget))) return;
    leaveMinuteFields(event.relatedTarget);
  });

  document.addEventListener("pointerdown", (event) => {
    leaveMinuteFields(event.target);
  });

  host.addEventListener("input", () => {
    dirty = true;
    renderTotals();
    flush();
  });
  window.addEventListener("pagehide", () => {
    settleUnits();
    settleCurrency();
    dirty = true;
    flush();
  });
  window.addEventListener("beforeunload", () => {
    settleUnits();
    settleCurrency();
    dirty = true;
    flush();
  });
  document.getElementById("kalk-save")?.addEventListener("click", () => {
    settleUnits();
    settleCurrency();
    dirty = true;
    flush();
    window.close();
  });
  document.getElementById("kalk-back")?.addEventListener("click", () => {
    if (window.opener && !window.opener.closed) {
      window.close();
      return;
    }
    location.href = "/workspace";
  });

  function loadRate() {
    fetch("https://api.frankfurter.app/latest?from=EUR&to=USD")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        const rate = Number(data?.rates?.USD);
        if (!Number.isFinite(rate) || rate <= 0) return;
        usdPerEur = rate;
        host.querySelectorAll("[data-ccy]").forEach((el) => {
          el.title = moneyTitle();
        });
        renderTotals();
      })
      .catch(() => {});
  }

  async function boot() {
    if (!SHARE) {
      paint({});
    } else {
      try {
        const r = await fetch(`/aufwand/${SHARE}/data`);
        const csv = r.ok ? await r.text() : "";
        paint(fromCsv(csv) || {});
        const meta = await fetch(`/aufwand/${SHARE}/meta`).then((res) => (res.ok ? res.json() : {}));
        if (meta.key) showIssueKey(meta.key, meta.url);
        if (forEl && !forTitle && meta.title) forEl.textContent = meta.title;
      } catch {
        paint({});
      }
    }
    renderTotals();
    loadRate();
  }

  boot();
})();
