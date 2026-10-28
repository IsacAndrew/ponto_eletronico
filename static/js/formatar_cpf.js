document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-formatar-cpf]").forEach((campo) => {
        function formatarCampo() {
            const digitos = campo.value.replace(/\D/g, "").slice(0, 11);
            if (digitos.length <= 3) {
                campo.value = digitos;
            } else if (digitos.length <= 6) {
                campo.value = `${digitos.slice(0, 3)}.${digitos.slice(3)}`;
            } else if (digitos.length <= 9) {
                campo.value = `${digitos.slice(0, 3)}.${digitos.slice(3, 6)}.${digitos.slice(6)}`;
            } else {
                campo.value = `${digitos.slice(0, 3)}.${digitos.slice(3, 6)}.${digitos.slice(6, 9)}-${digitos.slice(9)}`;
            }
        }

        campo.addEventListener("input", formatarCampo);
        formatarCampo();
    });
});
