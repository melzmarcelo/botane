"""Aplica o layout novo (protótipo aprovado em 05/11/2026) sobre uma cópia do site/index.html.

Uso: python aplicar.py <arquivo>
Cada troca exige que o trecho original apareça UMA vez — se o site mudou, para e diz onde.
"""
import re
import sys
from pathlib import Path

alvo = Path(sys.argv[1])
s = alvo.read_text(encoding="utf-8")


def troca(antes: str, depois: str) -> None:
    global s
    n = s.count(antes)
    if n != 1:
        raise SystemExit(f"esperava 1 ocorrência, achei {n}: {antes[:80]!r}")
    s = s.replace(antes, depois)


def troca_entre(inicio: str, fim: str, novo: str) -> None:
    """Troca do começo de `inicio` até o fim de `fim` (inclusive)."""
    global s
    i = s.index(inicio)
    j = s.index(fim, i) + len(fim)
    s = s[:i] + novo + s[j:]


DIR = Path(__file__).parent
CSS_BASE = (DIR / "css-base.css").read_text(encoding="utf-8")
CSS_NOVO = (DIR / "css-novo.css").read_text(encoding="utf-8")

# ---------------------------------------------------------------- fontes e cor da barra
troca('<meta name="theme-color" content="#3C4A3E">', '<meta name="theme-color" content="#234A36">')
troca("family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,600&family=Karla:wght@400;500;700&family=DM+Mono:wght@400;500&display=swap",
      "family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,600&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap")

# ---------------------------------------------------------------- CSS
troca_entre(":root {\n  --papel: #F3EFE4;", ".rot { display: block; font-size: 13px; font-weight: 500; margin-bottom: 6px; }", CSS_BASE)
troca("</style>\n</head>", CSS_NOVO + "\n</style>\n</head>")
# Karla e DM Mono saem: a letra do corpo vira a da casa nova, os números a mesma com tabular.
s = s.replace("Karla, system-ui, -apple-system, sans-serif", "var(--sans)")
s = s.replace("Karla, sans-serif", "var(--sans)")
s = s.replace('"DM Mono", monospace', "var(--sans)")

# ---------------------------------------------------------------- a capa
troca('''<body>
<div class="folha">

  <header class="capa">
    <span class="estado" id="estado">…</span>
    <!-- 🔑 PT · EN · DE (pedido do dono, 29/09/2026). Quem monta é o `montarSeletorDeIdioma`. -->
    <span class="idiomas" id="idiomas" role="group" aria-label="idioma · language · Sprache"></span>
    <div class="marca" id="marca"><b>Botané</b><span>comida de raiz</span></div>
  </header>''', '''<body data-tela-atual="inicio">
<div class="folha">

  <!-- 🔑 **Layout novo (protótipo aprovado pelo dono, 05/11/2026):** a capa verde só no
       início, com a logo, a saudação e o nome; as outras telas abrem direto no título. -->
  <header class="capa">
    <div class="capa-topo">
      <!-- 🔑 PT · EN · DE (pedido do dono, 29/09/2026). Quem monta é o `montarSeletorDeIdioma`. -->
      <span class="idiomas" id="idiomas" role="group" aria-label="idioma · language · Sprache"></span>
      <span class="estado" id="estado">…</span>
    </div>
    <div class="capa-casa">
      <div class="marca" id="marca"><b>Botané</b><span>comida de raiz</span></div>
      <div>
        <p class="saudacao" id="saudacao">Olá!</p>
        <h1 id="nome-da-casa">Botané Deli e Café</h1>
      </div>
    </div>
  </header>''')

ICONE_CAL = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h16v14H4z M4 10h16 M9 3v4 M15 3v4"/></svg>'
SETA = '<svg class="seta" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>'
ICONE_ZAP = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20l1.3-3.9A8 8 0 1 1 8 19z M9 10c.5 2 2 3.5 4 4"/></svg>'
ICONE_LOCAL = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z M12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z"/></svg>'
CHECK = '<div class="selo-ok" aria-hidden="true"><svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></div>'

# ---------------------------------------------------------------- o início
troca('''    <section class="tela" data-tela="inicio" data-ativa>
      <h2 id="nome-da-casa">Botané Deli e Café</h2>
      <!-- 🔑 A casa escolhida, e a saída para a outra. Só aparece com mais de
           uma loja no site — com uma, não há o que trocar. -->
      <p class="sub" id="loja-atual" hidden></p>
      <p class="sub" id="linha-dias">…</p>
      <div class="itens" id="itens">
        <button class="item destaque" id="ir-reservar">Reserve sua Mesa</button>
        <!-- 🔑 Os catálogos entram AQUI, um por cardápio, e cada um abre o PDF.
             Quem os monta é o `carregarCatalogos()`. -->
      </div>
    </section>''', f'''    <section class="tela" data-tela="inicio" data-ativa>
      <!-- 🔑 A casa escolhida, e a saída para a outra. Só aparece com mais de
           uma loja no site — com uma, não há o que trocar. -->
      <p class="sub loja-atual" id="loja-atual" hidden></p>
      <!-- 🔑 A reserva é a porta grande (protótipo, 05/11/2026): é o que a casa quer que
           aconteça. ⚠️ O título fica num <strong> só dele — é o texto que a tradução troca. -->
      <button class="porta porta-reserva" id="ir-reservar" type="button">
        <span class="porta-icone">{ICONE_CAL}</span>
        <span class="porta-texto"><strong>Reserve sua Mesa</strong><small>Escolha o dia, o horário e quantas pessoas</small></span>
        {SETA}
      </button>
      <!-- Cardápio e fidelidade lado a lado; sobrando um, ele ocupa a linha. -->
      <div class="atalhos" id="atalhos"></div>
      <!-- 🔑 **N catálogos** (pedido do dono, 05/11/2026): a fileira rola de lado, e
           "Ver tudo" abre a grade com todos. Quem monta é o `carregarCatalogos()`. -->
      <section class="bloco-catalogos" id="bloco-catalogos" aria-labelledby="t-bloco-catalogos" hidden>
        <div class="bloco-titulo">
          <h2 id="t-bloco-catalogos">Catálogos</h2>
          <button type="button" class="ver-tudo" id="ver-catalogos" data-ir="catalogos" hidden>Ver tudo</button>
        </div>
        <div class="itens carrossel" id="itens"></div>
      </section>
      <button class="porta porta-contato" id="ir-contato" type="button" data-ir="contato">
        <span class="porta-icone">{ICONE_ZAP}</span>
        <span class="porta-texto"><strong>Fale com a gente</strong><small>WhatsApp, endereço e horários</small></span>
        {SETA}
      </button>
      <div class="info-casa">
        {ICONE_LOCAL}
        <div><p id="rodape"></p><p id="linha-dias">…</p></div>
      </div>
    </section>

    <!-- ================= todos os catálogos ================= -->
    <section class="tela" data-tela="catalogos" aria-labelledby="t-catalogos">
      <button class="voltar" data-ir="inicio">‹ voltar</button>
      <h2 id="t-catalogos">Catálogos</h2>
      <div class="grade-catalogos" id="lista-catalogos"></div>
    </section>''')
troca('''    <p class="pe" id="rodape"></p>
  </div>
</div>''', '''  </div>
</div>
<!-- 🔑 As abas de baixo (protótipo, 05/11/2026): o caminho de qualquer tela para as quatro
     portas. Cada uma só aparece se a casa oferece aquilo — quem monta é `montarAbas()`. -->
<nav class="abas" id="abas" aria-label="Principal" hidden>
  <button type="button" data-aba="inicio" aria-current="page"><span class="pilula"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 11l9-7 9 7v9h-6v-6H9v6H3z"/></svg></span><span>Início</span></button>
  <button type="button" data-aba="cardapio" hidden><span class="pilula"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z M9 8h6 M9 12h6"/></svg></span><span>Cardápio</span></button>
  <button type="button" data-aba="reserva" hidden><span class="pilula"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h16v14H4z M4 10h16 M9 3v4 M15 3v4"/></svg></span><span>Reservar</span></button>
  <button type="button" data-aba="fidelidade" hidden><span class="pilula"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l2.6 5.3 5.9.9-4.2 4.1 1 5.8L12 16.4 6.7 19.1l1-5.8L3.5 9.2l5.9-.9z"/></svg></span><span>Fidelidade</span></button>
</nav>''')

# ---------------------------------------------------------------- a reserva
troca('''      <div class="dupla">
        <label class="campo">Quantas pessoas
          <input id="pessoas" type="number" inputmode="numeric" min="1" max="20" value="2">
        </label>
        <label class="campo">Que dia
          <input id="dia" type="date">
        </label>
      </div>
      <div>
        <span class="rot">Horários com mesa</span>''', '''      <!-- 🔑 Protótipo (05/11/2026): pessoas com − e +, o dia em botões (os próximos dias em
           que a casa abre) e, para mais longe, o calendário. ⚠️ Os campos de sempre
           (`#pessoas`, `#dia`) continuam sendo a fonte: os botões só os preenchem. -->
      <div class="pessoas-linha">
        <label for="pessoas"><strong>Quantas pessoas</strong><small>Grupos maiores, fale com a gente</small></label>
        <span class="passos-pessoas">
          <button type="button" class="passo" id="menos-pessoas" aria-label="Menos uma pessoa">−</button>
          <input id="pessoas" type="number" inputmode="numeric" min="1" max="20" value="2">
          <button type="button" class="passo mais" id="mais-pessoas" aria-label="Mais uma pessoa">+</button>
        </span>
      </div>
      <div>
        <span class="rot">Que dia</span>
        <div class="dias" id="dias" role="group" aria-label="Que dia"></div>
        <label class="campo outro-dia">Outro dia
          <input id="dia" type="date">
        </label>
      </div>
      <div>
        <span class="rot">Horários com mesa</span>''')

# ---------------------------------------------------------------- telas de "pronto"
troca('''      <h2 id="t-pronto">Pronto!</h2>''', f'''      {CHECK}
      <h2 id="t-pronto">Pronto!</h2>''')
troca('''      <h2 id="t-pedido-pronto">Pedido enviado!</h2>''', f'''      {CHECK}
      <h2 id="t-pedido-pronto">Pedido enviado!</h2>''')

# ---------------------------------------------------------------- a seção do cardápio: pílulas
troca('''      <h2 id="t-secao">Categoria</h2>''', '''      <!-- 🔑 Protótipo (05/11/2026): as seções do cardápio em pílulas, para trocar sem voltar. -->
      <div class="pilulas" id="pilulas-secoes" role="tablist" aria-label="seções do cardápio"></div>
      <h2 id="t-secao">Categoria</h2>''')

# ---------------------------------------------------------------- fidelidade: o cartão verde
troca('''      <div class="carimbos" id="carimbos" aria-live="polite"></div>
      <p class="falta" id="falta"></p>''', '''      <!-- 🔑 Protótipo (05/11/2026): o cartão verde, com a conta no canto e os selos. -->
      <div class="cartao-fidelidade">
        <div class="cf-topo">
          <div><small>Cartão fidelidade</small><b class="cf-casa" id="cf-casa">Botané</b></div>
          <div class="cf-conta" id="cf-conta"></div>
        </div>
        <div class="carimbos" id="carimbos" aria-live="polite"></div>
        <p class="falta" id="falta"></p>
      </div>''')

JS = (DIR / "js-novo.js").read_text(encoding="utf-8")
JS_TRAD = (DIR / "traducoes-novas.js").read_text(encoding="utf-8")

# ---------------------------------------------------------------- traduções novas
troca('''const TRADUCOES = {
  // ---- capa e navegação''', '''const TRADUCOES = {
''' + JS_TRAD + '''
  // ---- capa e navegação''')

# ---------------------------------------------------------------- ir(): a tela no <body> e a aba
troca('''  if (location.hash !== "#" + nome) history.pushState({ tela: nome }, "", "#" + nome);
  atualizarBarra(nome);
}''', '''  if (location.hash !== "#" + nome) history.pushState({ tela: nome }, "", "#" + nome);
  // 🔑 Layout novo: a capa só no início (CSS lê o `data-tela`), e a aba acesa.
  document.body.dataset.telaAtual = nome;
  marcarAba(nome);
  atualizarBarra(nome);
}''')

# ---------------------------------------------------------------- a casa
troca('''  $("#nome-da-casa").textContent = casa.casa;''', '''  $("#nome-da-casa").textContent = casa.casa;
  $("#cf-casa").textContent = casa.casa;
  $("#saudacao").textContent = saudacao();''')
troca('''  $("#estado").textContent = casa.aberta_agora''', '''  $("#estado").classList.toggle("fechado", !casa.aberta_agora);
  $("#estado").textContent = casa.aberta_agora''')
troca('''  montarContato();
  montarPortaDeFidelidade();
  montarPortaDeContato();
}''', '''  montarContato();
  montarPortaDeFidelidade();
  montarDias();
}''')

# fidelidade vira atalho; contato vira porta fixa no HTML
troca_entre("function montarPortaDeFidelidade() {", '''  $("#itens").appendChild(porta);
}''', JS)

# o contato: WhatsApp grande, dados num cartão e "Como chegar"
troca('''    l.push(`<a class="item" href="${zap}" target="_blank" rel="noopener">WhatsApp</a>`);''',
      '''    l.push(`<a class="item destaque zap" href="${zap}" target="_blank" rel="noopener">${ICONE_ZAP}<span>Conversar no WhatsApp</span></a>`);''')
troca('''  if (casa.telefone) l.push(linha("Telefone", esc(casa.telefone), `tel:${esc(casa.telefone)}`));''',
      '''  const dados = [];
  if (casa.endereco) {
    dados.push(linha("Endereço", esc(casa.endereco)
      + (casa.cidade ? " — " + esc(casa.cidade) + "/" + esc(casa.uf) : "")));
  }
  if ((casa.dias || []).length) {
    dados.push(linha("Horário", esc(casa.dias.map((d) => t(d)).join(" · "))
      + (casa.hoje ? " · " + esc(t("hoje {horas}", { horas: tHorario(casa.hoje) })) : "")));
  }
  if (casa.telefone) dados.push(linha("Telefone", esc(casa.telefone), `tel:${esc(casa.telefone)}`));''')
troca('''  if (casa.email) l.push(linha("E-mail", esc(casa.email), `mailto:${esc(casa.email)}`));
  if (casa.endereco) {
    l.push(linha("Onde estamos", esc(casa.endereco)
      + (casa.cidade ? " — " + esc(casa.cidade) + "/" + esc(casa.uf) : "")));
  }
  $("#bloco-contato").innerHTML = l.join("");''', '''  if (casa.email) dados.push(linha("E-mail", esc(casa.email), `mailto:${esc(casa.email)}`));
  if (dados.length) l.push(`<div class="cartao-dados">${dados.join("")}</div>`);
  // 🔑 "Como chegar" abre o mapa com o ENDEREÇO da casa — dado público, que ela cadastrou.
  if (casa.endereco) {
    const onde = [casa.endereco, casa.cidade, casa.uf].filter(Boolean).join(", ");
    l.push(`<a class="item" href="https://www.google.com/maps/search/?api=1&query=${
      encodeURIComponent(onde)}" target="_blank" rel="noopener">Como chegar</a>`);
  }
  $("#bloco-contato").innerHTML = l.join("");''')

# ---------------------------------------------------------------- os catálogos: cartões
troca_entre('''  // ⚠️ Entram DEPOIS do "Reservar" e ANTES do contato''', '''    if (contato) $("#itens").insertBefore(a, contato);
    else $("#itens").appendChild(a);
  });
}''', '''  // 🔑 **Layout novo (05/11/2026): cada catálogo é um CARTÃO com capa**, na fileira do início
  // e na grade de "Ver tudo" — a casa pode ter N. A capa vem do servidor (`capa`: a 1ª foto
  // das seções ou dos produtos); sem ela, um ícone.
  // 🔑 **Duas origens, dois destinos.** O catálogo de PDF abre o arquivo em outra aba, como
  // sempre; o montado por produtos abre DENTRO do site. Quem decide é o servidor (`origem`).
  // 🔑 **O que exige cadastro chega SEM conteúdo** — só o id. O cartão leva à identificação.
  // ⚠️ O cartão tem como TEXTO só o nome: a capa é decorativa (`aria-hidden`).
  const fileira = $("#itens"), grade = $("#lista-catalogos");
  fileira.innerHTML = ""; grade.innerHTML = "";
  lista.forEach((c) => {
    const pdf = !(c.origem === "PRODUTOS" || c.exige_cadastro) ? `${API}${c.arquivo_url}` : null;
    fileira.appendChild(cartaoDeCatalogo(c, pdf));
    grade.appendChild(cartaoDeCatalogo(c, pdf));
  });
  $("#bloco-catalogos").hidden = false;
  $("#t-bloco-catalogos").textContent = lista.length === 1 ? "Catálogo" : "Catálogos";
  $("#ver-catalogos").hidden = lista.length < 3;
  montarAtalhoDoCardapio();
}''')
troca('''function destravarCatalogos() {
  $("#itens").querySelectorAll("button[data-catalogo]").forEach(async (b) => {''', '''function destravarCatalogos() {
  document.querySelectorAll("button[data-catalogo]").forEach(async (b) => {''')
troca('''      const a = document.createElement("a");
      a.className = "item";
      a.href = `${API}${r.arquivo_url}`;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = c.nome;
      b.replaceWith(a);''', '''      b.replaceWith(cartaoDeCatalogo(c, `${API}${r.arquivo_url}`));''')

# ---------------------------------------------------------------- a seção: pílulas
troca('''  $("#t-secao").textContent = c.nome;
  const desc = $("#secao-descricao");''', '''  $("#t-secao").textContent = c.nome;
  desenharPilulas(indice);
  const desc = $("#secao-descricao");''')

# ---------------------------------------------------------------- fidelidade: a conta no canto
troca('''  $("#falta").innerHTML = c.faltam
    ? `<b>${t("{feitas} de {total}", { feitas: c.no_cartao, total })}</b>${t(c.faltam === 1
      ? "falta 1 visita para o prêmio" : "faltam {n} visitas para o prêmio", { n: c.faltam })}`
    : `<b>${t("Cartão completo!")}</b>`;''', '''  // 🔑 Protótipo (05/11/2026): a conta "6/10" no canto do cartão; embaixo, o que falta.
  $("#cf-conta").innerHTML = `${c.no_cartao}<span>/${total}</span><small>${esc(t("visitas"))}</small>`;
  $("#cf-conta").setAttribute("aria-label", t("{feitas} de {total}", { feitas: c.no_cartao, total }));
  $("#falta").innerHTML = c.faltam
    ? esc(t(c.faltam === 1 ? "falta 1 visita para o prêmio" : "faltam {n} visitas para o prêmio", { n: c.faltam }))
    : `<b>${t("Cartão completo!")}</b>`;''')

# ---------------------------------------------------------------- os horários: o dia aceso
troca('''async function buscarHorarios() {
  const dia = $("#dia").value;''', '''async function buscarHorarios() {
  marcarDia();
  const dia = $("#dia").value;''')

# ---------------------------------------------------------------- começo: pessoas e abas
troca('''  $("#pessoas").addEventListener("input", buscarHorarios);''', '''  $("#pessoas").addEventListener("input", buscarHorarios);
  // 🔑 − e + mexem no MESMO campo, e avisam como se a pessoa tivesse digitado.
  const passo = (n) => {
    const campo = $("#pessoas");
    const v = Math.min(Number(campo.max) || 20, Math.max(1, (Number(campo.value) || 0) + n));
    campo.value = v;
    campo.dispatchEvent(new Event("input", { bubbles: true }));
  };
  $("#menos-pessoas").addEventListener("click", () => passo(-1));
  $("#mais-pessoas").addEventListener("click", () => passo(1));
  $("#abas").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-aba]");
    if (!b) return;
    const aba = b.dataset.aba;
    if (aba === "inicio") return ir("inicio");
    if (aba === "reserva") return $("#ir-reservar").click();
    if (aba === "fidelidade") return abrirFidelidade();
    if (aba === "cardapio") return abrirCatalogos();
  });''')
troca('''  Promise.all([carregarCasa().then(carregarCatalogos), aceita]).then(restaurarTela);''',
      '''  Promise.all([carregarCasa().then(carregarCatalogos), aceita]).then(montarAbas).then(restaurarTela);''')
troca('''  if (tela === "contato") return ir("contato");''', '''  if (tela === "contato") return ir("contato");
  if (tela === "catalogos" && catalogosDaCasa.length) return ir("catalogos");''')

alvo.write_text(s, encoding="utf-8")
print("ok", alvo, len(s))
