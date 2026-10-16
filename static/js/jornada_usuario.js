(() => {
    const formulario = document.querySelector(".formulario-jornada");
    const quantidade = document.querySelector("#quantidade-batidas");
    if (!formulario || !quantidade) return;

    const camposQuatroBatidas = formulario.querySelectorAll(".campo-horario-quatro");
    const retorno = formulario.querySelector('[name="retorno_intervalo"]');
    const intervalo = formulario.querySelector('[name="intervalo"]');

    function atualizarCampos() {
        const usaQuatroBatidas = quantidade.value === "4";
        camposQuatroBatidas.forEach((campo) => {
            campo.hidden = !usaQuatroBatidas;
        });
        intervalo.required = usaQuatroBatidas;
        retorno.required = usaQuatroBatidas;
        formulario.dataset.quantidadeBatidas = quantidade.value;
    }

    quantidade.addEventListener("change", atualizarCampos);
    atualizarCampos();
})();
