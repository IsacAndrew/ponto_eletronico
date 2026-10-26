(() => {
    const mes = document.querySelector("#mes");
    const ano = document.querySelector("#ano");
    if (!mes || !ano) return;
    const meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
    const resumoMes = document.querySelector("[data-resumo-mes-ano]");
    const resumoMesCabecalho = document.querySelector("[data-resumo-mes]");

    function atualizarMes() {
        const texto = `${meses[Number(mes.value) - 1]} / ${ano.value}`;
        resumoMes.textContent = texto;
        resumoMesCabecalho.textContent = texto;
    }

    [mes, ano].forEach((campo) => campo.addEventListener("input", atualizarMes));
    [mes, ano].forEach((campo) => campo.addEventListener("change", atualizarMes));
    atualizarMes();

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
