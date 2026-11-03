// Utilitários compartilhados entre as telas.
window.UI = (() => {
  function esc(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  // tipo: "" | "ok" | "err" | "warn" | "busy"
  function setStatus(msg, tipo = "") {
    const el = document.getElementById("status");
    if (!el) return;
    el.textContent = msg;
    el.className = "status-bar" + (tipo ? ` ${tipo}` : "");
  }

  function loading(btn, on) {
    if (!btn) return;
    btn.classList.toggle("loading", on);
    btn.disabled = on;
  }

  async function api(url, opts = {}) {
    const init = { ...opts };
    if (opts.json !== undefined) {
      init.method = init.method || "POST";
      init.headers = { "Content-Type": "application/json", ...(init.headers || {}) };
      init.body = JSON.stringify(opts.json);
      delete init.json;
    }
    const resp = await fetch(url, init);
    let data;
    try {
      data = await resp.json();
    } catch {
      throw new Error(`Resposta inválida do servidor (HTTP ${resp.status})`);
    }
    if (!data.ok) throw new Error(data.erro || `Falha (HTTP ${resp.status})`);
    return data;
  }

  const fmt = (n) =>
    n === null || n === undefined || n === "" ? "—" : Number(n).toLocaleString("pt-BR");

  // Avisa ao sair da página com alterações não salvas.
  function guardaSaida(isDirty) {
    window.addEventListener("beforeunload", (e) => {
      if (isDirty()) {
        e.preventDefault();
        e.returnValue = "";
      }
    });
  }

  function marcarSujo(btn, sujo) {
    if (!btn) return;
    let dot = btn.querySelector(".dirty-dot");
    if (sujo && !dot) {
      dot = document.createElement("span");
      dot.className = "dirty-dot";
      dot.title = "Alterações não salvas";
      btn.appendChild(dot);
    } else if (!sujo && dot) {
      dot.remove();
    }
  }

  function baixarCsv(nome, linhas) {
    const conteudo = linhas
      .map((l) => l.map((v) => `"${String(v ?? "").replaceAll('"', '""')}"`).join(";"))
      .join("\r\n");
    const blob = new Blob(["﻿" + conteudo], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = nome;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  return { esc, setStatus, loading, api, fmt, guardaSaida, marcarSujo, baixarCsv };
})();
