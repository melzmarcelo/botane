function montarPortaDeFidelidade() {
  // 🔑 144: "Mostrar Fidelidade no site" desmarcado esconde o item. ⚠️ O QR da mesa continua
  // abrindo a fidelidade (o check-in) — esconder não é desligar o programa.
  // 🔑 Layout novo (05/11/2026): vira o ATALHO ao lado do cardápio, como no protótipo.
  if (!casa.fidelidade || casa.fidelidade_no_site === false || $("#ir-fidelidade")) return;
  const b = document.createElement("button");
  b.type = "button";
  b.className = "atalho atalho-fidelidade";
  b.id = "ir-fidelidade";
  b.innerHTML = `<span class="ico">${ICONES.estrela}</span><span class="texto-atalho"><strong>Cartão fidelidade</strong><small>Veja seus selos e prêmios</small></span>`;
  b.addEventListener("click", () => abrirFidelidade());
  $("#atalhos").appendChild(b);
}

/* ===========================================================================
   LAYOUT NOVO (protótipo aprovado pelo dono, 05/11/2026)
   =========================================================================== */
const ICONE_ZAP = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <path d="M4 20l1.3-3.9A8 8 0 1 1 8 19z M9 10c.5 2 2 3.5 4 4"/></svg>`;
const _svg = (d, n = 20) => `<svg width="${n}" height="${n}" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"
  aria-hidden="true"><path d="${d}"/></svg>`;
const ICONES = {
  estrela: _svg("M12 3l2.6 5.3 5.9.9-4.2 4.1 1 5.8L12 16.4 6.7 19.1l1-5.8L3.5 9.2l5.9-.9z"),
  cardapio: _svg("M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z M9 8h6 M9 12h6"),
  cardapioGrande: _svg("M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z M9 8h6 M9 12h6", 30),
  pdf: _svg("M6 3h9l4 4v14H6z M14 3v5h5 M9 13h6 M9 17h6", 30),
};

/** "Bom dia!", "Boa tarde!" ou "Boa noite!", pela hora do APARELHO de quem lê. */
function saudacao() {
  const h = new Date().getHours();
  return t(h < 12 ? "Bom dia!" : h < 18 ? "Boa tarde!" : "Boa noite!");
}

/**
 * O cartão de UM catálogo: a capa e o nome. Serve à fileira do início e à grade de "Ver tudo".
 *
 * ⚠️ **O texto do cartão é SÓ o nome** — a capa é decorativa (`aria-hidden`, imagem sem
 * `alt`). É o que o leitor de tela diz e o que a tradução e os testes conferem.
 * ⚠️ `href` preenchido = PDF aberto (link de verdade, que o celular não bloqueia como popup);
 * sem ele, o toque passa por `abrirCatalogo` (cardápio montado, feed ou identificação).
 */
function cartaoDeCatalogo(c, href) {
  const el = document.createElement(href ? "a" : "button");
  el.className = "cartao-catalogo";
  el.dataset.catalogo = c.id;
  if (href) {
    el.href = href;
    el.target = "_blank";
    el.rel = "noopener";
  } else {
    el.type = "button";
    el.addEventListener("click", () => abrirCatalogo(c));
  }
  const capa = document.createElement("span");
  capa.className = "capa-cat";
  capa.setAttribute("aria-hidden", "true");
  capa.innerHTML = c.capa
    ? `<img src="${API}${esc(c.capa)}" alt="" loading="lazy">`
    : (c.origem === "PRODUTOS" ? ICONES.cardapioGrande : ICONES.pdf);
  el.appendChild(capa);
  el.appendChild(document.createTextNode(c.nome));
  return el;
}

/** O atalho "Cardápio" do início: um catálogo abre direto; vários, a grade. */
function montarAtalhoDoCardapio() {
  if (!catalogosDaCasa.length || $("#ir-cardapio")) return;
  const b = document.createElement("button");
  b.type = "button";
  b.className = "atalho atalho-cardapio";
  b.id = "ir-cardapio";
  const n = catalogosDaCasa.length;
  b.innerHTML = `<span class="ico">${ICONES.cardapio}</span><span class="texto-atalho"><strong>${esc(t(n > 1 ? "Cardápios" : "Cardápio"))}</strong><small>${
      esc(n > 1 ? t("{n} catálogos", { n }) : catalogosDaCasa[0].nome)}</small></span>`;
  b.addEventListener("click", abrirCatalogos);
  // O cardápio vem ANTES da fidelidade, como no protótipo.
  $("#atalhos").prepend(b);
}

/** A aba e o atalho "Cardápio": com um catálogo só, abre ele; com vários, a grade. */
function abrirCatalogos() {
  if (catalogosDaCasa.length === 1) {
    const unico = $("#itens .cartao-catalogo");
    if (unico) unico.click();
    return;
  }
  ir("catalogos");
}

/**
 * As abas de baixo: Início sempre; Cardápio, Reservar e Fidelidade só quando a casa os
 * oferece — a mesma regra das portas do início. Com só o Início, a barra nem aparece.
 */
function montarAbas() {
  const abas = $("#abas");
  const mostra = {
    cardapio: catalogosDaCasa.length > 0,
    reserva: !$("#ir-reservar").hidden,
    fidelidade: !!$("#ir-fidelidade"),
  };
  abas.querySelectorAll("button[data-aba]").forEach((b) => {
    if (b.dataset.aba in mostra) b.hidden = !mostra[b.dataset.aba];
  });
  abas.hidden = !Object.values(mostra).some(Boolean);
  document.body.classList.toggle("sem-abas", abas.hidden);
  marcarAba((location.hash || "#inicio").slice(1));
}

/** Que aba acende em cada tela. "quem" (o telefone) é da porta que levou até ele. */
const ABA_DA_TELA = {
  inicio: "inicio", lojas: "inicio", contato: "inicio",
  catalogos: "cardapio", cardapio: "cardapio", secao: "cardapio", carrinho: "cardapio",
  "pedido-pronto": "cardapio", "meus-pedidos": "cardapio",
  reserva: "reserva", pronto: "reserva", fidelidade: "fidelidade",
};
function marcarAba(nome) {
  let para = null;
  // ⚠️ `destino` é declarado mais abaixo no arquivo: no primeiro `ir()` ele ainda não existe.
  try { para = destino; } catch { para = null; }
  const aba = nome === "quem"
    ? (para === "fidelidade" ? "fidelidade" : para === "reserva" ? "reserva" : "cardapio")
    : ABA_DA_TELA[nome] || "inicio";
  document.querySelectorAll("#abas button[data-aba]").forEach((b) =>
    b.setAttribute("aria-current", b.dataset.aba === aba ? "page" : "false"));
}

/**
 * Os dias em BOTÕES (protótipo): os próximos 14 dias em que a casa abre. Para mais longe
 * fica o calendário ("Outro dia").
 * ⚠️ Os dias de funcionamento vêm de `casa.dias` ("Ter", "Qua"…). Sem eles, todos entram —
 * a lista de horários é quem diz se há mesa.
 * ⚠️ O botão só PREENCHE o `#dia`: a busca e a gravação continuam lendo o campo.
 */
const SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
function montarDias() {
  const caixa = $("#dias");
  if (!caixa) return;
  const abre = new Set(casa && casa.dias && casa.dias.length ? casa.dias : SEMANA);
  const botoes = [];
  for (let i = 0; botoes.length < 14 && i < 30; i++) {
    const d = new Date();
    d.setDate(d.getDate() + i);
    if (!abre.has(SEMANA[d.getDay()])) continue;
    const iso = diaIso(i);
    const rotulo = i === 0 ? t("Hoje") : i === 1 ? t("Amanhã") : t(SEMANA[d.getDay()]);
    botoes.push(`<button type="button" class="dia-chip" data-dia="${iso}" aria-pressed="false"
      aria-label="${esc(d.toLocaleDateString(LOCALE, { weekday: "long", day: "numeric", month: "long" }))}">
      <small>${esc(rotulo)}</small><b>${d.getDate()}</b></button>`);
  }
  caixa.innerHTML = botoes.join("");
  caixa.onclick = (e) => {
    const b = e.target.closest(".dia-chip");
    if (!b) return;
    $("#dia").value = b.dataset.dia;
    diaTocado = true;
    buscarHorarios();
  };
  marcarDia();
}
/** Acende o botão do dia que está no campo (escolhido no calendário, nenhum acende). */
function marcarDia() {
  const dia = $("#dia").value;
  let aceso = null;
  document.querySelectorAll("#dias .dia-chip").forEach((b) => {
    const sim = b.dataset.dia === dia;
    b.setAttribute("aria-pressed", String(sim));
    if (sim) aceso = b;
  });
  if (aceso) aceso.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
}

/** As seções do cardápio em pílulas, no topo da seção — trocar sem voltar (protótipo). */
function desenharPilulas(atual) {
  const caixa = $("#pilulas-secoes");
  if (!caixa || !cardapio) return;
  if (cardapio.categorias.length < 2) { caixa.innerHTML = ""; return; }
  caixa.innerHTML = cardapio.categorias.map((c, i) =>
    `<button type="button" role="tab" aria-selected="${i === atual}" data-i="${i}">${esc(c.nome)}</button>`).join("");
  caixa.onclick = (e) => {
    const b = e.target.closest("button[data-i]");
    if (b && Number(b.dataset.i) !== atual) abrirSecao(Number(b.dataset.i));
  };
  const aceso = caixa.querySelector('[aria-selected="true"]');
  if (aceso) aceso.scrollIntoView({ block: "nearest", inline: "center" });
}
