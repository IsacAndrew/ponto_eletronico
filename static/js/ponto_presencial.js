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

    function obterLocalizacao() {
        return new Promise((resolver, rejeitar) => {
            if (!navigator.geolocation) {
                rejeitar(criarErroLocalizacao("E08"));
                return;
            }

            navigator.geolocation.getCurrentPosition(
                (posicao) => resolver({
                    latitude: posicao.coords.latitude,
                    longitude: posicao.coords.longitude,
                    precisao: posicao.coords.accuracy,
                }),
                (erro) => {
                    const codigos = {
                        1: "E05",
                        2: "E06",
                        3: "E07",
                    };
                    rejeitar(criarErroLocalizacao(codigos[erro.code] || "E06"));
                },
                { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 },
            );
        });
    }

    async function registrarPonto() {
        if (tentativaEmAndamento) return;
        tentativaEmAndamento = true;
        botaoTentar.hidden = true;
        mensagem.textContent = "Confirmando sua localização…";
        mensagem.dataset.estado = "";

        try {
            const localizacao = await obterLocalizacao();
            let resposta = await enviarRegistro(localizacao);
            let resultado = await resposta.json();
            if (resultado.perguntar_quantidade_batidas) {
                const quantidade = window.prompt(
                    "Quantas batidas de ponto você possui no dia de hoje? (2, 3 ou 4)"
                );
                if (quantidade === null) {
                    mensagem.textContent = "Registro cancelado. Você pode tentar novamente quando quiser.";
                    mensagem.dataset.estado = "";
                    botaoTentar.hidden = false;
                    return;
                }
                resposta = await enviarRegistro({
                    ...localizacao,
                    quantidade_batidas_dia: quantidade.trim(),
                });
                resultado = await resposta.json();
            }
            if (!resposta.ok) {
                const erro = new Error(resultado.mensagem || "Não foi possível registrar seu ponto.");
                erro.codigoErro = resultado.codigo_erro;
                throw erro;
            }
            mensagem.textContent = resultado.confirmacao_quantidade
                ? "Ok, muito obrigado. Ponto registrado com sucesso pode fechar essa aba"
                : resultado.mensagem;
            mensagem.dataset.estado = "sucesso";
        } catch (erro) {
            mostrarErro(erro.codigoErro
                ? `Erro ${erro.codigoErro} - Informe o Isac sobre este código.`
                : erro.message);
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

    function criarErroLocalizacao(codigo) {
        const erro = new Error(`Erro ${codigo} - Informe o Isac sobre este código.`);
        erro.codigoErro = codigo;
        return erro;
    }

    atualizarRelogio();
    window.setInterval(atualizarRelogio, 1000);
    botaoTentar.addEventListener("click", registrarPonto);
    registrarPonto();
})();
