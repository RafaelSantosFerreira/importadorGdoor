(() => {
  const { esc, setStatus, api, fmt, baixarCsv } = window.UI;
  const $ = (id) => document.getElementById(id);

  const tbody = document.querySelector("#tabelaLog tbody");
  const card = $("cardProgresso");
  const botoes = ["btnComparar", "btnDryRun", "btnAplicar", "btnPrecoSimular", "btnPrecoAplicar", "btnDifBuscar", "btnDifAplicar"].map($);
  const OPCOES = ["atualizar_preco", "atualizar_estoque", "atualizar_cadastro", "inserir_novos"];

  let pollTimer = null;
  let logComp = [];
  let filtroTipo = "";
  let ultimaSimulacao = null; // { chave, erros }

  // ---------- util ----------
  function setBusy(busy) {
    botoes.forEach((b) => (b.disabled = busy));
    OPCOES.forEach((id) => ($(id).disabled = busy));
  }
  function opcoes() {
    return Object.fromEntries(OPCOES.map((id) => [id, $(id).checked]));
  }
  const chaveOpcoes = () => JSON.stringify(opcoes());

  const ABAS = { comp: ["tabComp", "painelComp"], imp: ["tabImp", "painelImp"], dif: ["tabDif", "painelDif"] };
  function mostrarAba(qual) {
    Object.entries(ABAS).forEach(([nome, [tab, painel]]) => {
      const sel = nome === qual;
      $(tab).setAttribute("aria-selected", String(sel));
      $(painel).hidden = !sel;
    });
  }
  Object.entries(ABAS).forEach(([nome, [tab]]) =>
    $(tab).addEventListener("click", () => mostrarAba(nome))
  );

  // ---------- progresso ----------
  function renderProgresso(p) {
    const pct = Math.max(0, Math.min(100, Number(p.percent) || 0));
    card.hidden = false;
    const fim = p.done && !p.rodando && !p.erro;
    const nome = {
      comparar: "Comparação",
      preco: "Atualização de preços",
      dif_preco: "Busca de diferenças",
      dif_preco_aplicar: "Atualização de preços",
    }[p.operacao] || "Importação";
    $("progressMsg").textContent = fim ? `${nome} concluída` : p.mensagem || "…";
    $("progressPct").textContent = `${pct}%`;
    $("progressFill").style.width = `${pct}%`;
    $("progressBar").setAttribute("aria-valuenow", String(pct));
    $("progressDetail").textContent = p.total
      ? `${fmt(p.atual)} de ${fmt(p.total)}`
      : "";
    card.classList.remove("running", "done", "error");
    if (p.erro) card.classList.add("error");
    else if (p.rodando) card.classList.add("running");
    else if (p.done) card.classList.add("done");
  }

  function pararPoll() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  function acompanhar(operacao, ctx = {}) {
    setBusy(true);
    pararPoll();
    return new Promise((resolve, reject) => {
      pollTimer = setInterval(async () => {
        let p;
        try {
          p = await fetch("/api/progresso").then((r) => r.json());
        } catch (e) {
          pararPoll();
          setBusy(false);
          setStatus(`Servidor não respondeu: ${e.message}`, "err");
          reject(e);
          return;
        }
        renderProgresso(p);
        if (p.rodando && !p.done) {
          setStatus(p.mensagem || "Processando…", "busy");
          return;
        }
        pararPoll();
        setBusy(false);
        if (p.erro) {
          setStatus(`Erro: ${p.erro}`, "err");
          reject(new Error(p.erro));
          return;
        }
        const r = p.resultado || {};
        if (operacao === "comparar") concluirComparacao(r);
        else if (operacao === "preco") concluirPreco(r);
        else if (operacao === "dif_preco") concluirDifBusca(r);
        else if (operacao === "dif_preco_aplicar") concluirDifAplicar(r);
        else concluirImportacao(r, ctx);
        resolve(r);
      }, 400);
    });
  }

  // ---------- comparação ----------
  function tagTipo(tipo) {
    const cls = { PRECO: "preco", ESTOQUE: "estoque", "PRECO+ESTOQUE": "ambos", NOVO: "novo" }[tipo] || "";
    const txt = { PRECO: "Preço", ESTOQUE: "Quantidade", "PRECO+ESTOQUE": "Preço + qtd", NOVO: "Novo" }[tipo] || tipo;
    return `<span class="tag ${cls}">${esc(txt)}</span>`;
  }
  const difere = (a, b) => a !== "" && b !== "" && a !== b;

  function concluirComparacao(r) {
    $("sTotal").textContent = fmt(r.total_csv);
    $("sNovos").textContent = fmt(r.novos);
    $("sIguais").textContent = fmt(r.iguais);
    $("sPreco").textContent = fmt(r.dif_preco);
    $("sEstoque").textContent = fmt(r.dif_estoque);
    $("sAmbos").textContent = fmt(r.dif_ambos);
    document.querySelectorAll("#stats .tile[data-tipo]").forEach((t) => (t.disabled = false));
    logComp = r.log || [];
    filtroTipo = "";
    marcarTile();
    $("toolbarLog").hidden = !logComp.length;
    renderLog();
    mostrarAba("comp");
    const extra = r.log_truncado ? " A lista mostra só os primeiros itens." : "";
    setStatus(
      `Comparação concluída: ${fmt(r.novos)} novos, ${fmt(r.dif_preco + r.dif_ambos)} com preço diferente, ${fmt(r.dif_estoque + r.dif_ambos)} com quantidade diferente.${extra}`,
      "ok"
    );
  }

  function itensFiltrados() {
    const q = $("buscaLog").value.trim().toLowerCase();
    return logComp.filter(
      (r) =>
        (!filtroTipo || r.tipo === filtroTipo) &&
        (!q || r.codigo.toLowerCase().includes(q) || (r.descricao || "").toLowerCase().includes(q))
    );
  }

  function renderLog() {
    const items = itensFiltrados();
    $("infoLog").textContent = logComp.length
      ? `${fmt(items.length)} de ${fmt(logComp.length)} itens`
      : "";
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="8"><div class="empty"><b>${
        logComp.length ? "Nada neste filtro" : "Nenhuma diferença"
      }</b>${logComp.length ? "Clique no mesmo quadro de novo para ver todos." : "Preços e quantidades do CSV já batem com o banco."}</div></td></tr>`;
      return;
    }
    tbody.innerHTML = items
      .map((r) => {
        const pDif = difere(r.preco_csv, r.preco_banco) ? "diff" : "";
        const qDif = difere(r.qtd_csv, r.qtd_banco) ? "diff" : "";
        return `<tr>
          <td class="code">${esc(r.codigo)}</td>
          <td>${esc(r.descricao)}</td>
          <td>${tagTipo(r.tipo)}</td>
          <td class="num">${esc(r.preco_banco || "—")}</td>
          <td class="num"><span class="${pDif}">${esc(r.preco_csv || "—")}</span></td>
          <td class="num">${esc(r.qtd_banco || "—")}</td>
          <td class="num"><span class="${qDif}">${esc(r.qtd_csv || "—")}</span></td>
          <td class="detail">${esc(r.detalhe)}</td>
        </tr>`;
      })
      .join("");
  }

  function marcarTile() {
    document.querySelectorAll("#stats .tile").forEach((t) =>
      t.classList.toggle("sel", Boolean(filtroTipo) && t.dataset.tipo === filtroTipo)
    );
  }

  $("stats").addEventListener("click", (e) => {
    const t = e.target.closest(".tile[data-tipo]");
    if (!t || t.disabled) return;
    filtroTipo = filtroTipo === t.dataset.tipo ? "" : t.dataset.tipo;
    marcarTile();
    renderLog();
  });
  $("buscaLog").addEventListener("input", renderLog);
  $("btnExportar").addEventListener("click", () => {
    const cab = ["codigo", "descricao", "tipo", "preco_banco", "preco_csv", "custo_banco", "custo_csv", "qtd_banco", "qtd_csv", "detalhe"];
    baixarCsv(
      `comparacao_${new Date().toISOString().slice(0, 10)}.csv`,
      [cab, ...itensFiltrados().map((r) => cab.map((k) => r[k]))]
    );
  });

  // ---------- importação ----------
  function concluirImportacao(r, ctx) {
    if (r.dry_run && ctx.chave) ultimaSimulacao = { chave: ctx.chave, erros: r.erros };
    if (!r.dry_run && r.gravado) ultimaSimulacao = null;

    let banner;
    if (r.dry_run) {
      banner = r.erros
        ? ["err", "Simulação com erros", "Corrija os erros abaixo antes de aplicar. Nada foi gravado."]
        : ["info", "Simulação concluída", "Tudo foi executado e desfeito. Nada foi gravado. Se estiver certo, clique em “Aplicar no banco”."];
    } else if (r.gravado) {
      banner = ["ok", "Importação gravada no banco", r.situacao || ""];
    } else {
      banner = ["err", "Nada foi gravado", r.situacao || "Houve erros; a transação foi desfeita."];
    }

    const linhas = (r.log || [])
      .map((l) => {
        const cls = l.startsWith("ERRO") ? "l-erro" : l.startsWith("INSERT") ? "l-insert" : "l-update";
        return `<div class="${cls}">${esc(l)}</div>`;
      })
      .join("");
    const campos = (r.campos_update || []).map((c) => `<span class="chip">${esc(c)}</span>`).join("");

    $("resultadoImp").innerHTML = `
      <div class="banner ${banner[0]}"><div><b>${esc(banner[1])}</b><span>${esc(banner[2])}</span></div></div>
      <div class="tiles" style="margin-bottom:1rem">
        <div class="tile ok"><span>Inseridos</span><strong>${fmt(r.inseridos)}</strong></div>
        <div class="tile info"><span>Atualizados</span><strong>${fmt(r.atualizados)}</strong></div>
        <div class="tile"><span>Sem alteração</span><strong>${fmt(r.pulados)}</strong></div>
        <div class="tile ${r.erros ? "danger" : ""}"><span>Erros</span><strong>${fmt(r.erros)}</strong></div>
      </div>
      <p class="muted" style="margin:0 0 0.4rem">Campos alterados em produtos existentes:</p>
      <div style="margin-bottom:1rem">${campos || '<span class="muted">nenhum</span>'}</div>
      <p class="muted" style="margin:0 0 0.4rem">Log${(r.log || []).length >= 200 ? " (primeiras linhas)" : ""}:</p>
      <div class="log-box">${linhas || '<div class="muted">vazio</div>'}</div>`;

    const badge = $("impBadge");
    badge.hidden = false;
    badge.textContent = r.erros ? `${r.erros} erro(s)` : r.dry_run ? "simulação" : "gravado";
    mostrarAba("imp");

    const resumo = `${fmt(r.inseridos)} inserções, ${fmt(r.atualizados)} atualizações, ${fmt(r.erros)} erros.`;
    if (r.dry_run) setStatus(`Simulação: ${resumo}`, r.erros ? "err" : "ok");
    else setStatus(r.gravado ? `Gravado: ${resumo}` : `Nada gravado: ${resumo}`, r.gravado ? "ok" : "err");
  }

  async function rodarImportacao(dryRun) {
    const opts = opcoes();
    const chave = chaveOpcoes();
    setStatus(dryRun ? "Iniciando simulação…" : "Iniciando importação…", "busy");
    try {
      await api("/api/importar", { json: { ...opts, dry_run: dryRun } });
      await acompanhar("importar", { chave });
    } catch (e) {
      setBusy(false);
      setStatus(`Erro na importação: ${e.message}`, "err");
    }
  }

  $("btnComparar").addEventListener("click", async () => {
    setStatus("Iniciando comparação…", "busy");
    try {
      await api("/api/comparar", { method: "POST" });
      await acompanhar("comparar");
    } catch (e) {
      setBusy(false);
      setStatus(`Erro na comparação: ${e.message}`, "err");
    }
  });

  $("btnDryRun").addEventListener("click", () => rodarImportacao(true));

  $("btnAplicar").addEventListener("click", () => {
    const o = opcoes();
    const itens = [
      o.atualizar_preco && "preços",
      o.atualizar_estoque && "quantidades",
      o.atualizar_cadastro && "cadastro dos existentes",
      o.inserir_novos && "inserir novos",
    ].filter(Boolean);
    let aviso = "";
    if (!ultimaSimulacao || ultimaSimulacao.chave !== chaveOpcoes()) {
      aviso = "\n\n⚠ Você ainda não simulou com estas opções.";
    } else if (ultimaSimulacao.erros) {
      aviso = `\n\n⚠ A última simulação teve ${ultimaSimulacao.erros} erro(s). A gravação provavelmente será desfeita.`;
    }
    const msg =
      `Gravar no Firebird agora?\n\nVai alterar: ${itens.join(", ") || "nada"}.` +
      `\nSe houver qualquer erro, nada será gravado.${aviso}`;
    if (confirm(msg)) rodarImportacao(false);
  });

  // ---------- só preço ----------
  let ultimaSimPreco = null; // resultado da última simulação de preços

  function concluirPreco(r) {
    if (r.dry_run) ultimaSimPreco = r;
    else if (r.gravado) ultimaSimPreco = null;

    let banner;
    if (r.dry_run) {
      banner = r.erros
        ? ["err", "Simulação de preços com erros", "Nada foi gravado. Veja os erros no log."]
        : ["info", "Simulação de preços concluída", "Nada foi gravado. Confira a lista e clique em “Gravar preços”."];
    } else if (r.gravado) {
      banner = ["ok", "Preços gravados no banco", r.situacao];
    } else {
      banner = ["err", "Nada foi gravado", r.situacao];
    }

    const linhas = (r.log || [])
      .map((l) => `<div class="${l.startsWith("ERRO") ? "l-erro" : "l-update"}">${esc(l)}</div>`)
      .join("");
    const faltando = (r.nao_encontrados_amostra || []).map((c) => `<span class="chip">${esc(c)}</span>`).join("");

    $("resultadoImp").innerHTML = `
      <div class="banner ${banner[0]}"><div><b>${esc(banner[1])}</b><span>${esc(banner[2])}</span></div></div>
      <div class="tiles" style="margin-bottom:1rem">
        <div class="tile"><span>Linhas no CSV</span><strong>${fmt(r.linhas_csv)}</strong></div>
        <div class="tile info"><span>Preço alterado</span><strong>${fmt(r.atualizados)}</strong></div>
        <div class="tile"><span>Já iguais</span><strong>${fmt(r.iguais)}</strong></div>
        <div class="tile warn"><span>Sem preço no CSV (ignorados)</span><strong>${fmt(r.sem_preco)}</strong></div>
        <div class="tile ${r.nao_encontrados ? "warn" : ""}"><span>Código não existe no banco</span><strong>${fmt(r.nao_encontrados)}</strong></div>
        <div class="tile ${r.erros ? "danger" : ""}"><span>Erros</span><strong>${fmt(r.erros)}</strong></div>
      </div>
      ${r.duplicados ? `<p class="muted">${fmt(r.duplicados)} linha(s) com id_estoque repetido foram ignoradas (vale a primeira).</p>` : ""}
      ${faltando ? `<p class="muted" style="margin:0 0 0.4rem">id_estoque sem produto no banco${r.nao_encontrados > 200 ? " (primeiros 200)" : ""}:</p><div style="margin-bottom:1rem;max-height:120px;overflow:auto">${faltando}</div>` : ""}
      <p class="muted" style="margin:0 0 0.4rem">Alterações (banco → CSV)${(r.log || []).length >= 300 ? ", primeiras linhas" : ""}:</p>
      <div class="log-box">${linhas || '<div class="muted">nenhuma alteração</div>'}</div>`;

    const badge = $("impBadge");
    badge.hidden = false;
    badge.textContent = r.erros ? `${r.erros} erro(s)` : r.dry_run ? "simulação" : "gravado";
    mostrarAba("imp");

    const resumo = `${fmt(r.atualizados)} preços alterados, ${fmt(r.iguais)} iguais, ${fmt(r.nao_encontrados)} códigos não encontrados, ${fmt(r.erros)} erros.`;
    if (r.dry_run) setStatus(`Simulação de preços: ${resumo}`, r.erros ? "err" : "ok");
    else setStatus(r.gravado ? `Preços gravados: ${resumo}` : `Nada gravado: ${resumo}`, r.gravado ? "ok" : "err");
  }

  async function rodarPreco(dryRun) {
    setStatus(dryRun ? "Iniciando simulação de preços…" : "Gravando preços…", "busy");
    try {
      await api("/api/preco", { json: { dry_run: dryRun } });
      await acompanhar("preco");
    } catch (e) {
      setBusy(false);
      setStatus(`Erro ao atualizar preços: ${e.message}`, "err");
    }
  }

  $("btnPrecoSimular").addEventListener("click", () => rodarPreco(true));
  $("btnPrecoAplicar").addEventListener("click", () => {
    const s = ultimaSimPreco;
    const info = s
      ? `\n\nNa última simulação: ${fmt(s.atualizados)} preços seriam alterados${s.erros ? ` e houve ${s.erros} erro(s)` : ""}.`
      : "\n\n⚠ Você ainda não simulou os preços.";
    if (confirm(`Gravar PRECO_VENDA no Firebird agora?\nNenhum outro campo será alterado.${info}`)) {
      rodarPreco(false);
    }
  });

  // ---------- diferenças de preço (id_identificador) ----------
  const tbodyDif = document.querySelector("#tabelaDif tbody");
  let itensDif = [];
  let ultimaBuscaDif = null; // último resultado de "Buscar diferenças"

  function statsDif(r) {
    $("dTotal").textContent = fmt(r.linhas_csv);
    $("dDif").textContent = fmt(r.diferentes);
    $("dIguais").textContent = fmt(r.iguais);
    $("dSemPreco").textContent = fmt(r.sem_preco);
    $("dNaoAch").textContent = fmt(r.nao_encontrados);
    $("dZera").textContent = fmt(r.zerariam);
  }

  function itensDifFiltrados() {
    const q = $("buscaDif").value.trim().toLowerCase();
    return itensDif.filter(
      (r) => !q || r.codigo.toLowerCase().includes(q) || (r.descricao || "").toLowerCase().includes(q)
    );
  }

  function renderDif() {
    const items = itensDifFiltrados();
    $("infoDif").textContent = itensDif.length
      ? `${fmt(items.length)} de ${fmt(itensDif.length)} itens`
      : "";
    if (!items.length) {
      tbodyDif.innerHTML = `<tr><td colspan="5"><div class="empty"><b>${
        itensDif.length ? "Nada neste filtro" : "Nenhuma diferença de preço"
      }</b>${
        itensDif.length ? "Limpe a busca para ver todos." : "PRECO_VENDA do banco já bate com o CSV."
      }</div></td></tr>`;
      return;
    }
    tbodyDif.innerHTML = items
      .map(
        (r) => `<tr>
          <td class="code">${esc(r.codigo)}</td>
          <td>${esc(r.descricao)}</td>
          <td class="num">${esc(r.preco_banco || "—")}</td>
          <td class="num"><span class="diff">${esc(r.preco_csv || "—")}</span></td>
          <td>${
            r.zeraria
              ? '<span class="tag ambos">zeraria — não grava</span>'
              : '<span class="tag preco">atualiza</span>'
          }</td>
        </tr>`
      )
      .join("");
  }

  function aplicarResultadoDif(r, banner) {
    statsDif(r);
    itensDif = r.itens || [];
    $("toolbarDif").hidden = !itensDif.length;
    renderDif();
    $("bannerDif").innerHTML = banner
      ? `<div class="banner ${banner[0]}" style="margin:1rem 1rem 0"><div><b>${esc(
          banner[1]
        )}</b><span>${esc(banner[2])}</span></div></div>`
      : "";
    const badge = $("difBadge");
    badge.hidden = false;
    badge.textContent = `${fmt(r.diferentes)} dif.`;
    mostrarAba("dif");
  }

  function concluirDifBusca(r) {
    ultimaBuscaDif = r;
    aplicarResultadoDif(r, null);
    const extra = r.truncado ? " A lista mostra só os primeiros itens." : "";
    const zera = r.zerariam ? ` ${fmt(r.zerariam)} zerariam o preço e não serão gravados.` : "";
    setStatus(
      `${fmt(r.diferentes)} produto(s) com preço diferente de ${fmt(r.linhas_csv)} linhas.${zera}${extra}`,
      r.diferentes ? "ok" : "ok"
    );
  }

  function concluirDifAplicar(r) {
    if (!r.dry_run && r.gravado) ultimaBuscaDif = null;
    let banner;
    if (r.dry_run) {
      banner = r.erros
        ? ["err", "Simulação com erros", "Nada foi gravado."]
        : ["info", "Simulação concluída", "Nada foi gravado. Clique em “Atualizar preços do CSV” para gravar."];
    } else if (r.gravado) {
      banner = ["ok", "Preços gravados no banco", r.situacao || ""];
    } else {
      banner = ["err", "Nada foi gravado", r.situacao || ""];
    }
    aplicarResultadoDif(r, banner);
    const resumo = `${fmt(r.atualizados)} preço(s) alterado(s), ${fmt(r.pulados_zero)} pulado(s) por zerarem, ${fmt(r.erros)} erro(s).`;
    if (r.dry_run) setStatus(`Simulação: ${resumo}`, r.erros ? "err" : "ok");
    else setStatus(r.gravado ? `Gravado: ${resumo}` : `Nada gravado: ${resumo}`, r.gravado ? "ok" : "err");
  }

  $("buscaDif").addEventListener("input", renderDif);
  $("btnExportarDif").addEventListener("click", () => {
    const cab = ["codigo", "descricao", "preco_banco", "preco_csv", "zeraria"];
    baixarCsv(
      `diferencas_preco_${new Date().toISOString().slice(0, 10)}.csv`,
      [cab, ...itensDifFiltrados().map((r) => cab.map((k) => r[k]))]
    );
  });

  $("btnDifBuscar").addEventListener("click", async () => {
    setStatus("Buscando diferenças de preço…", "busy");
    try {
      await api("/api/preco/diferencas", { method: "POST" });
      await acompanhar("dif_preco");
    } catch (e) {
      setBusy(false);
      setStatus(`Erro ao buscar diferenças: ${e.message}`, "err");
    }
  });

  async function rodarDifAplicar(dryRun) {
    setStatus(dryRun ? "Simulando preços do CSV…" : "Gravando preços do CSV…", "busy");
    try {
      await api("/api/preco/diferencas/aplicar", { json: { dry_run: dryRun } });
      await acompanhar("dif_preco_aplicar");
    } catch (e) {
      setBusy(false);
      setStatus(`Erro ao atualizar preços: ${e.message}`, "err");
    }
  }

  $("btnDifAplicar").addEventListener("click", () => {
    const b = ultimaBuscaDif;
    const info = b
      ? `\n\nNa última busca: ${fmt(b.diferentes)} produto(s) com preço diferente` +
        (b.zerariam ? `, dos quais ${fmt(b.zerariam)} não serão gravados por zerarem o preço` : "") +
        "."
      : "\n\n⚠ Você ainda não buscou as diferenças.";
    const msg =
      "Gravar PRECO_VENDA no Firebird agora?\n" +
      "Casa por id_identificador e altera só o preço de venda." +
      `${info}\n\nSe houver qualquer erro, nada será gravado.`;
    if (confirm(msg)) rodarDifAplicar(false);
  });

  // Mostra qual coluna do CSV alimenta o preço (de-para de PRECO_VENDA).
  api("/api/mapeamento")
    .then((m) => {
      const col = (m.mapeamento || {}).PRECO_VENDA;
      if (col) {
        $("colPreco").textContent = col;
        $("colPrecoDif").textContent = col;
      }
    })
    .catch(() => {});

  // Se a página foi recarregada no meio de uma operação, retoma o acompanhamento.
  fetch("/api/progresso")
    .then((r) => r.json())
    .then((p) => {
      if (p.rodando) {
        renderProgresso(p);
        const op = ["comparar", "preco", "dif_preco", "dif_preco_aplicar"].includes(p.operacao)
          ? p.operacao
          : "importar";
        acompanhar(op).catch(() => {});
      }
    })
    .catch(() => {});
})();
