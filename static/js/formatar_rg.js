document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-formatar-rg]").forEach((campo) => {
        function formatarCampo() {
            const digitos = campo.value.replace(/\D/g, "").slice(0, 9);
            if (digitos.length <= 2) {
                campo.value = digitos;
            } else if (digitos.length <= 5) {
                campo.value = `${digitos.slice(0, 2)}.${digitos.slice(2)}`;
            } else if (digitos.length <= 8) {
                campo.value = `${digitos.slice(0, 2)}.${digitos.slice(2, 5)}.${digitos.slice(5)}`;
            } else {
                campo.value = `${digitos.slice(0, 2)}.${digitos.slice(2, 5)}.${digitos.slice(5, 8)}-${digitos[8]}`;
            }
        }

        campo.addEventListener("input", formatarCampo);
        formatarCampo();
    });
});
