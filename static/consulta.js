(() => {
  const { esc, setStatus, api, fmt, baixarCsv } = window.UI;
  const $ = (id) => document.getElementById(id);

  // Mesma tabela para a busca e para o SELECT livre: colunas vêm no resultado.
  function criarTabela(cfg) {
    const tabela = $(cfg.tabela);
    const thead = tabela.querySelector("thead tr");
    const tbody = tabela.querySelector("tbody");
    let colunas = [];
    let linhas = [];

    function render(r) {
      colunas = r.colunas || [];
      linhas = r.linhas || [];
      const vazio = cfg.vazio;

      if (!colunas.length || !linhas.length) {
        thead.innerHTML = "<th>Resultado</th>";
        tbody.innerHTML = `<tr><td><div class="empty"><b>Nada encontrado</b>${esc(vazio)}</div></td></tr>`;
      } else {
        thead.innerHTML = colunas.map((c) => `<th>${esc(c)}</th>`).join("");
        tbody.innerHTML = linhas
          .map(
            (linha) =>
              "<tr>" +
              linha
                .map((v, i) => {
                  const cls = i === 0 ? "code" : /^-?[\d.,]+$/.test(v || "") ? "num" : "";
                  return `<td class="${cls}">${v === null ? '<span class="muted">null</span>' : esc(v)}</td>`;
                })
                .join("") +
              "</tr>"
          )
          .join("");
      }

      if (cfg.toolbar) $(cfg.toolbar).hidden = !linhas.length;
      const truncado = r.truncado ? ` (limite de ${fmt(r.limite)} atingido)` : "";
      $(cfg.info).textContent = linhas.length
        ? `${fmt(linhas.length)} linha(s)${truncado}`
        : "nenhuma linha";
    }

    function exportar() {
      if (!linhas.length) return;
      baixarCsv(`${cfg.arquivo}_${new Date().toISOString().slice(0, 10)}.csv`, [colunas, ...linhas]);
    }

    return { render, exportar, temLinhas: () => linhas.length > 0 };
  }

  const tabBusca = criarTabela({
    tabela: "tabelaBusca",
    info: "infoBusca",
    toolbar: "toolbarBusca",
    arquivo: "estoque",
    vazio: "Nenhum produto bate com esse termo.",
  });

  const tabSql = criarTabela({
    tabela: "tabelaSql",
    info: "infoSql",
    arquivo: "consulta",
    vazio: "A consulta não devolveu linhas.",
  });

  // ---------- busca no estoque ----------
  async function buscar() {
    const termo = $("termo").value.trim();
    $("btnBuscar").disabled = true;
    setStatus(termo ? `Buscando “${termo}”…` : "Listando o estoque…", "busy");
    try {
      const r = await api("/api/consulta/estoque", {
        json: { termo, limite: Number($("limiteBusca").value) || 200 },
      });
      tabBusca.render(r);
      const extra = r.truncado ? ` Mostrando os primeiros ${fmt(r.limite)}.` : "";
      setStatus(
        r.total ? `${fmt(r.total)} produto(s) encontrado(s).${extra}` : "Nenhum produto encontrado.",
        "ok"
      );
    } catch (e) {
      setStatus(`Erro na busca: ${e.message}`, "err");
    } finally {
      $("btnBuscar").disabled = false;
    }
  }

  $("btnBuscar").addEventListener("click", buscar);
  $("termo").addEventListener("keydown", (e) => {
    if (e.key === "Enter") buscar();
  });
  $("btnExportarBusca").addEventListener("click", () => tabBusca.exportar());

  // ---------- SELECT livre ----------
  async function executar() {
    const sql = $("sql").value.trim();
    if (!sql) {
      setStatus("Escreva uma consulta.", "err");
      return;
    }
    $("btnExecutar").disabled = true;
    setStatus("Executando…", "busy");
    try {
      const r = await api("/api/consulta/sql", {
        json: { sql, limite: Number($("limiteSql").value) || 200 },
      });
      tabSql.render(r);
      const extra = r.truncado ? ` Mostrando as primeiras ${fmt(r.limite)}.` : "";
      setStatus(`${fmt(r.total)} linha(s).${extra}`, "ok");
    } catch (e) {
      tabSql.render({ colunas: [], linhas: [] });
      $("infoSql").textContent = e.message;
      setStatus(e.message, "err");
    } finally {
      $("btnExecutar").disabled = false;
    }
  }

  $("btnExecutar").addEventListener("click", executar);
  // Ctrl+Enter executa, como na maioria dos editores de SQL
  $("sql").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      executar();
    }
  });
  $("btnExportarSql").addEventListener("click", () => tabSql.exportar());

  buscar();
})();
