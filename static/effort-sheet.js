(function () {
  const TYPE = "critr-effort-sheet-v1";
  const SHARE =
    new URLSearchParams(location.search).get("share") ||
    (location.pathname.match(/\/aufwand\/([0-9a-fA-F-]{36})/i) || [])[1] ||
    "";
  const host = document.getElementById("kalk");
  if (!host) return;

  const SCS_RATE = 750;
  const CIT_RATE = 665;
  const CIT_OH = 0.1544;
  const CIT_PROFIT = 0.05;
  const EMPTY = 4;

  const BLOCKS = [
    {
      id: "concept-scs",
      phase: "konzeption",
      rolle: "scs",
      title: "Konzeption & Einführung — SCS",
      hint: "SCS-Satz; gilt auch für andere Schwarz-Gruppen (ohne CIT). Sachkosten netto.",
      rate: SCS_RATE,
      cit: false,
    },
    {
      id: "concept-cit",
      phase: "konzeption",
      rolle: "cit",
      title: "Konzeption & Einführung — CIT",
      hint: "Nur von CIT auszufüllen (kalkulieren). Sachkosten netto.",
      rate: CIT_RATE,
      cit: true,
    },
    {
      id: "operate-scs",
      phase: "betrieb",
      rolle: "scs",
      title: "Betrieb — SCS",
      hint: "SCS-Satz; gilt auch für andere Schwarz-Gruppen (ohne CIT). Sachkosten netto.",
      rate: SCS_RATE,
      cit: false,
    },
    {
      id: "operate-cit",
      phase: "betrieb",
      rolle: "cit",
      title: "Betrieb — CIT",
      hint: "Nur von CIT auszufüllen (kalkulieren). Sachkosten netto.",
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

  function euro(n) {
    return `${n.toFixed(2).replace(".", ",")} €`;
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
    const pt = rowsOf(block, "pt").reduce((sum, tr) => sum + parseNum(lineValues(tr).menge), 0);
    const sach = rowsOf(block, "sach").reduce((sum, tr) => sum + parseNum(lineValues(tr).menge), 0);
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
        spec.phase === "betrieb" ? "Betriebs-Phase" : "Konzeptions & Einführungs-Phase";
      if (index === 0 || spec.phase === "betrieb") lines.push(row([phaseTitle, "", "", ""]));
      lines.push(row([spec.cit ? "Kalkulation IT" : "Kalkulation SCS + andere Schwarz-Gruppen", "", "", ""]));
      lines.push(row(["", "", "", ""]));
      lines.push(row([pt || "", "Gesamt-Personentage (Summe aus der PT-Aufschlüsselung)", "", ""]));
      lines.push(row(["", "", "", ""]));
      lines.push(row(["Personentage", "Aufschlüsselung / Beschreibung", "", ""]));
      padLines(rowsOf(block, "pt").map(lineValues)).forEach((item) => {
        lines.push(row([item.menge, item.beschreibung, "", ""]));
      });
      lines.push(row(["", "", "", ""]));
      lines.push(row(["Sach-/Lizenzkosten", "Aufschlüsselung / Beschreibung", "", ""]));
      padLines(rowsOf(block, "sach").map(lineValues)).forEach((item) => {
        lines.push(row([item.menge, item.beschreibung, "", ""]));
      });
      lines.push(row(["", "", "", ""]));
      if (spec.cit) {
        lines.push(row(["Kosten-Kalkulation IT", "Sätze", "Teilsummen", "Berechnungen"]));
        lines.push(row(["Tagessatz PT", `${de(CIT_RATE)} €`, "", ""]));
        lines.push(row(["Freigegebene PT", String(pt || ""), "", ""]));
        lines.push(row(["Summe PT Netto", "", "", `${de(laborNet)} €`]));
        lines.push(row(["+ Gemeinkosten %", "15,44", "", `${de(oh)} €`]));
        lines.push(row(["+ Gewinnzuschlag %", "5,00", "", `${de(profit)} €`]));
        lines.push(row(["Sachkosten Summe", "", "", `${de(sach)} €`]));
        lines.push(row(["Summe Brutto", "", "", `${de(brutto)} €`]));
      } else {
        lines.push(row(["Kosten-Kalkulation", "Sätze", "Teilsummen", "Berechnungen"]));
        lines.push(row(["Tarifsatz (SCS)", "750,00", "", `${de(laborNet)} €`]));
        lines.push(row(["+ Sach-/Lizenzkosten", de(sach), "", `${de(sach)} €`]));
        lines.push(row(["+ Sonstiges", "0,00", "", "0,00 €"]));
        lines.push(row(["Summe Brutto", "", "", `${de(brutto)} €`]));
      }
      lines.push(row(["", "", "", ""]));
    });
    return `\uFEFF${lines.join("\r\n")}`;
  }

  async function downloadExcel() {
    const csv = toCsv();
    if (SHARE) {
      location.href = `/aufwand/${SHARE}/xlsx`;
      return;
    }
    const res = await fetch("/api/sessions/effort-sheet/xlsx", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csv }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href;
    a.download = "kalkulation.xlsx";
    a.click();
    URL.revokeObjectURL(href);
  }

  let dirty = false;

  function flush() {
    renderTotals();
    if (!dirty) return;
    const csv = toCsv();
    if (window.opener && !window.opener.closed) {
      window.opener.postMessage({ type: TYPE, csv }, window.location.origin);
    }
  }

  function addLine(tbody, values) {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td contenteditable="true" data-col="menge">${values?.menge || ""}</td>` +
      `<td contenteditable="true" data-col="beschreibung">${values?.beschreibung || ""}</td>`;
    tbody.appendChild(tr);
  }

  function table(art, qtyLabel) {
    const wrap = document.createElement("div");
    wrap.className = "kalk-table";
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
      section.innerHTML =
        `<header>` +
        `<div><p class="kalk-phase">${phase}</p><h2>${spec.cit ? "Kalkulation IT" : 'Kalkulation SCS <span class="kalk-plus">+ andere Schwarz-Gruppen</span>'}</h2></div>` +
        `<span class="kalk-badge">${spec.cit ? "CIT" : "SCS"}</span>` +
        `</header>` +
        `<p class="kalk-rate">${spec.hint}<br>Satz ${spec.rate.toLocaleString("de-DE")} € / PT` +
        (spec.cit ? ` · Gemeinkosten ${(CIT_OH * 100).toLocaleString("de-DE")} % · Gewinn ${(CIT_PROFIT * 100).toLocaleString("de-DE")} %` : "") +
        `</p>`;
      const pt = table("pt", "Personentage");
      const sach = table("sach", "Sach-/Lizenzkosten");
      section.appendChild(pt);
      section.appendChild(sach);
      const foot = document.createElement("dl");
      foot.className = "kalk-totals";
      foot.innerHTML =
        `<div><dt>Gesamt-PT</dt><dd data-total="pt">0</dd></div>` +
        `<div><dt>Sachkosten netto</dt><dd data-total="sach">0,00 €</dd></div>` +
        `<div><dt>Summe Brutto</dt><dd data-total="brutto">0,00 €</dd></div>`;
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
    const skip = /^(personentage|sach-|kosten-kalkulation|gesamt-|tarifsatz|tagessatz|freigegebene|summe |gemeinkosten|gewinn|sachkosten summe|\+ )/i;
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
      if (skip.test(first) || /bitte trage/i.test(cols[1] || "")) return;
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

  host.addEventListener("input", () => {
    dirty = true;
    flush();
  });
  window.addEventListener("pagehide", flush);
  window.addEventListener("beforeunload", flush);
  document.getElementById("kalk-csv")?.addEventListener("click", () => {
    void downloadExcel();
  });
  document.getElementById("kalk-save")?.addEventListener("click", () => {
    dirty = true;
    flush();
    window.close();
  });

  async function boot() {
    if (!SHARE) {
      paint({});
      renderTotals();
      return;
    }
    try {
      const r = await fetch(`/aufwand/${SHARE}/data`);
      const csv = r.ok ? await r.text() : "";
      paint(fromCsv(csv) || {});
    } catch {
      paint({});
    }
    renderTotals();
  }

  boot();
})();
