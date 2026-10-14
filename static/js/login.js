const campoSenha = document.querySelector("#senha");
const botaoVisibilidadeSenha = document.querySelector(
    "#alternar-visibilidade-senha"
);

botaoVisibilidadeSenha.addEventListener("click", () => {
    const mostrarSenha = campoSenha.type === "password";

    campoSenha.type = mostrarSenha ? "text" : "password";
    botaoVisibilidadeSenha.setAttribute("aria-pressed", String(mostrarSenha));
    botaoVisibilidadeSenha.setAttribute(
        "aria-label",
        mostrarSenha ? "Ocultar senha" : "Mostrar senha"
    );
});
