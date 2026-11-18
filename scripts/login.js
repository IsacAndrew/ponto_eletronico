const campoSenha = document.querySelector("#senha");
const botaoVisibilidadeSenha = document.querySelector(
    "#alternar-visibilidade-senha"
);
const campoLogin = document.querySelector("#login");
const formularioLogin = document.querySelector(".formulario-login");

botaoVisibilidadeSenha.addEventListener("click", () => {
    const mostrarSenha = campoSenha.type === "password";

    campoSenha.type = mostrarSenha ? "text" : "password";
    botaoVisibilidadeSenha.setAttribute("aria-pressed", String(mostrarSenha));
    botaoVisibilidadeSenha.setAttribute(
        "aria-label",
        mostrarSenha ? "Ocultar senha" : "Mostrar senha"
    );
});

campoLogin.addEventListener("blur", async () => {
    const login = campoLogin.value.trim();
    if (!login) return;

    try {
        const resposta = await fetch(formularioLogin.dataset.mensagensUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ login }),
        });
        if (!resposta.ok) return;
        const resultado = await resposta.json();
        if (resultado.mensagens?.length) {
            window.alert(resultado.mensagens.join("\n\n"));
        }
    } catch (_) {
        // Avisos de login são opcionais e não devem impedir a entrada no sistema.
    }
});
