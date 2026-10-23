const cartaoPontoHoje = document.querySelector(".cartao-ponto-hoje");
const campoDataPonto = document.querySelector("#data-ponto-hoje");

if (campoDataPonto) {
    campoDataPonto.addEventListener("input", () => {
        const digitos = campoDataPonto.value.replace(/\D/g, "").slice(0, 8);
        if (digitos.length <= 2) {
            campoDataPonto.value = digitos;
        } else if (digitos.length <= 4) {
            campoDataPonto.value = `${digitos.slice(0, 2)}-${digitos.slice(2)}`;
        } else {
            campoDataPonto.value = `${digitos.slice(0, 2)}-${digitos.slice(2, 4)}-${digitos.slice(4)}`;
        }
    });
}

function dataAtualDaEscola() {
    const partes = new Intl.DateTimeFormat("en-CA", {
        timeZone: "America/Sao_Paulo",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    }).formatToParts(new Date());
    const valores = Object.fromEntries(partes.map((parte) => [parte.type, parte.value]));
    return `${valores.year}-${valores.month}-${valores.day}`;
}

window.setInterval(() => {
    if (dataAtualDaEscola() !== cartaoPontoHoje.dataset.dataHoje) {
        window.location.reload();
    }
}, 15000);

window.setInterval(() => window.location.reload(), 60000);
