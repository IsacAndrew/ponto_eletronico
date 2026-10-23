const relogioDigital = document.querySelector("#relogio-digital");
const botaoRegistrar = document.querySelector("#botao-registrar");
const ultimoRegistro = document.querySelector("#ultimo-registro");

function atualizarRelogio() {
    const horarioAtual = new Date();
    relogioDigital.textContent = horarioAtual.toLocaleTimeString("pt-BR", {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });
}

async function registrarPonto() {
    botaoRegistrar.disabled = true;

    try {
        const localizacao = await obterLocalizacao();
        let resposta = await enviarRegistro(localizacao);
        let resultado = await resposta.json();

        if (resultado.perguntar_quantidade_batidas) {
            const quantidade = window.prompt(
                "Quantas batidas de ponto você possui no dia de hoje? (2, 3 ou 4)"
            );
            if (quantidade === null) return;
            resposta = await enviarRegistro({
                ...localizacao,
                quantidade_batidas_dia: quantidade.trim(),
            });
            resultado = await resposta.json();
        }

        if (!resposta.ok) {
            throw new Error(resultado.mensagem || "Não foi possível registrar o ponto.");
        }

        ultimoRegistro.textContent = `Último registro: ${resultado.horario} / ${resultado.tipo_batida}`;
        if (resultado.confirmacao_quantidade) {
            window.alert("Ok, muito obrigado. Ponto registrado com sucesso pode fechar essa aba");
        }
    } catch (erro) {
        window.alert(mensagemErroPonto(erro));
    } finally {
        botaoRegistrar.disabled = false;
    }
}

function enviarRegistro(dados) {
    return fetch("/registrar-ponto", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(dados),
    });
}

function obterLocalizacao() {
    return new Promise((resolver, rejeitar) => {
        if (!navigator.geolocation) {
            rejeitar(new Error("Este navegador não disponibiliza a localização do aparelho."));
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
                    1: "Permita o acesso à localização nas configurações do navegador e tente novamente.",
                    2: "O aparelho não conseguiu obter a localização. Confira se o GPS está ativado e tente novamente.",
                    3: "A localização demorou para responder. Tente novamente em alguns segundos.",
                };
                rejeitar(new Error(mensagens[erro.code] || "Não foi possível obter a localização. Confira o GPS e tente novamente."));
            },
            { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 },
        );
    });
}

function mensagemErroPonto(erro) {
    return erro.message;
}

atualizarRelogio();
window.setInterval(atualizarRelogio, 1000);
botaoRegistrar.addEventListener("click", registrarPonto);
