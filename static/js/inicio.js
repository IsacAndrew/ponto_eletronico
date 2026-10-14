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
        const resposta = await fetch("/registrar-ponto", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
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

atualizarRelogio();
window.setInterval(atualizarRelogio, 1000);
botaoRegistrar.addEventListener("click", registrarPonto);
