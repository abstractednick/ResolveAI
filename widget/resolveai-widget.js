(function () {
  const root = document.getElementById("resolveai-widget");
  if (!root) return;

  const apiBase = root.getAttribute("data-api") || "http://localhost:8000";
  let apiKey = root.getAttribute("data-tenant-key") || localStorage.getItem("resolveai_widget_key") || "";

  root.innerHTML = `
    <div style="border:1px solid rgba(15,28,46,.12);border-radius:16px;background:rgba(255,255,255,.85);padding:16px;box-shadow:0 10px 30px rgba(15,28,46,.06)">
      <label style="display:block;font-size:12px;margin-bottom:6px;opacity:.7">Tenant API key</label>
      <input id="rai-key" value="${apiKey}" placeholder="paste tenant api key" style="width:100%;box-sizing:border-box;margin-bottom:12px;padding:10px 12px;border-radius:10px;border:1px solid rgba(15,28,46,.15)" />
      <label style="display:block;font-size:12px;margin-bottom:6px;opacity:.7">Your question</label>
      <textarea id="rai-q" rows="4" placeholder="How do I reset my password?" style="width:100%;box-sizing:border-box;padding:10px 12px;border-radius:10px;border:1px solid rgba(15,28,46,.15);resize:vertical"></textarea>
      <div style="display:flex;gap:8px;margin-top:12px">
        <button id="rai-ask" style="flex:1;border:0;border-radius:10px;background:#0f1c2e;color:#fff;padding:10px 12px;cursor:pointer">Get answer</button>
        <button id="rai-ticket" style="border:0;border-radius:10px;background:#e07a5f;color:#fff;padding:10px 12px;cursor:pointer">Still need help</button>
      </div>
      <div id="rai-out" style="margin-top:14px;font-size:14px;line-height:1.45;color:rgba(15,28,46,.8)"></div>
    </div>
  `;

  const keyEl = document.getElementById("rai-key");
  const qEl = document.getElementById("rai-q");
  const out = document.getElementById("rai-out");

  async function query(createTicket) {
    apiKey = keyEl.value.trim();
    localStorage.setItem("resolveai_widget_key", apiKey);
    out.textContent = "Thinking…";
    try {
      const res = await fetch(apiBase + "/api/v1/widget/query", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Tenant-Key": apiKey,
        },
        body: JSON.stringify({
          question: qEl.value,
          create_ticket_if_unresolved: !!createTicket,
          customer_email: "widget.user@example.com",
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      if (data.answered && data.answer) {
        out.innerHTML = `<strong>Suggested answer</strong><div style="margin-top:6px">${escapeHtml(data.answer)}</div><div style="margin-top:8px;font-size:12px;opacity:.6">confidence ${(data.confidence * 100).toFixed(0)}%</div>`;
      } else if (data.ticket_id) {
        out.textContent = "Ticket created: " + data.ticket_id;
      } else {
        out.textContent = "No confident answer yet. Click “Still need help” to open a ticket.";
      }
    } catch (e) {
      out.textContent = e.message || String(e);
    }
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  document.getElementById("rai-ask").addEventListener("click", function () {
    query(false);
  });
  document.getElementById("rai-ticket").addEventListener("click", function () {
    query(true);
  });
})();
