(() => {
    const cobertura = document.querySelector("[data-cobertura]");
    const campos = document.querySelector("[data-campos-horario]");
    const inicio = document.querySelector("[data-hora-inicio]");
    const fim = document.querySelector("[data-hora-fim]");
    if (!cobertura || !campos || !inicio || !fim) return;

    function atualizarCampos() {
        const periodo = cobertura.value === "horas";
        campos.hidden = !periodo;
        inicio.disabled = !periodo;
        fim.disabled = !periodo;
        inicio.required = periodo;
        fim.required = periodo;
    }

    cobertura.addEventListener("change", atualizarCampos);
    atualizarCampos();
})();
