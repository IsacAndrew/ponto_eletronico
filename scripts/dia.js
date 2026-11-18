// Preenche as barrinhas das 4 batidas a partir do texto "Último registro: HH:MM:SS / Tipo"
(() => {
  const tipos = ["Entrada", "Intervalo", "Retorno intervalo", "Saída"];
  const texto = document.querySelector("#ultimo-registro");
  const passos = [...document.querySelectorAll("#dia li")];
  if (!texto || !passos.length) return;
  const atualizar = () => {
    const m = texto.textContent.match(/(\d{2}:\d{2})(?::\d{2})?\s*\/\s*(.+?)\s*$/);
    const ultimo = m ? tipos.indexOf(m[2]) : -1;
    passos.forEach((li, i) => {
      li.classList.toggle("feito", i <= ultimo);
      li.querySelector("b").textContent = i === ultimo ? m[1] : i < ultimo ? "✓" : "--:--";
    });
  };
  new MutationObserver(atualizar).observe(texto, { childList: true, characterData: true, subtree: true });
  atualizar();
})();
