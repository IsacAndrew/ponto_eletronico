(() => {
    const janela = document.querySelector("[data-ajuste-batidas]");
    if (!janela) return;

    const dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
    const conteiner = janela.querySelector("[data-dias-ajuste-batidas]");
    const botaoCancelar = janela.querySelector("[data-cancelar-ajuste]");
    const botaoSalvar = janela.querySelector("[data-salvar-ajuste]");
    let quantidades = [];
    let resolver;

    function desenharDias() {
        conteiner.replaceChildren();
        dias.forEach((dia, indice) => {
            const cartao = document.createElement("article");
            cartao.className = "dia-ajuste-batidas";
            cartao.innerHTML = `
                <strong>${dia}</strong>
                <button type="button" aria-label="Aumentar batidas de ${dia}" data-aumentar="${indice}">⌃</button>
                <span>${quantidades[indice]}</span>
                <button type="button" aria-label="Diminuir batidas de ${dia}" data-diminuir="${indice}">⌄</button>
            `;
            conteiner.append(cartao);
        });
    }

    function alterarQuantidade(indice, direcao) {
        const valores = [0, 2, 4];
        const atual = valores.indexOf(quantidades[indice]);
        const proximo = Math.max(0, Math.min(valores.length - 1, atual + direcao));
        quantidades[indice] = valores[proximo];
        desenharDias();
    }

    function fechar(resultado) {
        janela.close();
        if (resolver) resolver(resultado);
        resolver = null;
    }

    conteiner.addEventListener("click", (evento) => {
        const aumentar = evento.target.closest("[data-aumentar]");
        const diminuir = evento.target.closest("[data-diminuir]");
        if (aumentar) alterarQuantidade(Number(aumentar.dataset.aumentar), 1);
        if (diminuir) alterarQuantidade(Number(diminuir.dataset.diminuir), -1);
    });
    botaoCancelar.addEventListener("click", () => fechar(null));
    botaoSalvar.addEventListener("click", () => fechar([...quantidades]));
    janela.addEventListener("cancel", (evento) => {
        evento.preventDefault();
        fechar(null);
    });

    window.abrirAjusteBatidas = (valoresIniciais) => new Promise((resolve) => {
        quantidades = valoresIniciais.map((quantidade) => [0, 2, 4].includes(quantidade) ? quantidade : 0);
        resolver = resolve;
        desenharDias();
        janela.showModal();
    });
})();
