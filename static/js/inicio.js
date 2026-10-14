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
        const resposta = await fetch("/registrar-ponto", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(localizacao),
        });
        const resultado = await resposta.json();

        if (!resposta.ok) {
            throw new Error(resultado.mensagem || "Não foi possível registrar o ponto.");
        }

        ultimoRegistro.textContent = `Último registro: ${resultado.horario} / ${resultado.tipo_batida}`;
    } catch (erro) {
        window.alert(erro.message);
    } finally {
        botaoRegistrar.disabled = false;
    }
}

function obterLocalizacao() {
    return new Promise((resolver, rejeitar) => {
        if (!navigator.geolocation) {
            rejeitar(new Error("Este navegador não oferece acesso à localização."));
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
                    1: "Permita o acesso à localização para registrar o ponto.",
                    2: "Não foi possível determinar sua localização. Verifique o GPS e tente novamente.",
                    3: "A localização demorou demais. Tente novamente.",
                };
                rejeitar(new Error(mensagens[erro.code] || "Falha ao obter sua localização."));
            },
            { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 },
        );
    });
}

atualizarRelogio();
window.setInterval(atualizarRelogio, 1000);
botaoRegistrar.addEventListener("click", registrarPonto);
