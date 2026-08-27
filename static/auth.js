(function () {
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function showAccount(user) {
    window.currentActorName = user.displayName || "";
    window.currentActor = user;
    let box = document.getElementById("account");
    if (!box) {
      box = el("div", "account");
      box.id = "account";
      document.querySelector(".chrome .top")?.appendChild(box);
    }
    box.replaceChildren();
    box.hidden = false;

    const nameEl = el("span", "account-name", user.displayName);
    box.appendChild(nameEl);

    const out = el("button", "account-out", "Abmelden");
    out.type = "button";
    out.onclick = async () => {
      await fetch("/api/auth/logout", { method: "POST" });
      location.reload();
    };
    box.appendChild(out);
  }

  function gate() {
    return new Promise((resolve, reject) => {
      document.body.classList.add("gated");
      const overlay = el("div", "gate");
      const box = el("form", "gate-box");
      box.appendChild(el("p", "empty-title", "Anmelden"));
      box.appendChild(el("p", "empty-sub", "Jira-Account wählen."));
      const filterLabel = el("label", null, "Suchen");
      const filter = el("input");
      filter.type = "search";
      filter.id = "account-filter";
      filter.placeholder = "Name oder Person…";
      filter.autocomplete = "off";
      filterLabel.appendChild(filter);
      box.appendChild(filterLabel);
      const label = el("label", null, "Account");
      const select = el("select");
      select.id = "account-select";
      select.setAttribute("aria-label", "Account");
      select.required = true;
      label.appendChild(select);
      box.appendChild(label);
      const status = el("p", "empty-sub gate-status", "Lade Personen…");
      box.appendChild(status);
      const go = el("button", "btn btn-primary", "Weiter");
      go.type = "submit";
      go.disabled = true;
      box.appendChild(go);
      overlay.appendChild(box);
      document.body.appendChild(overlay);

      let accounts = [];

      function fillSelect(rows) {
        select.replaceChildren();
        rows.forEach((row) => {
          const opt = el("option", null, row.displayName + (row.id ? ` (${row.id})` : ""));
          opt.value = row.id;
          select.appendChild(opt);
        });
        go.disabled = rows.length === 0;
      }

      function applyFilter() {
        const needle = (filter.value || "").trim().toLowerCase();
        if (!needle) {
          fillSelect(accounts);
          return;
        }
        fillSelect(
          accounts.filter((row) => {
            const blob = `${row.displayName || ""} ${row.id || ""}`.toLowerCase();
            return blob.includes(needle);
          })
        );
      }

      async function loadAccounts(q) {
        const needle = (q || "").trim();
        if (needle.length < 2) {
          accounts = [];
          fillSelect([]);
          status.textContent = "Mind. 2 Zeichen suchen.";
          return;
        }
        status.textContent = "Lade Personen…";
        go.disabled = true;
        const r = await fetch(`/api/auth/accounts?q=${encodeURIComponent(needle)}`);
        if (!r.ok) throw new Error("accounts");
        const d = await r.json();
        accounts = d.accounts || [];
        if (!accounts.length) {
          status.textContent = "Keine Treffer.";
          fillSelect([]);
          return;
        }
        status.textContent = `${accounts.length} Personen`;
        applyFilter();
      }

      let filterTimer = null;
      filter.addEventListener("input", () => {
        clearTimeout(filterTimer);
        const local = (filter.value || "").trim();
        applyFilter();
        filterTimer = setTimeout(() => {
          loadAccounts(local).catch(() => {
            status.textContent = "Jira-Anbindung prüfen.";
            fillSelect([]);
          });
        }, 280);
      });

      status.textContent = "Mind. 2 Zeichen suchen.";

      box.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!select.value) return;
        go.disabled = true;
        status.textContent = "";
        try {
          const r = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ account: select.value }),
          });
          if (!r.ok) {
            status.textContent = "Anmeldung fehlgeschlagen.";
            return;
          }
          const d = await r.json();
          overlay.remove();
          document.body.classList.remove("gated");
          showAccount(d.user);
          resolve(d.user);
        } catch {
          status.textContent = "Netzwerkfehler — bitte erneut versuchen.";
        } finally {
          go.disabled = false;
        }
      });
    });
  }

  window.whenAuthed = (async () => {
    try {
      const r = await fetch("/api/auth/me");
      const d = await r.json().catch(() => ({}));
      if (d.authenticated && d.user) {
        document.body.classList.remove("gated");
        showAccount(d.user);
        return d.user;
      }
    } catch {
      /* Gate öffnen — kein Blank-Screen */
    }
    return gate();
  })();
})();
