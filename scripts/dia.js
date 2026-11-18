// Exibe as etapas de ponto previstas para hoje e acompanha a última batida.
(() => {
  const tipos = ["Entrada", "Intervalo", "Retorno intervalo", "Saída"];
  const dia = document.querySelector("#dia");
  const texto = document.querySelector("#ultimo-registro");
  const mensagemSemJornada = document.querySelector("#dia-sem-jornada");
  if (!dia || !texto) return;

  const passos = [...dia.querySelectorAll("li")];
  const atualizar = () => {
    const quantidade = Number(dia.dataset.quantidade);
    const indicesAtivos = quantidade === 2 ? [0, 3] : quantidade === 0 ? [] : [0, 1, 2, 3];
    const registro = texto.textContent.match(/(\d{2}:\d{2})(?::\d{2})?\s*\/\s*(.+?)\s*$/);
    const indiceBatida = registro ? tipos.indexOf(registro[2]) : -1;
    const posicaoAtual = indicesAtivos.indexOf(indiceBatida);

    dia.hidden = quantidade === 0;
    if (mensagemSemJornada) mensagemSemJornada.hidden = quantidade !== 0;

    passos.forEach((li, indice) => {
      const posicao = indicesAtivos.indexOf(indice);
      li.hidden = posicao === -1;
      li.classList.toggle("feito", posicao !== -1 && posicao <= posicaoAtual);
      li.querySelector("b").textContent =
        posicao === posicaoAtual && registro
          ? registro[1]
          : posicao !== -1 && posicao < posicaoAtual
            ? "✓"
            : "--:--";
    });
  };

  new MutationObserver(atualizar).observe(texto, {
    childList: true,
    characterData: true,
    subtree: true,
  });
  dia.addEventListener("quantidadebatidasalterada", atualizar);
  atualizar();
})();
