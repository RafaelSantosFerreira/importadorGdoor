(() => {
  const { esc, setStatus, api, fmt, baixarCsv } = window.UI;
  const $ = (id) => document.getElementById(id);

  const card = $("cardProgresso");
  const botoes = ["btnDifBuscar", "btnDifSimular", "btnDifAplicar",
                  "btnSalBuscar", "btnSalSimular", "btnSalAplicar", "btnFaltantes"].map($);

  let pollTimer = null;

  // ---------- util ----------
  function setBusy(busy) {
    botoes.forEach((b) => (b.disabled = busy));
  }

  const ABAS = {
    dif: ["tabDif", "painelDif"],
    sal: ["tabSal", "painelSal"],
    falta: ["tabFalta", "painelFalta"],
  };
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
      dif_preco: "Busca de diferenças",
      dif_saldo: "Busca de diferenças",
      dif_saldo_aplicar: "Atualização de saldo",
      faltantes: "Busca de faltantes",
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

  function acompanhar(operacao) {
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
        if (operacao === "dif_preco") painelPreco.concluirBusca(r);
        else if (operacao === "dif_preco_aplicar") painelPreco.concluirAplicar(r);
        else if (operacao === "dif_saldo") painelSaldo.concluirBusca(r);
        else if (operacao === "dif_saldo_aplicar") painelSaldo.concluirAplicar(r);
        else if (operacao === "faltantes") concluirFaltantes(r);
        resolve(r);
      }, 400);
    });
  }

  // ---------- diferenças de um campo (preço, saldo) ----------
  // Mesma tela para os dois: muda o campo gravado, os ids e os textos.
  function criarPainelDiferenca(cfg) {
    const tbody = document.querySelector("#" + cfg.tabela + " tbody");
    let itens = [];
    let ultimaBusca = null;

    const filtrados = () => {
      const q = $(cfg.busca).value.trim().toLowerCase();
      return itens.filter(
        (r) => !q || r.codigo.toLowerCase().includes(q) || (r.descricao || "").toLowerCase().includes(q)
      );
    };

    function render() {
      const items = filtrados();
      $(cfg.info).textContent = itens.length ? `${fmt(items.length)} de ${fmt(itens.length)} itens` : "";
      if (!items.length) {
        const titulo = itens.length ? "Nada neste filtro" : `Nenhuma diferença de ${cfg.rotulo}`;
        const texto = itens.length
          ? "Limpe a busca para ver todos."
          : `${cfg.campo} do banco já bate com o CSV.`;
        tbody.innerHTML =
          `<tr><td colspan="5"><div class="empty"><b>${esc(titulo)}</b>${esc(texto)}</div></td></tr>`;
        return;
      }
      tbody.innerHTML = items
        .map((r) => {
          const tag = r.bloqueado
            ? `<span class="tag ambos">${esc(r.motivo)}</span>`
            : `<span class="tag preco">atualiza</span>`;
          return `<tr>
            <td class="code">${esc(r.codigo)}</td>
            <td>${esc(r.descricao)}</td>
            <td class="num">${esc(r.valor_banco || "—")}</td>
            <td class="num"><span class="diff">${esc(r.valor_csv || "—")}</span></td>
            <td>${tag}</td>
          </tr>`;
        })
        .join("");
    }

    function aplicarResultado(r, banner) {
      $(cfg.tTotal).textContent = fmt(r.linhas_csv);
      $(cfg.tDif).textContent = fmt(r.diferentes);
      $(cfg.tIguais).textContent = fmt(r.iguais);
      $(cfg.tSemValor).textContent = fmt(r.sem_valor);
      $(cfg.tNaoAch).textContent = fmt(r.nao_encontrados);
      $(cfg.tBloq).textContent = fmt(r.bloqueados);
      itens = r.itens || [];
      $(cfg.toolbar).hidden = !itens.length;
      render();
      $(cfg.banner).innerHTML = banner
        ? `<div class="banner ${banner[0]}" style="margin:1rem 1rem 0"><div><b>${esc(
            banner[1]
          )}</b><span>${esc(banner[2])}</span></div></div>`
        : "";
      const badge = $(cfg.badge);
      badge.hidden = false;
      badge.textContent = `${fmt(r.diferentes)} dif.`;
      mostrarAba(cfg.aba);
    }

    function concluirBusca(r) {
      ultimaBusca = r;
      aplicarResultado(r, null);
      const extra = r.truncado ? " A lista mostra só os primeiros itens." : "";
      const bloq = r.bloqueados ? ` ${fmt(r.bloqueados)} não serão gravados (${cfg.motivoCurto}).` : "";
      setStatus(
        `${fmt(r.diferentes)} produto(s) com ${cfg.rotulo} diferente de ${fmt(r.linhas_csv)} linhas.${bloq}${extra}`,
        "ok"
      );
    }

    function concluirAplicar(r) {
      if (!r.dry_run && r.gravado) ultimaBusca = null;
      let banner;
      if (r.dry_run) {
        banner = r.erros
          ? ["err", "Simulação com erros", "Nada foi gravado. Veja os erros listados abaixo."]
          : [
              "info",
              "Simulação concluída",
              `Tudo foi executado e desfeito. Nada foi gravado. Se estiver certo, clique em “${cfg.rotuloGravar}”.`,
            ];
      } else if (r.gravado) {
        banner = ["ok", "Gravado no banco", r.situacao || ""];
      } else {
        banner = ["err", "Nada foi gravado", r.situacao || ""];
      }
      aplicarResultado(r, banner);
      if (r.erros && (r.log || []).length) {
        const linhas = (r.log || [])
          .slice(0, 20)
          .map((l) => `<div class="${l.startsWith("ERRO") ? "l-erro" : "l-update"}">${esc(l)}</div>`)
          .join("");
        $(cfg.banner).innerHTML += `<div class="log-box" style="margin:0.6rem 1rem 0">${linhas}</div>`;
      }
      const resumo = `${fmt(r.atualizados)} alterado(s), ${fmt(r.pulados)} pulado(s), ${fmt(r.erros)} erro(s).`;
      if (r.dry_run) setStatus(`Simulação: ${resumo}`, r.erros ? "err" : "ok");
      else setStatus(r.gravado ? `Gravado: ${resumo}` : `Nada gravado: ${resumo}`, r.gravado ? "ok" : "err");
    }

    async function rodarAplicar(dryRun) {
      setStatus(dryRun ? `Simulando ${cfg.rotulo} do CSV…` : `Gravando ${cfg.rotulo} do CSV…`, "busy");
      try {
        await api(cfg.endpointAplicar, { json: { dry_run: dryRun } });
        await acompanhar(cfg.opAplicar);
      } catch (e) {
        setBusy(false);
        setStatus(`Erro ao atualizar ${cfg.rotulo}: ${e.message}`, "err");
      }
    }

    $(cfg.busca).addEventListener("input", render);
    $(cfg.exportar).addEventListener("click", () => {
      const cab = ["codigo", "descricao", "valor_banco", "valor_csv", "bloqueado", "motivo"];
      baixarCsv(cfg.arquivo + "_" + new Date().toISOString().slice(0, 10) + ".csv", [
        cab,
        ...filtrados().map((r) => cab.map((k) => r[k])),
      ]);
    });

    $(cfg.btnBuscar).addEventListener("click", async () => {
      setStatus(`Buscando diferenças de ${cfg.rotulo}…`, "busy");
      try {
        await api(cfg.endpointBuscar, { method: "POST" });
        await acompanhar(cfg.opBuscar);
      } catch (e) {
        setBusy(false);
        setStatus(`Erro ao buscar diferenças: ${e.message}`, "err");
      }
    });

    $(cfg.btnSimular).addEventListener("click", () => rodarAplicar(true));

    $(cfg.btnAplicar).addEventListener("click", () => {
      const b = ultimaBusca;
      const bloqueio = b && b.bloqueados
        ? `, dos quais ${fmt(b.bloqueados)} não serão gravados (${cfg.motivoCurto})`
        : "";
      const info = b
        ? `\n\nNa última busca: ${fmt(b.diferentes)} produto(s) diferentes${bloqueio}.`
        : "\n\n⚠ Você ainda não buscou as diferenças.";
      const msg =
        `Gravar ${cfg.campo} no Firebird agora?\n` +
        `Casa cast(CODIGO as int) = cast(id_identificador as int) e altera só ${cfg.campo}.` +
        `${info}\n\nSe houver qualquer erro, nada será gravado.`;
      if (confirm(msg)) rodarAplicar(false);
    });

    return { concluirBusca, concluirAplicar };
  }

  const painelPreco = criarPainelDiferenca({
    aba: "dif", campo: "PRECO_VENDA", rotulo: "preço", rotuloGravar: "Gravar preços",
    motivoCurto: "zerariam o preço", arquivo: "diferencas_preco",
    tabela: "tabelaDif", busca: "buscaDif", info: "infoDif", toolbar: "toolbarDif",
    badge: "difBadge", banner: "bannerDif", exportar: "btnExportarDif",
    tTotal: "dTotal", tDif: "dDif", tIguais: "dIguais", tSemValor: "dSemValor",
    tNaoAch: "dNaoAch", tBloq: "dZera",
    btnBuscar: "btnDifBuscar", btnSimular: "btnDifSimular", btnAplicar: "btnDifAplicar",
    endpointBuscar: "/api/preco/diferencas", endpointAplicar: "/api/preco/diferencas/aplicar",
    opBuscar: "dif_preco", opAplicar: "dif_preco_aplicar",
  });

  const painelSaldo = criarPainelDiferenca({
    aba: "sal", campo: "QTD_SALDO", rotulo: "saldo", rotuloGravar: "Gravar saldo",
    motivoCurto: "saldo negativo", arquivo: "diferencas_saldo",
    tabela: "tabelaSal", busca: "buscaSal", info: "infoSal", toolbar: "toolbarSal",
    badge: "salBadge", banner: "bannerSal", exportar: "btnExportarSal",
    tTotal: "qTotal", tDif: "qDif", tIguais: "qIguais", tSemValor: "qSemValor",
    tNaoAch: "qNaoAch", tBloq: "qBloq",
    btnBuscar: "btnSalBuscar", btnSimular: "btnSalSimular", btnAplicar: "btnSalAplicar",
    endpointBuscar: "/api/saldo/diferencas", endpointAplicar: "/api/saldo/diferencas/aplicar",
    opBuscar: "dif_saldo", opAplicar: "dif_saldo_aplicar",
  });

  // ---------- faltando no banco ----------
  const tbodyFalta = document.querySelector("#tabelaFalta tbody");
  let itensFalta = [];

  function itensFaltaFiltrados() {
    const q = $("buscaFalta").value.trim().toLowerCase();
    return itensFalta.filter(
      (r) => !q || r.codigo.toLowerCase().includes(q) || (r.descricao || "").toLowerCase().includes(q)
    );
  }

  function renderFalta() {
    const items = itensFaltaFiltrados();
    $("infoFalta").textContent = itensFalta.length
      ? `${fmt(items.length)} de ${fmt(itensFalta.length)} itens`
      : "";
    if (!items.length) {
      tbodyFalta.innerHTML = `<tr><td colspan="7"><div class="empty"><b>${
        itensFalta.length ? "Nada neste filtro" : "Nenhum código faltando"
      }</b>${
        itensFalta.length ? "Limpe a busca para ver todos." : "Todo código do CSV já existe no banco."
      }</div></td></tr>`;
      return;
    }
    tbodyFalta.innerHTML = items
      .map(
        (r) => `<tr>
          <td class="code">${esc(r.codigo)}</td>
          <td>${esc(r.descricao)}</td>
          <td class="code">${esc(r.barras || "—")}</td>
          <td class="num">${esc(r.preco_venda || "—")}</td>
          <td class="num">${esc(r.preco_custo || "—")}</td>
          <td class="num">${esc(r.qtd || "—")}</td>
          <td class="num">${esc(String(r.linha))}</td>
        </tr>`
      )
      .join("");
  }

  function concluirFaltantes(r) {
    $("fTotal").textContent = fmt(r.linhas_csv);
    $("fFalta").textContent = fmt(r.faltando);
    $("fExiste").textContent = fmt(r.existentes);
    $("fBanco").textContent = fmt(r.codigos_no_banco);
    itensFalta = r.itens || [];
    $("toolbarFalta").hidden = !itensFalta.length;
    renderFalta();
    const badge = $("faltaBadge");
    badge.hidden = false;
    badge.textContent = `${fmt(r.faltando)} falt.`;
    mostrarAba("falta");
    const extra = r.truncado ? " A lista mostra só os primeiros itens." : "";
    const dup = r.duplicados ? ` ${fmt(r.duplicados)} linha(s) com codigo repetido ignoradas.` : "";
    setStatus(`${r.situacao}${dup}${extra}`, "ok");
  }

  $("buscaFalta").addEventListener("input", renderFalta);
  $("btnExportarFalta").addEventListener("click", () => {
    const cab = ["codigo", "descricao", "barras", "preco_venda", "preco_custo", "qtd", "linha"];
    baixarCsv(
      `faltando_no_banco_${new Date().toISOString().slice(0, 10)}.csv`,
      [cab, ...itensFaltaFiltrados().map((r) => cab.map((k) => r[k]))]
    );
  });

  $("btnFaltantes").addEventListener("click", async () => {
    setStatus("Procurando códigos que faltam no banco…", "busy");
    try {
      await api("/api/faltantes", { method: "POST" });
      await acompanhar("faltantes");
    } catch (e) {
      setBusy(false);
      setStatus(`Erro ao buscar faltantes: ${e.message}`, "err");
    }
  });

  // ---------- validação de código de barras ----------
  // Liga/desliga TR_ESTOQUE_BARRAS, que chama FN_VALIDA_BARCODE a cada gravação.
  const chkBarras = $("validacaoBarras");
  const infoBarras = $("validacaoInfo");
  let barrasEstado = null;

  function pintarBarras(r) {
    barrasEstado = r;
    chkBarras.checked = Boolean(r.ativo);
    chkBarras.disabled = !r.existe;
    infoBarras.textContent = r.situacao || "";
    infoBarras.classList.toggle("muted", true);
  }

  function erroBarras(msg) {
    // volta o checkbox para o estado real: a troca não aconteceu
    if (barrasEstado) chkBarras.checked = Boolean(barrasEstado.ativo);
    infoBarras.textContent = msg;
    setStatus(msg.split("\n")[0], "err");
  }

  async function carregarBarras() {
    try {
      const r = await api("/api/validacao-barras");
      pintarBarras(r);
    } catch (e) {
      chkBarras.disabled = true;
      infoBarras.textContent = `Não foi possível ler o estado: ${e.message}`;
    }
  }

  chkBarras.addEventListener("change", async () => {
    const querAtivar = chkBarras.checked;
    chkBarras.disabled = true;
    infoBarras.textContent = querAtivar ? "Ligando validação…" : "Desligando validação…";
    try {
      const r = await api("/api/validacao-barras", { json: { ativo: querAtivar } });
      pintarBarras(r);
      setStatus(r.situacao, "ok");
    } catch (e) {
      erroBarras(e.message);
    } finally {
      chkBarras.disabled = !(barrasEstado && barrasEstado.existe);
    }
  });

  carregarBarras();

  // Mostra qual coluna do CSV alimenta o preço (de-para de PRECO_VENDA).
  api("/api/mapeamento")
    .then((m) => {
      const col = (m.mapeamento || {}).PRECO_VENDA;
      if (col) $("colPrecoDif").textContent = col;
      const colQtd = (m.mapeamento || {}).QTD_SALDO;
      if (colQtd) $("colSaldo").textContent = colQtd;
    })
    .catch(() => {});

  // Se a página foi recarregada no meio de uma operação, retoma o acompanhamento.
  fetch("/api/progresso")
    .then((r) => r.json())
    .then((p) => {
      if (p.rodando) {
        renderProgresso(p);
        const op = p.operacao;
        acompanhar(op).catch(() => {});
      }
    })
    .catch(() => {});
})();
