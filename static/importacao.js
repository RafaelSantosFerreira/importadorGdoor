(() => {
  const { esc, setStatus, api, fmt, baixarCsv } = window.UI;
  const $ = (id) => document.getElementById(id);

  const card = $("cardProgresso");
  const botoes = ["btnDifBuscar", "btnDifAplicar",
                  "btnSalBuscar", "btnSalAplicar", "btnFaltantes",
                  "btnNcmPrevia", "btnNcmAplicar", "btnBackup"].map($);

  let pollTimer = null;

  // ---------- util ----------
  function setBusy(busy) {
    botoes.forEach((b) => (b.disabled = busy));
  }

  const ABAS = {
    dif: ["tabDif", "painelDif"],
    sal: ["tabSal", "painelSal"],
    falta: ["tabFalta", "painelFalta"],
    ncm: ["tabNcm", "painelNcm"],
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
      ncm_previa: "Prévia da inserção",
      ncm_aplicar: "Inserção de faltantes",
      backup: "Backup",
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
        else if (operacao === "ncm_previa" || operacao === "ncm_aplicar") concluirNcm(r);
        else if (operacao === "backup") concluirBackup(r);
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
      if (r.gravado) ultimaBusca = null;
      const banner = r.gravado
        ? ["ok", "Gravado no banco", r.situacao || ""]
        : ["err", "Nada foi gravado", r.situacao || ""];
      aplicarResultado(r, banner);
      if (r.erros && (r.log || []).length) {
        const linhas = (r.log || [])
          .slice(0, 20)
          .map((l) => `<div class="${l.startsWith("ERRO") ? "l-erro" : "l-update"}">${esc(l)}</div>`)
          .join("");
        $(cfg.banner).innerHTML += `<div class="log-box" style="margin:0.6rem 1rem 0">${linhas}</div>`;
      }
      const resumo = `${fmt(r.atualizados)} alterado(s), ${fmt(r.pulados)} pulado(s), ${fmt(r.erros)} erro(s).`;
      setStatus(r.gravado ? `Gravado: ${resumo}` : `Nada gravado: ${resumo}`, r.gravado ? "ok" : "err");
    }

    async function rodarAplicar() {
      setStatus(`Gravando ${cfg.rotulo} do CSV…`, "busy");
      try {
        await api(cfg.endpointAplicar, { json: { dry_run: false } });
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
      if (confirm(msg)) rodarAplicar();
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
    btnBuscar: "btnDifBuscar", btnAplicar: "btnDifAplicar",
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
    btnBuscar: "btnSalBuscar", btnAplicar: "btnSalAplicar",
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

  // ---------- backup do banco ----------
  const mb = (n) => `${(Number(n) / 1024 / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB`;

  function renderBackups(lista) {
    const el = $("listaBackups");
    if (!lista || !lista.length) {
      el.textContent = "Nenhum backup feito por esta tela ainda.";
      return;
    }
    el.innerHTML =
      `<b>Últimos backups</b><div class="log-box" style="margin-top:0.4rem;max-height:160px">` +
      lista
        .map((b) => `<div class="l-update">${esc(b.data)} · ${esc(b.nome)} · ${esc(mb(b.tamanho))}</div>`)
        .join("") +
      `</div>`;
  }

  function concluirBackup(r) {
    renderBackups(r.backups);
    setStatus(`${r.situacao} Arquivo: ${r.arquivo}`, "ok");
  }

  api("/api/backup")
    .then((r) => renderBackups(r.backups))
    .catch((e) => ($("listaBackups").textContent = `Não foi possível listar os backups: ${e.message}`));

  $("btnBackup").addEventListener("click", async () => {
    setStatus("Gerando backup do banco…", "busy");
    try {
      await api("/api/backup", { method: "POST" });
      await acompanhar("backup");
    } catch (e) {
      setBusy(false);
      setStatus(`Erro no backup: ${e.message}`, "err");
    }
  });

  // ---------- inserir faltantes copiando produto do mesmo NCM ----------
  const tbodyNcm = document.querySelector("#tabelaNcm tbody");
  let itensNcm = [];
  let logNcm = [];
  let ultimaPrevia = null;
  // {codigo_csv: codigo_modelo} digitados na coluna Modelo.
  const escolhasNcm = {};

  function itensNcmFiltrados() {
    const q = $("buscaNcm").value.trim().toLowerCase();
    const soSem = $("soSemModelo").checked;
    return itensNcm.filter(
      (r) =>
        (!soSem || !r.pronto) &&
        (!q ||
          r.codigo.toLowerCase().includes(q) ||
          (r.descricao || "").toLowerCase().includes(q) ||
          (r.ncm || "").includes(q))
    );
  }

  function renderNcm() {
    const items = itensNcmFiltrados();
    $("infoNcm").textContent = itensNcm.length ? `${fmt(items.length)} de ${fmt(itensNcm.length)} itens` : "";
    if (!items.length) {
      tbodyNcm.innerHTML = `<tr><td colspan="8"><div class="empty"><b>${
        itensNcm.length ? "Nada neste filtro" : "Nenhum código faltando"
      }</b>${itensNcm.length ? "Limpe a busca para ver todos." : "Todo código do CSV já existe no banco."}</div></td></tr>`;
      return;
    }
    tbodyNcm.innerHTML = items
      .map((r) => {
        const valor = escolhasNcm[r.codigo] ?? r.modelo ?? "";
        const desc = r.modelo_descricao
          ? `<div class="muted" style="font-size:0.78rem">${esc(r.modelo_descricao)}${
              r.origem_modelo === "escolhido" ? " · escolhido" : ""
            }</div>`
          : "";
        const tag = r.pronto
          ? `<span class="tag novo">insere</span>`
          : `<span class="tag ambos">${esc(r.motivo)}</span>`;
        const avisos = (r.avisos || []).map((a) => ` <span class="tag preco">${esc(a)}</span>`).join("");
        return `<tr>
          <td class="code">${esc(r.codigo_banco || r.codigo)}</td>
          <td>${esc(r.descricao)}</td>
          <td class="code">${esc(r.ncm || "—")}</td>
          <td class="code">${esc(r.barras || "—")}</td>
          <td class="num">${esc(r.preco_venda || "—")}</td>
          <td class="num">${esc(r.qtd || "—")}</td>
          <td><input type="text" class="modelo-ncm" data-codigo="${esc(r.codigo)}" value="${esc(valor)}"
                placeholder="código" size="8" aria-label="Produto modelo para ${esc(r.codigo)}" />${desc}</td>
          <td>${tag}${avisos}</td>
        </tr>`;
      })
      .join("");
  }

  tbodyNcm.addEventListener("change", (e) => {
    const el = e.target.closest(".modelo-ncm");
    if (!el) return;
    const codigo = el.dataset.codigo;
    const valor = el.value.trim();
    const item = itensNcm.find((r) => r.codigo === codigo);
    if (valor && !(item && item.origem_modelo === "ncm" && valor === item.modelo)) escolhasNcm[codigo] = valor;
    else delete escolhasNcm[codigo];
    setStatus("Modelo alterado. Clique em “Prévia” para conferir antes de inserir.", "warn");
  });

  function concluirNcm(r) {
    const aplicar = r.modo === "ncm_aplicar";
    if (!aplicar) ultimaPrevia = r;
    else if (r.gravado) ultimaPrevia = null;
    $("nTotal").textContent = fmt(r.linhas_csv);
    $("nFalta").textContent = fmt(r.faltando);
    $("nCom").textContent = fmt(r.com_modelo);
    $("nSem").textContent = fmt(r.sem_modelo);
    $("nIns").textContent = aplicar ? fmt(r.inseridos) : "—";
    itensNcm = r.itens || [];
    logNcm = r.log || [];
    $("toolbarNcm").hidden = !itensNcm.length;
    renderNcm();

    let banner = null;
    if (aplicar) {
      banner = r.gravado ? ["ok", "Gravado no banco", r.situacao] : ["err", "Nada foi gravado", r.situacao];
    } else if (r.sem_modelo) {
      banner = ["err", `${r.sem_modelo} produto(s) sem modelo`,
        "Sem produto ativo com o mesmo NCM (ou o modelo digitado não existe). Digite na coluna Modelo o código de um produto para copiar e rode a prévia de novo; senão eles ficam de fora. O motivo de cada um está no log abaixo."];
    }
    let html = banner
      ? `<div class="banner ${banner[0]}" style="margin:1rem 1rem 0"><div><b>${esc(banner[1])}</b><span>${esc(banner[2])}</span></div></div>`
      : "";
    if (logNcm.length) {
      const linhas = logNcm
        .slice(0, 50)
        .map((l) => `<div class="${l.startsWith("INSERT") ? "l-insert" : l.startsWith("ERRO") || l.startsWith("SEM") ? "l-erro" : "l-update"}">${esc(l)}</div>`)
        .join("");
      html += `<div class="log-box" style="margin:0.6rem 1rem 0">${linhas}${
        logNcm.length > 50 ? `<div class="muted">… mais ${fmt(logNcm.length - 50)} linha(s) no “Baixar log CSV”.</div>` : ""
      }</div>`;
    }
    $("bannerNcm").innerHTML = html;

    const badge = $("ncmBadge");
    badge.hidden = false;
    badge.textContent = `${fmt(r.faltando)} falt.`;
    mostrarAba("ncm");
    const ok = !(r.erros || (aplicar && !r.gravado));
    setStatus(r.situacao || "", ok ? "ok" : "err");
  }

  $("buscaNcm").addEventListener("input", renderNcm);
  $("soSemModelo").addEventListener("change", renderNcm);
  $("btnExportarNcm").addEventListener("click", () => {
    const cab = ["codigo", "codigo_banco", "descricao", "ncm", "barras", "preco_venda", "qtd",
                 "modelo", "modelo_descricao", "origem_modelo", "pronto", "motivo"];
    baixarCsv(`inserir_por_ncm_${new Date().toISOString().slice(0, 10)}.csv`, [
      cab,
      ...itensNcmFiltrados().map((r) => cab.map((k) => r[k])),
    ]);
  });

  async function rodarNcm(endpoint, json, operacao, msg) {
    setStatus(msg, "busy");
    try {
      await api(endpoint, { json });
      await acompanhar(operacao);
    } catch (e) {
      setBusy(false);
      setStatus(`Erro: ${e.message}`, "err");
    }
  }

  $("btnNcmPrevia").addEventListener("click", () =>
    rodarNcm("/api/faltantes/ncm/previa", { escolhas: escolhasNcm }, "ncm_previa", "Procurando modelos por NCM…")
  );
  $("btnNcmAplicar").addEventListener("click", () => {
    const b = ultimaPrevia;
    const info = b
      ? `\n\nNa última prévia: ${fmt(b.com_modelo)} serão inseridos, ${fmt(b.sem_modelo)} ficam de fora (sem modelo).`
      : "\n\n⚠ Você ainda não rodou a prévia.";
    const msg =
      "Inserir no ESTOQUE os produtos que faltam, copiando o produto do mesmo NCM?" +
      `${info}\n\nSe houver qualquer erro, nada será gravado.`;
    if (confirm(msg))
      rodarNcm("/api/faltantes/ncm/aplicar", { dry_run: false, escolhas: escolhasNcm }, "ncm_aplicar",
               "Inserindo faltantes…");
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
