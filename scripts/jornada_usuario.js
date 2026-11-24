(() => {
    const formulario = document.querySelector(".formulario-jornada");
    const quantidade = document.querySelector("#quantidade-batidas");
    if (!formulario || !quantidade) return;

    const camposQuatroBatidas = formulario.querySelectorAll(".campo-horario-quatro");
    function atualizarCampos() {
        const usaQuatroBatidas = quantidade.value === "4";
        camposQuatroBatidas.forEach((campo) => {
            campo.hidden = !usaQuatroBatidas;
        });
        formulario.dataset.quantidadeBatidas = quantidade.value;
    }

    quantidade.addEventListener("change", atualizarCampos);
    atualizarCampos();
})();
