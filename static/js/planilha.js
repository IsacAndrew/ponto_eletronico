function formatarCampoNumerico(campo, digitos, separadorData = false) {
    campo.addEventListener("input", () => {
        const valorNumerico = campo.value.replace(/\D/g, "").slice(0, digitos);
        if (separadorData && valorNumerico.length > 4) {
            campo.value = `${valorNumerico.slice(0, 2)}/${valorNumerico.slice(2, 4)}/${valorNumerico.slice(4)}`;
        } else if (valorNumerico.length > 2) {
            campo.value = `${valorNumerico.slice(0, 2)}/${valorNumerico.slice(2)}`;
        } else {
            campo.value = valorNumerico;
        }
    });
}

document.querySelectorAll("[data-formato-data]").forEach((campo) => {
    if (/^\d{4}-\d{2}-\d{2}$/.test(campo.value)) {
        const [ano, mes, dia] = campo.value.split("-");
        campo.value = `${dia}/${mes}/${ano.slice(-2)}`;
    }
    formatarCampoNumerico(campo, 6, true);
});

document.querySelectorAll("[data-formato-mes]").forEach((campo) => {
    if (/^\d{4}-\d{2}$/.test(campo.value)) {
        const [ano, mes] = campo.value.split("-");
        campo.value = `${mes}/${ano}`;
    }
    formatarCampoNumerico(campo, 6);
});
