(() => {
    const areaChat = document.querySelector("[data-conversa]");
    if (!areaChat || !areaChat.dataset.conversa) return;

    const conversa = areaChat.dataset.conversa;
    const listaMensagens = areaChat.querySelector("[data-mensagens]");
    const formulario = areaChat.querySelector("[data-form-mensagem]");
    const status = areaChat.querySelector("[data-status]");
    let ultimaMensagem = 0;

    function mostrarMensagem(mensagem) {
        if (mensagem.id <= ultimaMensagem) return;
        const item = document.createElement("article");
        item.className = `mensagem-chat${(areaChat.dataset.suporte === "true") === (mensagem.remetente === "Suporte") ? " mensagem-propria" : ""}`;
        const texto = document.createElement("p");
        texto.textContent = mensagem.texto;
        const horario = document.createElement("time");
        horario.textContent = mensagem.horario;
        item.append(texto, horario);
        listaMensagens.append(item);
        ultimaMensagem = mensagem.id;
        listaMensagens.scrollTop = listaMensagens.scrollHeight;
    }

    async function atualizarMensagens() {
        try {
            const resposta = await fetch(`/chat-suporte/atualizacoes?conversa=${encodeURIComponent(conversa)}&desde=${ultimaMensagem}`);
            if (!resposta.ok) {
                if (resposta.status === 404) window.location.reload();
                return;
            }
            const dados = await resposta.json();
            dados.mensagens.forEach(mostrarMensagem);
        } catch {
            if (status) status.textContent = "Sem conexão. Tentando novamente…";
        }
    }

    formulario?.addEventListener("submit", async (evento) => {
        evento.preventDefault();
        const campo = formulario.elements.mensagem;
        const mensagem = campo.value.trim();
        if (!mensagem) return;
        const botao = formulario.querySelector("button[type=submit]");
        botao.disabled = true;
        try {
            const resposta = await fetch("/chat-suporte/mensagem", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ conversa, mensagem }),
            });
            const dados = await resposta.json();
            if (!resposta.ok) throw new Error(dados.mensagem || "Não foi possível enviar a mensagem.");
            campo.value = "";
            if (status) status.textContent = "";
            await atualizarMensagens();
        } catch (erro) {
            if (status) status.textContent = erro.message;
        } finally {
            botao.disabled = false;
            campo.focus();
        }
    });

    areaChat.querySelector("[data-encerrar]")?.addEventListener("click", async () => {
        if (!window.confirm("Encerrar esta conversa e apagar todas as mensagens?")) return;
        try {
            const resposta = await fetch(`/chat-suporte/${encodeURIComponent(conversa)}/encerrar`, { method: "POST" });
            if (!resposta.ok) throw new Error("Não foi possível encerrar a conversa.");
            window.location.assign("/chat-suporte");
        } catch (erro) {
            if (status) status.textContent = erro.message;
        }
    });

    atualizarMensagens();
    window.setInterval(atualizarMensagens, 2000);
})();
