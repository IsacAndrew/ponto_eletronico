(() => {
    const pagina = document.querySelector("[data-registro-url]");
    if (!pagina) return;

    const relogio = pagina.querySelector("[data-relogio]");
    const mensagem = pagina.querySelector("[data-mensagem]");
    const botaoTentar = pagina.querySelector("[data-tentar]");
    let tentativaEmAndamento = false;

    function atualizarRelogio() {
        relogio.textContent = new Date().toLocaleTimeString("pt-BR", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
        });
    }

    function mostrarErro(texto) {
        mensagem.textContent = texto;
        mensagem.dataset.estado = "erro";
        botaoTentar.hidden = false;
    }

    async function registrarPonto() {
        if (tentativaEmAndamento) return;
        tentativaEmAndamento = true;
        botaoTentar.hidden = true;
        mensagem.textContent = "Registrando seu ponto…";
        mensagem.dataset.estado = "";

        try {
            const dadosRegistro = {};
            let resposta = await enviarRegistro(dadosRegistro);
            let resultado = await resposta.json();
            if (resultado.perguntar_quantidade_batidas) {
                const confirmou = window.confirm("Você possui 4 batidas de ponto no dia de hoje?");
                if (!confirmou) {
                    mostrarErro("As 2 batidas de hoje já foram registradas. Se você acredita que há algo errado, fale com o Isac.");
                    return;
                }
                const quantidades = await window.abrirAjusteBatidas(resultado.quantidades_semanais);
                if (!quantidades) {
                    mensagem.textContent = "Ajuste cancelado. Nenhum ponto foi registrado.";
                    mensagem.dataset.estado = "";
                    botaoTentar.hidden = false;
                    return;
                }
                resposta = await enviarRegistro({
                    ...dadosRegistro,
                    quatro_batidas_hoje: true,
                    quantidades_semanais: quantidades,
                });
                resultado = await resposta.json();
            }
            if (!resposta.ok) {
                throw new Error(resultado.mensagem || "Não foi possível registrar seu ponto.");
            }
            mensagem.textContent = resultado.confirmacao_quantidade
                ? "Ponto registrado com sucesso."
                : resultado.mensagem;
            mensagem.dataset.estado = "sucesso";
        } catch (erro) {
            mostrarErro(erro.message);
        } finally {
            tentativaEmAndamento = false;
        }
    }

    function enviarRegistro(dados) {
        return fetch(pagina.dataset.registroUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(dados),
        });
    }

    atualizarRelogio();
    window.setInterval(atualizarRelogio, 1000);
    botaoTentar.addEventListener("click", registrarPonto);
    registrarPonto();
})();
