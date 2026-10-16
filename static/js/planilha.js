(() => {
    const seletorPeriodo = document.querySelector("#periodo");
    const referencia = document.querySelector("#data-referencia");
    const mes = document.querySelector("#mes");
    const ano = document.querySelector("#ano");
    const previa = document.querySelector("[data-period-preview]");
    if (!seletorPeriodo) return;

    const formatar = (data) => new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" }).format(data);
    const atualizar = () => {
        const tipo = seletorPeriodo.value;
        document.querySelectorAll("[data-period-field]").forEach((campo) => {
            const visivel = campo.dataset.periodField.split(" ").includes(tipo);
            campo.hidden = !visivel;
            campo.querySelector("input")?.toggleAttribute("required", visivel);
        });
        let texto = "";
        if ((tipo === "dia" || tipo === "semana") && referencia.value) {
            const data = new Date(`${referencia.value}T12:00:00`);
            if (tipo === "dia") texto = `Planilha de ${formatar(data)}`;
            else {
                const inicio = new Date(data);
                inicio.setDate(data.getDate() - data.getDay());
                const fim = new Date(inicio);
                fim.setDate(inicio.getDate() + 6);
                texto = `Semana de ${formatar(inicio)} a ${formatar(fim)}`;
            }
        } else if (tipo === "mes" && mes.value) {
            const [y, m] = mes.value.split("-").map(Number);
            const ultimoDia = new Date(y, m, 0).getDate();
            texto = `Período de 01/${String(m).padStart(2,"0")}/${y} a ${ultimoDia}/${String(m).padStart(2,"0")}/${y}`;
        } else if (tipo === "ano" && ano.value) {
            texto = `Período de 01/01/${ano.value} a 31/12/${ano.value}`;
        }
        previa.textContent = texto;
    };
    [seletorPeriodo, referencia, mes, ano].forEach((campo) => campo.addEventListener("input", atualizar));
    atualizar();
})();
