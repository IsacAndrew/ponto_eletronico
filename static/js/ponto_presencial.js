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
                rejeitar(new Error("Este navegador não permite acessar a localização."));
                return;
            }

            navigator.geolocation.getCurrentPosition(
                (posicao) => resolver({
                    latitude: posicao.coords.latitude,
                    longitude: posicao.coords.longitude,
                    precisao: posicao.coords.accuracy,
                }),
                (erro) => {
                    const mensagens = {
                        1: "Permita o acesso à localização para registrar seu ponto.",
                        2: "Não foi possível obter sua localização. Verifique o GPS.",
                        3: "A localização demorou. Tente novamente.",
                    };
                    rejeitar(new Error(mensagens[erro.code] || "Não foi possível obter sua localização."));
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
            const resposta = await fetch(pagina.dataset.registroUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(localizacao),
            });
            const resultado = await resposta.json();
            if (!resposta.ok) {
                throw new Error(resultado.mensagem || "Não foi possível registrar seu ponto.");
            }
            mensagem.textContent = resultado.mensagem;
            mensagem.dataset.estado = "sucesso";
        } catch (erro) {
            mostrarErro(erro.message);
        } finally {
            tentativaEmAndamento = false;
        }
    }

    atualizarRelogio();
    window.setInterval(atualizarRelogio, 1000);
    botaoTentar.addEventListener("click", registrarPonto);
    registrarPonto();
})();
