document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-formatar-telefone]").forEach((campo) => {
        campo.addEventListener("input", () => {
            let numeros = campo.value.replace(/\D/g, "");

            if (numeros.length === 13 && numeros.startsWith("55")) {
                numeros = numeros.slice(2);
            }

            numeros = numeros.slice(0, 11);
            if (!numeros) {
                campo.value = "";
                return;
            }

            const ddd = numeros.slice(0, 2);
            const restante = numeros.slice(2);
            if (numeros.length <= 2) {
                campo.value = `(${numeros}`;
            } else if (numeros.length <= 7) {
                campo.value = `(${ddd}) ${restante}`;
            } else {
                campo.value = `(${ddd}) ${restante.slice(0, 5)}-${restante.slice(5)}`;
            }
        });
    });
});
