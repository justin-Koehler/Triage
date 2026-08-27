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

  function toCsv() {
    const rows = [...grid.querySelectorAll("tr")].map((tr) =>
      [...tr.querySelectorAll("th, td")].map((cell) => csvCell(cell.innerText.trim()))
    );
    return rows.map((row) => row.join(",")).join("\n");
  }

  function flush() {
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
    headers.forEach((_, i) => {
      const td = document.createElement("td");
      td.contentEditable = "true";
      td.textContent = values?.[i] || "";
      tr.appendChild(td);
    });
    grid.querySelector("tbody")?.appendChild(tr);
  }

  function render(rows) {
    headers = rows[0] || [];
    const body = rows.slice(1);
    grid.innerHTML = "";
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
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
  if (draft.trim()) {
    render(parseCsv(draft));
    flush();
  } else {
    fetch("/api/sessions/effort-sheet/template")
      .then((r) => r.text())
      .then((text) => {
        render(parseCsv(text));
        flush();
      })
      .catch(() => {
        render([["Tätigkeit", "Phase", "Bereich", "PT", "Sachkosten"]]);
      });
  }
})();
