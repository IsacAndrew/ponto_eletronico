(() => {
    const janela = document.querySelector("#janela-registros-ponto");
    if (janela && !janela.open) janela.showModal();

    document.querySelectorAll(".campo-horario-registro").forEach((campo) => {
        campo.addEventListener("input", () => {
            const digitos = campo.value.replace(/\D/g, "").slice(0, 4);
            campo.value = digitos.length > 2
                ? `${digitos.slice(0, 2)}:${digitos.slice(2)}`
                : digitos;
        });
    });
})();
