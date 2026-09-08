(function () {
  const KEY = "critr-effort-sheet-draft";
  const TYPE = "critr-effort-sheet-v1";
  const grid = document.getElementById("grid");
  const addBtn = document.getElementById("add-row");
  if (!grid) return;

  let headers = [];

  function parseCsv(text) {
    return String(text || "")
      .replace(/^\uFEFF/, "")
      .trim()
      .split(/\r?\n/)
      .filter(Boolean)
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
          else if (ch === ",") {
            out.push(cur);
            cur = "";
          } else cur += ch;
        }
        out.push(cur);
        return out;
      });
  }

  function csvCell(value) {
    const text = String(value || "");
    if (/[",\n]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
    return text;
  }

  function dataCells(tr) {
    return [...tr.querySelectorAll("td")].filter((cell) => !cell.classList.contains("effort-row-num"));
  }

  function toCsv() {
    const head = headers.map((name) => csvCell(name)).join(",");
    const body = [...grid.querySelectorAll("tbody tr")].map((tr) =>
      dataCells(tr)
        .map((cell) => csvCell(cell.innerText.trim()))
        .join(",")
    );
    return [head, ...body].join("\n");
  }

  function parseNum(text) {
    const match = String(text || "")
      .replace(",", ".")
      .match(/-?\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : 0;
  }

  function colIndex(re) {
    return headers.findIndex((name) => re.test(String(name || "").trim()));
  }

  function numberRows() {
    [...grid.querySelectorAll("tbody tr")].forEach((tr, i) => {
      const num = tr.querySelector(".effort-row-num");
      if (num) num.textContent = String(i + 1);
    });
  }

  function recalc() {
    const i1 = colIndex(/aufwand\s*fb|zeit\s*1/i);
    const i2 = colIndex(/aufwand\s*it|zeit\s*2/i);
    const is = colIndex(/^summe$/i);
    if (i1 < 0 || i2 < 0 || is < 0) return;
    grid.querySelectorAll("tbody tr").forEach((tr) => {
      const cells = dataCells(tr);
      const total = parseNum(cells[i1]?.innerText) + parseNum(cells[i2]?.innerText);
      const cell = cells[is];
      if (!cell) return;
      cell.contentEditable = "false";
      cell.classList.add("is-sum");
      cell.textContent = String(total);
    });
    numberRows();
  }

  function flush() {
    recalc();
    const csv = toCsv();
    try {
      localStorage.setItem(KEY, csv);
    } catch {
      /* ignore quota */
    }
    if (window.opener && !window.opener.closed) {
      window.opener.postMessage({ type: TYPE, csv }, window.location.origin);
    }
  }

  function addRow(values) {
    const tr = document.createElement("tr");
    const num = document.createElement("td");
    num.className = "effort-row-num";
    num.textContent = String((grid.querySelectorAll("tbody tr").length || 0) + 1);
    tr.appendChild(num);
    headers.forEach((name, i) => {
      const td = document.createElement("td");
      const isSum = /^summe$/i.test(String(name || "").trim());
      td.contentEditable = isSum ? "false" : "true";
      if (isSum) td.classList.add("is-sum");
      td.textContent = values?.[i] || "";
      tr.appendChild(td);
    });
    grid.querySelector("tbody")?.appendChild(tr);
  }

  function colLetter(i) {
    return String.fromCharCode(65 + i);
  }

  function render(rows) {
    headers = rows[0] || [];
    const body = rows.slice(1);
    grid.innerHTML = "";
    const thead = document.createElement("thead");
    const letters = document.createElement("tr");
    letters.className = "effort-col-letters";
    const corner = document.createElement("th");
    corner.className = "effort-corner";
    letters.appendChild(corner);
    headers.forEach((_, i) => {
      const th = document.createElement("th");
      th.textContent = colLetter(i);
      letters.appendChild(th);
    });
    thead.appendChild(letters);
    const hr = document.createElement("tr");
    const rowZero = document.createElement("th");
    rowZero.className = "effort-row-num";
    rowZero.textContent = "";
    hr.appendChild(rowZero);
    headers.forEach((name) => {
      const th = document.createElement("th");
      th.textContent = name;
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    const tbody = document.createElement("tbody");
    grid.appendChild(thead);
    grid.appendChild(tbody);
    (body.length ? body : [headers.map(() => "")]).forEach((row) => addRow(row));
    recalc();
  }

  grid.addEventListener("input", flush);
  addBtn?.addEventListener("click", () => {
    addRow();
    flush();
  });
  window.addEventListener("pagehide", flush);
  window.addEventListener("beforeunload", flush);

  const draft = (() => {
    try {
      return localStorage.getItem(KEY) || "";
    } catch {
      return "";
    }
  })();
  if (draft.trim() && /aufwand\s*fb/i.test(draft.split(/\r?\n/)[0] || "")) {
    render(parseCsv(draft));
    flush();
  } else {
    fetch("/api/sessions/effort-sheet/template?dummy=1")
      .then((r) => r.text())
      .then((text) => {
        render(parseCsv(text));
        flush();
      })
      .catch(() => {
        render([
          ["Aufwand FB", "Aufwand IT", "Summe"],
          ["", "", "0"],
        ]);
        flush();
      });
  }
})();
