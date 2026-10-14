const cartaoPontoHoje = document.querySelector(".cartao-ponto-hoje");

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
