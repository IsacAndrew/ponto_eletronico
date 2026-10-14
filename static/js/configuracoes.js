const formularioMarcoZero = document.querySelector("#formulario-marco-zero");
const botaoUsarLocalizacao = document.querySelector("#botao-usar-localizacao");
const campoLatitudeMarco = document.querySelector("#latitude-marco-zero");
const campoLongitudeMarco = document.querySelector("#longitude-marco-zero");
const campoEnderecoMarco = document.querySelector("#endereco-marco-zero");
const campoRaioMarco = document.querySelector("#raio-marco-zero");
const mensagemMarcoZero = document.querySelector("#mensagem-marco-zero");
const mapaMarcoZero = document.querySelector("#mapa-marco-zero");

function mostrarMensagemMarcoZero(mensagem, erro = false) {
    mensagemMarcoZero.textContent = mensagem;
    mensagemMarcoZero.classList.toggle("mensagem-erro", erro);
}

function atualizarMapaMarcoZero() {
    const latitude = Number(campoLatitudeMarco.value);
    const longitude = Number(campoLongitudeMarco.value);

    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;

    const mapa = document.createElement("iframe");
    mapa.title = "Mapa do marco zero";
    mapa.loading = "lazy";
    mapa.referrerPolicy = "no-referrer-when-downgrade";
    mapa.src = `https://maps.google.com/maps?q=${encodeURIComponent(`${latitude},${longitude}`)}&z=17&output=embed`;
    mapaMarcoZero.replaceChildren(mapa);
}

botaoUsarLocalizacao.addEventListener("click", () => {
    if (!navigator.geolocation) {
        mostrarMensagemMarcoZero("Este navegador não oferece acesso à localização.", true);
        return;
    }

    botaoUsarLocalizacao.disabled = true;
    mostrarMensagemMarcoZero("Obtendo localização… permita o acesso quando o navegador solicitar.");
    navigator.geolocation.getCurrentPosition(
        (posicao) => {
            campoLatitudeMarco.value = posicao.coords.latitude.toFixed(7);
            campoLongitudeMarco.value = posicao.coords.longitude.toFixed(7);
            atualizarMapaMarcoZero();
            mostrarMensagemMarcoZero("Coordenadas obtidas. Confira o endereço e salve o marco zero.");
            botaoUsarLocalizacao.disabled = false;
        },
        (erro) => {
            const mensagens = {
                1: "A permissão de localização foi negada. Habilite-a nas configurações do navegador.",
                2: "Não foi possível determinar a localização. Verifique o GPS e tente novamente.",
                3: "A localização demorou demais. Tente novamente em um local com melhor sinal.",
            };
            mostrarMensagemMarcoZero(mensagens[erro.code] || "Falha ao obter a localização.", true);
            botaoUsarLocalizacao.disabled = false;
        },
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 },
    );
});

formularioMarcoZero.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const botaoSalvar = formularioMarcoZero.querySelector(".botao-salvar-marco");
    botaoSalvar.disabled = true;
    mostrarMensagemMarcoZero("Salvando marco zero…");

    try {
        const resposta = await fetch("/configuracoes/marco-zero", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                endereco: campoEnderecoMarco.value.trim(),
                latitude: campoLatitudeMarco.value,
                longitude: campoLongitudeMarco.value,
                raio_metros: campoRaioMarco.value,
            }),
        });
        const resultado = await resposta.json();
        if (!resposta.ok) throw new Error(resultado.mensagem || "Não foi possível salvar o marco zero.");

        mostrarMensagemMarcoZero(resultado.mensagem);
        atualizarMapaMarcoZero();
        window.setTimeout(() => window.location.reload(), 700);
    } catch (erro) {
        mostrarMensagemMarcoZero(erro.message, true);
        botaoSalvar.disabled = false;
    }
});

if (campoLatitudeMarco.value && campoLongitudeMarco.value) atualizarMapaMarcoZero();
