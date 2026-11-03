(() => {
  const { setStatus, loading, api, fmt, guardaSaida, marcarSujo } = window.UI;
  const fields = [
    "host",
    "port",
    "database",
    "user",
    "password",
    "charset",
    "csv",
    "csv_encoding",
    "csv_delimiter",
  ];
  const btnSalvar = document.getElementById("btnSalvar");
  const btnTestar = document.getElementById("btnTestar");
  let sujo = false;

  function setSujo(v) {
    sujo = v;
    marcarSujo(btnSalvar, v);
  }

  function lerForm() {
    const data = {};
    for (const id of fields) {
      const el = document.getElementById(id);
      data[id] = el.type === "number" ? Number(el.value) : el.value;
    }
    return data;
  }

  function preencher(data) {
    for (const id of fields) {
      const el = document.getElementById(id);
      if (data[id] == null) continue;
      if (el.tagName === "SELECT" && ![...el.options].some((o) => o.value === data[id])) {
        el.add(new Option(`Outro ( ${data[id]} )`, data[id]));
      }
      el.value = data[id];
    }
  }

  async function carregar() {
    try {
      preencher(await api("/api/conexao"));
      setSujo(false);
      setStatus("Configuração carregada. Teste a conexão antes de seguir para o De-para.");
    } catch (e) {
      setStatus(`Erro ao carregar: ${e.message}`, "err");
    }
  }

  async function salvar() {
    loading(btnSalvar, true);
    try {
      await api("/api/conexao", { json: lerForm() });
      setSujo(false);
      setStatus("Configuração salva.", "ok");
    } catch (e) {
      setStatus(`Erro ao salvar: ${e.message}`, "err");
    } finally {
      loading(btnSalvar, false);
    }
  }

  async function testar() {
    loading(btnTestar, true);
    setStatus("Testando conexão com o Firebird…", "busy");
    document.getElementById("cardTeste").hidden = true;
    try {
      const r = await api("/api/conexao/testar", { json: lerForm() });
      document.getElementById("tUsuario").textContent = r.usuario || "—";
      document.getElementById("tTabelas").textContent = fmt(r.tabelas);
      document.getElementById("tEstoque").textContent = fmt(r.estoque);
      document.getElementById("testeQuando").textContent =
        "às " + new Date().toLocaleTimeString("pt-BR");
      document.getElementById("cardTeste").hidden = false;
      setStatus(
        sujo
          ? "Conexão OK. Lembre de salvar as alterações."
          : "Conexão OK.",
        sujo ? "warn" : "ok"
      );
    } catch (e) {
      setStatus(`Falha na conexão: ${e.message}`, "err");
    } finally {
      loading(btnTestar, false);
    }
  }

  document.getElementById("form").addEventListener("input", () => setSujo(true));
  document.getElementById("form").addEventListener("change", () => setSujo(true));
  btnSalvar.addEventListener("click", salvar);
  btnTestar.addEventListener("click", testar);

  const btnVer = document.getElementById("btnVerSenha");
  btnVer.addEventListener("click", () => {
    const pwd = document.getElementById("password");
    const mostrar = pwd.type === "password";
    pwd.type = mostrar ? "text" : "password";
    btnVer.textContent = mostrar ? "Ocultar" : "Mostrar";
    btnVer.setAttribute("aria-label", mostrar ? "Ocultar senha" : "Mostrar senha");
  });

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      salvar();
    }
  });

  guardaSaida(() => sujo);
  carregar();
})();
