(() => {
    const seletorPeriodo = document.querySelector("#periodo");
    if (!seletorPeriodo) return;

    const referenciaSemana = document.querySelector("#data-referencia");
    const dataInicio = document.querySelector("#data-inicio");
    const dataFim = document.querySelector("#data-fim");
    const mes = document.querySelector("#mes");
    const ano = document.querySelector("#ano");
    const previa = document.querySelector("[data-period-preview]");
    const formatar = (data) => new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" }).format(data);

    function atualizarPeriodo() {
        const tipo = seletorPeriodo.value;
        document.querySelectorAll("[data-period-field]").forEach((campo) => {
            const visivel = campo.dataset.periodField === tipo;
            campo.hidden = !visivel;
            campo.querySelectorAll("input").forEach((input) => input.required = visivel);
        });
        let texto = "";
        if (tipo === "dia" && dataInicio.value && dataFim.value) {
            texto = `Período de ${formatar(new Date(`${dataInicio.value}T12:00:00`))} a ${formatar(new Date(`${dataFim.value}T12:00:00`))}`;
        } else if (tipo === "semana" && referenciaSemana.value) {
            const data = new Date(`${referenciaSemana.value}T12:00:00`);
            const inicio = new Date(data);
            inicio.setDate(data.getDate() - data.getDay());
            const fim = new Date(inicio);
            fim.setDate(inicio.getDate() + 6);
            texto = `Semana de ${formatar(inicio)} a ${formatar(fim)}`;
        } else if (tipo === "mes" && mes.value) {
            const [y, m] = mes.value.split("-").map(Number);
            const ultimoDia = new Date(y, m, 0).getDate();
            texto = `Período de 01/${String(m).padStart(2,"0")}/${y} a ${ultimoDia}/${String(m).padStart(2,"0")}/${y}`;
        } else if (tipo === "ano" && ano.value) {
            texto = `Período de 01/01/${ano.value} a 31/12/${ano.value}`;
        }
        previa.textContent = texto;
    }

    [seletorPeriodo, referenciaSemana, dataInicio, dataFim, mes, ano].forEach((campo) => {
        campo.addEventListener("input", atualizarPeriodo);
        campo.addEventListener("change", atualizarPeriodo);
    });
    atualizarPeriodo();

    const campoBusca = document.querySelector("#busca-colaborador");
    const listaUsuarios = document.querySelector(".lista-colaboradores");
    if (!campoBusca || !listaUsuarios) return;
    const caixas = [...listaUsuarios.querySelectorAll('input[name="escopo"]')];
    const caixaTodos = caixas.find((caixa) => caixa.value === "todos");
    const caixasIndividuais = caixas.filter((caixa) => caixa !== caixaTodos);
    const resumo = document.querySelector("[data-resumo-colaboradores]");
    const resumoCabecalho = document.querySelector("[data-resumo-colaboradores-cabecalho]");
    const semResultados = listaUsuarios.querySelector(".sem-colaboradores");

    function atualizarSelecao() {
        if (caixaTodos.checked) caixasIndividuais.forEach((caixa) => caixa.checked = false);
        else if (!caixasIndividuais.some((caixa) => caixa.checked)) caixaTodos.checked = true;
        const selecionados = caixasIndividuais.filter((caixa) => caixa.checked);
        const textoResumo = caixaTodos.checked
            ? "Todos os usuários selecionados"
            : `${selecionados.length} usuário${selecionados.length === 1 ? "" : "s"} selecionado${selecionados.length === 1 ? "" : "s"}`;
        resumo.textContent = textoResumo;
        resumoCabecalho.textContent = textoResumo;
    }

    campoBusca.addEventListener("input", () => {
        const termo = campoBusca.value.trim().toLocaleLowerCase("pt-BR");
        let encontrados = 0;
        listaUsuarios.querySelectorAll("[data-nome-colaborador]").forEach((opcao) => {
            const corresponde = opcao.dataset.nomeColaborador.includes(termo);
            opcao.hidden = !corresponde;
            if (corresponde) encontrados += 1;
        });
        semResultados.hidden = encontrados !== 0;
    });
    caixas.forEach((caixa) => caixa.addEventListener("change", () => {
        if (caixa === caixaTodos && caixa.checked) caixasIndividuais.forEach((item) => item.checked = false);
        else if (caixa !== caixaTodos && caixa.checked) caixaTodos.checked = false;
        atualizarSelecao();
    }));
    atualizarSelecao();
})();
