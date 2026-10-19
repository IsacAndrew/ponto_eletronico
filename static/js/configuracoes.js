const botaoAbrirMarco = document.querySelector("#abrir-marco-zero");
const janelaMarco = document.querySelector("#janela-marco-zero");
const formularioMarco = document.querySelector("#formulario-marco-zero");
const enderecoMarco = document.querySelector("#endereco-marco-zero");
const latitudeMarco = document.querySelector("#latitude-marco-zero");
const longitudeMarco = document.querySelector("#longitude-marco-zero");
const raioMarco = document.querySelector("#raio-marco-zero");
const mapaMarco = document.querySelector("#mapa-marco-zero");
const camadaTilesMapa = document.querySelector("#camada-tiles-mapa");
const instrucaoMapaVazio = document.querySelector("#instrucao-mapa-vazio");
const mensagemMarco = document.querySelector("#mensagem-marco-zero");
const botaoConfirmarMapa = document.querySelector("#botao-confirmar-mapa");
const controles = {
    buscar: document.querySelector("#botao-localizar-endereco"),
    gps: document.querySelector("#botao-usar-localizacao"),
    aproximar: document.querySelector("#aproximar-mapa"),
    afastar: document.querySelector("#afastar-mapa"),
};

const TAMANHO_TILE = 256;
const ZOOM_MINIMO = 3;
const ZOOM_MAXIMO = 19;
let centroMapa = null;
let zoomMapa = 17;
let arrastoMapa = null;
let ultimaBuscaMapa = 0;
let enderecoCoordenadasConfirmadas = enderecoMarco.value.trim();

function mostrarMensagem(mensagem, erro = false) {
    mensagemMarco.textContent = mensagem;
    mensagemMarco.classList.toggle("mensagem-erro", erro);
}

function limitarLatitude(latitude) {
    return Math.max(-85.05112878, Math.min(85.05112878, latitude));
}

function coordenadasParaPixel(latitude, longitude, zoom) {
    const escala = TAMANHO_TILE * (2 ** zoom);
    const latRad = limitarLatitude(latitude) * Math.PI / 180;
    return {
        x: (longitude + 180) / 360 * escala,
        y: (1 - Math.asinh(Math.tan(latRad)) / Math.PI) / 2 * escala,
    };
}

function pixelParaCoordenadas(x, y, zoom) {
    const escala = TAMANHO_TILE * (2 ** zoom);
    const longitude = x / escala * 360 - 180;
    const n = Math.PI - 2 * Math.PI * y / escala;
    const latitude = 180 / Math.PI * Math.atan(Math.sinh(n));
    return { latitude, longitude };
}

function desenharMapa() {
    if (!centroMapa) return;
    const largura = mapaMarco.clientWidth;
    const altura = mapaMarco.clientHeight;
    if (!largura || !altura) return;

    const centroPixel = coordenadasParaPixel(centroMapa.latitude, centroMapa.longitude, zoomMapa);
    const escala = 2 ** zoomMapa;
    const quantidadeX = Math.ceil(largura / TAMANHO_TILE) + 2;
    const quantidadeY = Math.ceil(altura / TAMANHO_TILE) + 2;
    const tileCentroX = Math.floor(centroPixel.x / TAMANHO_TILE);
    const tileCentroY = Math.floor(centroPixel.y / TAMANHO_TILE);
    const tileInicialX = tileCentroX - Math.floor(quantidadeX / 2);
    const tileInicialY = tileCentroY - Math.floor(quantidadeY / 2);
    const fragmento = document.createDocumentFragment();

    for (let deslocamentoY = 0; deslocamentoY < quantidadeY; deslocamentoY += 1) {
        const tileY = tileInicialY + deslocamentoY;
        if (tileY < 0 || tileY >= escala) continue;
        for (let deslocamentoX = 0; deslocamentoX < quantidadeX; deslocamentoX += 1) {
            const tileX = tileInicialX + deslocamentoX;
            const tileXUrl = ((tileX % escala) + escala) % escala;
            const imagem = document.createElement("img");
            imagem.alt = "";
            imagem.draggable = false;
            imagem.loading = "lazy";
            imagem.src = `https://tile.openstreetmap.org/${zoomMapa}/${tileXUrl}/${tileY}.png`;
            imagem.style.left = `${tileX * TAMANHO_TILE - centroPixel.x + largura / 2}px`;
            imagem.style.top = `${tileY * TAMANHO_TILE - centroPixel.y + altura / 2}px`;
            fragmento.append(imagem);
        }
    }

    camadaTilesMapa.replaceChildren(fragmento);
    instrucaoMapaVazio.hidden = true;
    botaoConfirmarMapa.disabled = false;
}

function definirCentro(latitude, longitude, atualizarCoordenadas = true) {
    centroMapa = { latitude: limitarLatitude(latitude), longitude };
    if (atualizarCoordenadas) {
        latitudeMarco.value = centroMapa.latitude.toFixed(7);
        longitudeMarco.value = centroMapa.longitude.toFixed(7);
    }
    desenharMapa();
}

async function aguardarLimiteDeBusca() {
    const espera = 1100 - (Date.now() - ultimaBuscaMapa);
    if (espera > 0) await new Promise((resolver) => window.setTimeout(resolver, espera));
    ultimaBuscaMapa = Date.now();
}

async function consultarNominatim(caminho, parametros) {
    await aguardarLimiteDeBusca();
    const consulta = new URLSearchParams({
        format: "jsonv2",
        addressdetails: "1",
        "accept-language": "pt-BR",
        ...parametros,
    });
    const resposta = await fetch(`https://nominatim.openstreetmap.org/${caminho}?${consulta}`);
    if (!resposta.ok) throw new Error("O serviço de mapas não respondeu. Tente novamente em instantes.");
    return resposta.json();
}

async function consultarCep(cep) {
    const resposta = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
    if (!resposta.ok) throw new Error("Não foi possível consultar esse CEP. Tente novamente.");
    const local = await resposta.json();
    if (local.erro) throw new Error("CEP não encontrado. Confira os números digitados.");
    return local;
}

function formatarEnderecoCep(local) {
    return [
        local.logradouro,
        local.bairro,
        local.localidade,
        local.uf,
        local.cep,
        "Brasil",
    ].filter(Boolean).join(", ");
}

function marcarEnderecoResolvido(endereco) {
    enderecoMarco.value = endereco;
    enderecoCoordenadasConfirmadas = enderecoMarco.value.trim();
}

function enderecoComCep(local) {
    const partes = local.address || {};
    const logradouro = [partes.road || partes.pedestrian, partes.house_number]
        .filter(Boolean)
        .join(", ");
    const localidade = partes.city || partes.town || partes.municipality || partes.village;
    const componentes = [logradouro, partes.suburb || partes.neighbourhood, localidade, partes.state, partes.postcode]
        .filter(Boolean);
    if (componentes.length) return [...new Set(componentes)].join(" — ");
    return local.display_name || "";
}

async function preencherEnderecoDaCoordenada(latitude, longitude) {
    mostrarMensagem("Identificando o endereço do ponto no mapa…");
    const resultado = await consultarNominatim("reverse", {
        lat: latitude,
        lon: longitude,
        zoom: 18,
    });
    const endereco = enderecoComCep(resultado);
    if (!endereco) throw new Error("O mapa não encontrou um endereço para este ponto.");
    return endereco;
}

async function localizarEndereco() {
    const endereco = enderecoMarco.value.trim();
    if (!endereco) {
        mostrarMensagem("Informe um CEP ou endereço para localizar no mapa.", true);
        return;
    }

    controles.buscar.disabled = true;
    mostrarMensagem("Localizando endereço no mapa…");
    try {
        const cep = endereco.replace(/\D/g, "");
        let parametros;
        let buscaPorCep = false;
        let enderecoCep = "";
        if (cep.length === 8 && /^\d{5}-?\d{3}$/.test(endereco.replace(/\s/g, ""))) {
            const localCep = await consultarCep(cep);
            enderecoCep = formatarEnderecoCep(localCep);
            parametros = {
                street: localCep.logradouro,
                city: localCep.localidade,
                state: localCep.uf,
                postalcode: cep,
                country: "Brasil",
                countrycodes: "br",
                limit: 1,
            };
            Object.keys(parametros).forEach((chave) => {
                if (!parametros[chave]) delete parametros[chave];
            });
            buscaPorCep = true;
        } else {
            parametros = { q: endereco, countrycodes: "br", limit: 1 };
        }
        const resultados = await consultarNominatim("search", parametros);
        if (!resultados.length) throw new Error("Endereço não encontrado. Confira o CEP ou informe rua, número e cidade.");
        const local = resultados[0];
        definirCentro(Number(local.lat), Number(local.lon));
        marcarEnderecoResolvido(
            buscaPorCep ? enderecoCep : enderecoComCep(local) || local.display_name,
        );
        mostrarMensagem(
            buscaPorCep
                ? "CEP localizado como referência aproximada. Ajuste o mapa até o ponto exato da escola e clique em Usar centro do mapa."
                : "Local encontrado. Confira o marcador no mapa e salve.",
        );
    } catch (erro) {
        mostrarMensagem(erro.message, true);
    } finally {
        controles.buscar.disabled = false;
    }
}

function obterLocalizacaoAtual() {
    if (!navigator.geolocation) {
        mostrarMensagem("Este navegador não oferece acesso à localização.", true);
        return;
    }

    controles.gps.disabled = true;
    mostrarMensagem("Obtendo localização atual…");
    navigator.geolocation.getCurrentPosition(
        async (posicao) => {
            try {
                definirCentro(posicao.coords.latitude, posicao.coords.longitude, false);
                const endereco = await preencherEnderecoDaCoordenada(
                    posicao.coords.latitude,
                    posicao.coords.longitude,
                );
                marcarEnderecoResolvido(endereco);
                latitudeMarco.value = posicao.coords.latitude.toFixed(7);
                longitudeMarco.value = posicao.coords.longitude.toFixed(7);
                mostrarMensagem("Endereço identificado. Confira o raio e salve o marco zero.");
            } catch (erro) {
                mostrarMensagem(erro.message, true);
            } finally {
                controles.gps.disabled = false;
            }
        },
        (erro) => {
            const mensagens = {
                1: "A permissão de localização foi negada. Habilite-a nas configurações do navegador.",
                2: "Não foi possível determinar a localização. Verifique o GPS e tente novamente.",
                3: "A localização demorou demais. Tente novamente em um local com melhor sinal.",
            };
            mostrarMensagem(mensagens[erro.code] || "Falha ao obter a localização.", true);
            controles.gps.disabled = false;
        },
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 },
    );
}

function selecionarCentroDoMapa() {
    if (!centroMapa) return;
    const coordenadaSelecionada = { ...centroMapa };
    botaoConfirmarMapa.disabled = true;
    preencherEnderecoDaCoordenada(coordenadaSelecionada.latitude, coordenadaSelecionada.longitude)
        .then((endereco) => {
            marcarEnderecoResolvido(endereco);
            latitudeMarco.value = coordenadaSelecionada.latitude.toFixed(7);
            longitudeMarco.value = coordenadaSelecionada.longitude.toFixed(7);
            mostrarMensagem("Coordenadas selecionadas. O endereço exibido é aproximado; confira o marcador e salve o marco zero.");
        })
        .catch((erro) => mostrarMensagem(erro.message, true))
        .finally(() => { botaoConfirmarMapa.disabled = false; });
}

botaoAbrirMarco.addEventListener("click", () => {
    janelaMarco.showModal();
    if (!centroMapa && mapaMarco.dataset.latitude && mapaMarco.dataset.longitude) {
        definirCentro(Number(mapaMarco.dataset.latitude), Number(mapaMarco.dataset.longitude));
    }
    window.requestAnimationFrame(desenharMapa);
});

document.querySelector("#fechar-marco-zero").addEventListener("click", () => janelaMarco.close());
document.querySelector("#cancelar-marco-zero").addEventListener("click", () => janelaMarco.close());
enderecoMarco.addEventListener("input", () => {
    if (enderecoMarco.value.trim() === enderecoCoordenadasConfirmadas) return;
    latitudeMarco.value = "";
    longitudeMarco.value = "";
    centroMapa = null;
    camadaTilesMapa.replaceChildren();
    instrucaoMapaVazio.hidden = false;
    botaoConfirmarMapa.disabled = true;
    mostrarMensagem("O endereço foi alterado. Localize-o novamente para atualizar as coordenadas.");
});
controles.buscar.addEventListener("click", localizarEndereco);
controles.gps.addEventListener("click", obterLocalizacaoAtual);
botaoConfirmarMapa.addEventListener("click", selecionarCentroDoMapa);
controles.aproximar.addEventListener("click", () => {
    zoomMapa = Math.min(ZOOM_MAXIMO, zoomMapa + 1);
    desenharMapa();
});
controles.afastar.addEventListener("click", () => {
    zoomMapa = Math.max(ZOOM_MINIMO, zoomMapa - 1);
    desenharMapa();
});

mapaMarco.addEventListener("pointerdown", (evento) => {
    if (!centroMapa || evento.target.closest("button, a")) return;
    arrastoMapa = { x: evento.clientX, y: evento.clientY, centro: { ...centroMapa } };
    mapaMarco.setPointerCapture(evento.pointerId);
});

mapaMarco.addEventListener("pointermove", (evento) => {
    if (!arrastoMapa) return;
    const deltaX = evento.clientX - arrastoMapa.x;
    const deltaY = evento.clientY - arrastoMapa.y;
    arrastoMapa.deltaX = deltaX;
    arrastoMapa.deltaY = deltaY;
    camadaTilesMapa.style.transform = `translate3d(${deltaX}px, ${deltaY}px, 0)`;
});

function finalizarArrastoMapa() {
    if (!arrastoMapa) return;
    const centroPixel = coordenadasParaPixel(
        arrastoMapa.centro.latitude,
        arrastoMapa.centro.longitude,
        zoomMapa,
    );
    const deltaX = arrastoMapa.deltaX || 0;
    const deltaY = arrastoMapa.deltaY || 0;
    centroMapa = pixelParaCoordenadas(centroPixel.x - deltaX, centroPixel.y - deltaY, zoomMapa);
    centroMapa.latitude = limitarLatitude(centroMapa.latitude);
    camadaTilesMapa.style.transform = "";
    arrastoMapa = null;
    desenharMapa();
}

mapaMarco.addEventListener("pointerup", finalizarArrastoMapa);
mapaMarco.addEventListener("pointercancel", finalizarArrastoMapa);

formularioMarco.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    if (!latitudeMarco.value || !longitudeMarco.value) {
        mostrarMensagem("Localize um endereço ou escolha o centro do mapa antes de salvar.", true);
        return;
    }
    if (centroMapa) {
        const pixelConfirmado = coordenadasParaPixel(
            Number(latitudeMarco.value), Number(longitudeMarco.value), zoomMapa,
        );
        const pixelAtual = coordenadasParaPixel(centroMapa.latitude, centroMapa.longitude, zoomMapa);
        const metrosPorPixel = 156543.03392 * Math.cos(centroMapa.latitude * Math.PI / 180) / (2 ** zoomMapa);
        const diferencaMetros = Math.hypot(pixelConfirmado.x - pixelAtual.x, pixelConfirmado.y - pixelAtual.y) * metrosPorPixel;
        if (diferencaMetros > 3) {
            mostrarMensagem("Confirme o novo ponto clicando em Usar centro do mapa.", true);
            return;
        }
    }
    const botaoSalvar = formularioMarco.querySelector(".botao-salvar-marco");
    botaoSalvar.disabled = true;
    mostrarMensagem("Salvando marco zero…");

    try {
        const resposta = await fetch("/configuracoes/marco-zero", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                endereco: enderecoMarco.value.trim(),
                latitude: latitudeMarco.value,
                longitude: longitudeMarco.value,
                raio_metros: raioMarco.value,
            }),
        });
        const resultado = await resposta.json();
        if (!resposta.ok) throw new Error(resultado.mensagem || "Não foi possível salvar o marco zero.");
        mostrarMensagem(resultado.mensagem);
        window.setTimeout(() => window.location.reload(), 700);
    } catch (erro) {
        mostrarMensagem(erro.message, true);
        botaoSalvar.disabled = false;
    }
});

window.addEventListener("resize", desenharMapa);
