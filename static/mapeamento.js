(() => {
  const { esc, setStatus, loading, api, fmt, guardaSaida, marcarSujo } = window.UI;

  const state = {
    csv: null,
    colunas: [],
    campos: [],
    mapeamento: {},
    valores_padrao: {},
    valoresDb: {}, // cache: campo -> string[]
    carregandoDb: {},
    filtroMap: "todos",
    filtroOrigem: "todas",
    sujo: false,
  };

  const OUTRO = "__outro__";
  const $ = (id) => document.getElementById(id);
  const el = {
    metaOrigem: $("metaOrigem"),
    metaDestino: $("metaDestino"),
    listaOrigem: $("listaOrigem"),
    listaMap: $("listaMap"),
    buscaOrigem: $("buscaOrigem"),
    buscaMap: $("buscaMap"),
    btnSalvar: $("btnSalvar"),
    btnSugerir: $("btnSugerir"),
    btnLimpar: $("btnLimpar"),
  };

  const sel = (cls, destino) =>
    el.listaMap.querySelector(`.${cls}[data-destino="${CSS.escape(destino)}"]`);

  function setSujo(v) {
    state.sujo = v;
    marcarSujo(el.btnSalvar, v);
  }

  // ---- estado de cada campo ----
  function temPadrao(nome) {
    const v = state.valores_padrao[nome];
    return !state.mapeamento[nome] && v !== undefined && v !== "";
  }
  function estadoCampo(c) {
    if (state.mapeamento[c.nome]) return "csv";
    if (temPadrao(c.nome)) return "padrao";
    return "vazio";
  }
  function classeLinha(c) {
    const e = estadoCampo(c);
    if (e === "csv") return "mapeado";
    if (e === "padrao") return "com-padrao";
    return c.obrigatorio ? "pendente" : "";
  }

  function exemplosDe(coluna) {
    const c = state.colunas.find((x) => x.nome === coluna);
    if (!c) return "";
    return c.exemplos.length ? `ex.: ${c.exemplos.join(" · ")}` : "vazio na amostra";
  }

  function atualizarContadores() {
    const cont = { csv: 0, padrao: 0, vazios: 0, pendentes: 0 };
    for (const c of state.campos) {
      const e = estadoCampo(c);
      if (e === "csv") cont.csv++;
      else if (e === "padrao") cont.padrao++;
      else {
        cont.vazios++;
        if (c.obrigatorio) cont.pendentes++;
      }
    }
    $("cTodos").textContent = state.campos.length;
    $("cCsv").textContent = cont.csv;
    $("cPadrao").textContent = cont.padrao;
    $("cVazios").textContent = cont.vazios;
    return cont;
  }

  // ---- origem (CSV) ----
  function usosPorColuna() {
    const usos = {};
    for (const [dest, orig] of Object.entries(state.mapeamento)) {
      if (!orig) continue;
      (usos[orig] ||= []).push(dest);
    }
    return usos;
  }

  function renderOrigem() {
    const filtro = el.buscaOrigem.value.trim().toLowerCase();
    const usos = usosPorColuna();
    const html = state.colunas
      .filter((c) => !filtro || c.nome.toLowerCase().includes(filtro))
      .filter((c) => state.filtroOrigem === "todas" || !usos[c.nome])
      .map((c) => {
        const ex = c.exemplos.length ? c.exemplos.join(" · ") : "vazio na amostra";
        const u = usos[c.nome] || [];
        return `<div class="origem-item${u.length ? " usada" : ""}">
          <span class="nome" title="${esc(c.nome)}">${esc(c.nome)}</span>
          <span class="idx">#${c.indice}</span>
          <span class="ex" title="${esc(ex)}">${esc(ex)}</span>
          ${u.length ? `<span class="usos">${u.map((d) => `<span>→ ${esc(d)}</span>`).join("")}</span>` : ""}
        </div>`;
      })
      .join("");
    el.listaOrigem.innerHTML =
      html || `<div class="empty"><b>Nenhuma coluna</b>Ajuste o filtro.</div>`;
  }

  // ---- selects ----
  function opcoesOrigem(selecionado) {
    const usados = new Set(Object.values(state.mapeamento).filter(Boolean));
    const opts = ['<option value="">— nenhuma —</option>'];
    for (const c of state.colunas) {
      const s = c.nome === selecionado ? " selected" : "";
      const emUso = usados.has(c.nome) && c.nome !== selecionado ? "  (já usada)" : "";
      opts.push(`<option value="${esc(c.nome)}"${s}>${esc(c.nome)}${emUso}</option>`);
    }
    return opts.join("");
  }

  function opcoesPadraoDb(destino, valorAtual) {
    const lista = state.valoresDb[destino];
    const opts = ['<option value="">— sem padrão —</option>'];
    if (state.carregandoDb[destino]) {
      opts.push('<option value="" disabled>Carregando valores do banco…</option>');
    } else if (!lista) {
      opts.push('<option value="" disabled>Abra para carregar valores do banco</option>');
    } else if (!lista.length) {
      opts.push('<option value="" disabled>Nenhum valor no banco</option>');
    } else {
      const grupo = lista
        .map((v) => `<option value="${esc(v)}"${v === valorAtual ? " selected" : ""}>${esc(v)}</option>`)
        .join("");
      opts.push(`<optgroup label="Valores existentes no banco">${grupo}</optgroup>`);
    }
    const estaNaLista = Array.isArray(lista) && lista.includes(valorAtual);
    const usarOutro = valorAtual && !estaNaLista;
    opts.push(`<option value="${OUTRO}"${usarOutro ? " selected" : ""}>✎ Digitar valor…</option>`);
    return opts.join("");
  }

  async function carregarValoresDb(destino) {
    if (state.valoresDb[destino] || state.carregandoDb[destino]) return;
    state.carregandoDb[destino] = true;
    atualizarSelectPadrao(destino);
    try {
      const resp = await api(`/api/destino/${encodeURIComponent(destino)}/valores`);
      state.valoresDb[destino] = resp.valores || [];
    } catch (err) {
      state.valoresDb[destino] = [];
      setStatus(`Não foi possível ler valores de ${destino}: ${err.message}`, "err");
    } finally {
      delete state.carregandoDb[destino];
      atualizarSelectPadrao(destino);
    }
  }

  function atualizarSelectPadrao(destino) {
    const select = sel("padrao-select", destino);
    if (!select) return;
    const atual = state.valores_padrao[destino] || "";
    select.innerHTML = opcoesPadraoDb(destino, atual);
    const lista = state.valoresDb[destino] || [];
    const outro = sel("padrao-outro", destino);
    if (atual && !lista.includes(atual)) {
      select.value = OUTRO;
      if (outro) {
        outro.classList.remove("hidden");
        outro.value = atual;
      }
    } else {
      select.value = atual;
    }
  }

  // ---- linhas de-para ----
  function colunaPadrao(c, temOrigem, padrao) {
    if (temOrigem) return `<div class="via-csv">Usa a coluna do CSV</div>`;
    const lista = state.valoresDb[c.nome];
    const mostrarOutro = Boolean(padrao) && !(Array.isArray(lista) && lista.includes(padrao));
    return `<select class="padrao-select" data-destino="${esc(c.nome)}" aria-label="Valor padrão de ${esc(c.nome)}">
        ${opcoesPadraoDb(c.nome, padrao)}
      </select>
      <input class="padrao-outro${mostrarOutro ? "" : " hidden"}" type="text"
        data-destino="${esc(c.nome)}" value="${esc(mostrarOutro ? padrao : "")}"
        placeholder="Valor fixo para todos os produtos" aria-label="Valor digitado para ${esc(c.nome)}" />`;
  }

  function linhaHtml(c) {
    const origem = state.mapeamento[c.nome] || "";
    const padrao = state.valores_padrao[c.nome] ?? "";
    const tipo = `${c.tipo}${c.tamanho ? ` · ${c.tamanho}` : ""}`;
    return `<div class="map-row ${classeLinha(c)}" data-destino="${esc(c.nome)}">
      <div class="dest">
        <span class="dest-name">${esc(c.nome)}${c.obrigatorio ? '<span class="req">obrigatório</span>' : ""}</span>
        <span class="tipo">${esc(tipo)}</span>
      </div>
      <div>
        <select class="origem-select" data-destino="${esc(c.nome)}" aria-label="Coluna do CSV para ${esc(c.nome)}">${opcoesOrigem(origem)}</select>
        <div class="ex" title="${esc(exemplosDe(origem))}">${esc(origem ? exemplosDe(origem) : "")}</div>
      </div>
      <div class="padrao-cell">${colunaPadrao(c, Boolean(origem), padrao)}</div>
    </div>`;
  }

  function camposFiltrados() {
    const filtro = el.buscaMap.value.trim().toLowerCase();
    return state.campos.filter((c) => {
      if (filtro && !c.nome.toLowerCase().includes(filtro)) return false;
      const e = estadoCampo(c);
      if (state.filtroMap === "csv") return e === "csv";
      if (state.filtroMap === "padrao") return e === "padrao";
      if (state.filtroMap === "vazios") return e === "vazio";
      return true;
    });
  }

  function renderMap() {
    const lista = camposFiltrados();
    el.listaMap.innerHTML = lista.length
      ? lista.map(linhaHtml).join("")
      : `<div class="empty"><b>Nenhum campo neste filtro</b>Troque o filtro ou limpe a busca.</div>`;
    atualizarContadores();
  }

  function rerenderLinha(destino) {
    const row = el.listaMap.querySelector(`.map-row[data-destino="${CSS.escape(destino)}"]`);
    const c = state.campos.find((x) => x.nome === destino);
    if (!row || !c) return;
    const tmp = document.createElement("div");
    tmp.innerHTML = linhaHtml(c);
    row.replaceWith(tmp.firstElementChild);
  }

  function atualizarOpcoesOrigem() {
    el.listaMap.querySelectorAll("select.origem-select").forEach((s) => {
      const atual = s.value;
      s.innerHTML = opcoesOrigem(atual);
      s.value = atual;
    });
  }

  function aposMudanca() {
    setSujo(true);
    atualizarContadores();
    renderOrigem();
  }

  // Delegação de eventos (as linhas são recriadas com frequência).
  el.listaMap.addEventListener("change", (e) => {
    const t = e.target;
    const destino = t.dataset.destino;
    if (!destino) return;

    if (t.classList.contains("origem-select")) {
      if (t.value) {
        state.mapeamento[destino] = t.value;
        delete state.valores_padrao[destino];
      } else {
        delete state.mapeamento[destino];
      }
      rerenderLinha(destino);
      atualizarOpcoesOrigem();
      aposMudanca();
      return;
    }

    if (t.classList.contains("padrao-select")) {
      const outro = sel("padrao-outro", destino);
      if (t.value === OUTRO) {
        outro.classList.remove("hidden");
        outro.focus();
        if (outro.value === "") delete state.valores_padrao[destino];
        else state.valores_padrao[destino] = outro.value;
      } else {
        outro.classList.add("hidden");
        outro.value = "";
        if (t.value === "") delete state.valores_padrao[destino];
        else state.valores_padrao[destino] = t.value;
      }
      atualizarClasseLinha(destino);
      aposMudanca();
    }
  });

  el.listaMap.addEventListener("input", (e) => {
    const t = e.target;
    if (!t.classList.contains("padrao-outro")) return;
    const destino = t.dataset.destino;
    if (t.value === "") delete state.valores_padrao[destino];
    else state.valores_padrao[destino] = t.value;
    atualizarClasseLinha(destino);
    aposMudanca();
  });

  const carregarAoAbrir = (e) => {
    const t = e.target;
    if (t.classList && t.classList.contains("padrao-select")) carregarValoresDb(t.dataset.destino);
  };
  el.listaMap.addEventListener("focusin", carregarAoAbrir);
  el.listaMap.addEventListener("mousedown", carregarAoAbrir);

  function atualizarClasseLinha(destino) {
    const row = el.listaMap.querySelector(`.map-row[data-destino="${CSS.escape(destino)}"]`);
    const c = state.campos.find((x) => x.nome === destino);
    if (row && c) row.className = `map-row ${classeLinha(c)}`;
  }

  // ---- filtros ----
  function ligarSegmented(id, chave, render) {
    $(id).addEventListener("click", (e) => {
      const b = e.target.closest("button[data-f]");
      if (!b) return;
      state[chave] = b.dataset.f;
      $(id).querySelectorAll("button").forEach((x) =>
        x.setAttribute("aria-pressed", String(x === b))
      );
      render();
    });
  }
  ligarSegmented("filtroMap", "filtroMap", renderMap);
  ligarSegmented("filtroOrigem", "filtroOrigem", renderOrigem);
  el.buscaOrigem.addEventListener("input", renderOrigem);
  el.buscaMap.addEventListener("input", renderMap);

  // ---- carregar / ações ----
  async function sugerir() {
    return api("/api/mapeamento/sugerir", {
      json: { colunas: state.colunas.map((c) => c.nome) },
    });
  }

  async function carregarTudo() {
    try {
      const [origem, destino, map] = await Promise.all([
        api("/api/origem"),
        api("/api/destino"),
        api("/api/mapeamento"),
      ]);
      state.csv = origem.arquivo;
      state.colunas = origem.colunas;
      state.campos = destino.campos;
      state.mapeamento = map.mapeamento || {};
      state.valores_padrao = map.valores_padrao || {};
      state.valoresDb = {};

      if (!Object.keys(state.mapeamento).length && !Object.keys(state.valores_padrao).length) {
        try {
          const sug = await sugerir();
          state.mapeamento = sug.mapeamento || {};
          state.valores_padrao = sug.valores_padrao || {};
          setSujo(true);
        } catch {
          /* segue sem sugestão */
        }
      }
      for (const dest of Object.keys(state.valores_padrao)) {
        if (state.mapeamento[dest]) delete state.valores_padrao[dest];
      }

      el.metaOrigem.textContent = `${origem.nome_arquivo} · ${fmt(origem.total_linhas)} linhas`;
      el.metaDestino.textContent = `· ${destino.campos.length} campos`;
      renderOrigem();
      renderMap();
      statusPronto();
    } catch (err) {
      setStatus(`Erro ao carregar: ${err.message}. Verifique a tela de Conexão.`, "err");
    }
  }

  function statusPronto(prefixo = "") {
    const c = atualizarContadores();
    const base = `${prefixo}${c.csv} campos do CSV, ${c.padrao} com valor padrão.`;
    if (c.pendentes) {
      setStatus(`${base} Atenção: ${c.pendentes} campo(s) obrigatório(s) sem valor.`, "warn");
    } else {
      setStatus(base, prefixo ? "ok" : "");
    }
  }

  el.btnLimpar.addEventListener("click", () => {
    if (!confirm("Remover todas as ligações e valores padrão? (só é gravado ao salvar)")) return;
    state.mapeamento = {};
    state.valores_padrao = {};
    renderMap();
    renderOrigem();
    setSujo(true);
    setStatus("Mapeamento limpo. Ainda não salvo.", "warn");
  });

  el.btnSugerir.addEventListener("click", async () => {
    loading(el.btnSugerir, true);
    try {
      const sug = await sugerir();
      state.mapeamento = sug.mapeamento || {};
      state.valores_padrao = sug.valores_padrao || {};
      renderMap();
      renderOrigem();
      setSujo(true);
      statusPronto("Sugestão aplicada (não salva): ");
    } catch (err) {
      setStatus(`Falha ao sugerir: ${err.message}`, "err");
    } finally {
      loading(el.btnSugerir, false);
    }
  });

  async function salvar() {
    loading(el.btnSalvar, true);
    try {
      await api("/api/mapeamento", {
        json: {
          csv: state.csv,
          tabela_destino: "ESTOQUE",
          mapeamento: state.mapeamento,
          valores_padrao: state.valores_padrao,
        },
      });
      setSujo(false);
      statusPronto("Salvo: ");
    } catch (err) {
      setStatus(`Erro ao salvar: ${err.message}`, "err");
    } finally {
      loading(el.btnSalvar, false);
    }
  }
  el.btnSalvar.addEventListener("click", salvar);
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      salvar();
    }
  });

  guardaSaida(() => state.sujo);
  carregarTudo();
})();
