const campoSenhaNova = document.querySelector("#senha-nova");
const avisoSenha = document.querySelector("#aviso-senha");

campoSenhaNova.addEventListener("input", () => {
    avisoSenha.hidden = campoSenhaNova.value.length === 0;
});
