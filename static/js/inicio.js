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
            const erro = new Error(resultado.mensagem || "Não foi possível registrar o ponto.");
            erro.codigoErro = resultado.codigo_erro;
            throw erro;
        }

        ultimoRegistro.textContent = `Último registro: ${resultado.horario} / ${resultado.tipo_batida}`;
    } catch (erro) {
        window.alert(mensagemErroPonto(erro));
    } finally {
        botaoRegistrar.disabled = false;
    }
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

function criarErroLocalizacao(codigo) {
    const erro = new Error(`Erro ${codigo} - Informe o Isac sobre este código.`);
    erro.codigoErro = codigo;
    return erro;
}

function mensagemErroPonto(erro) {
    return erro.codigoErro
        ? `Erro ${erro.codigoErro} - Informe o Isac sobre este código.`
        : erro.message;
}

atualizarRelogio();
window.setInterval(atualizarRelogio, 1000);
botaoRegistrar.addEventListener("click", registrarPonto);
