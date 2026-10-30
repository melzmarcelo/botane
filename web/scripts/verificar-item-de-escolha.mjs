/**
 * O ITEM DE ESCOLHA (migração 142) no navegador: o cadastro, o feed e o site.
 *
 * 🔑 Pedido do dono (29/10/2026): "Chocolate Quente → Preto ou Branco"; "Monte sua cesta →
 * embalagem, depois os itens, de um mínimo a um máximo, somando o valor". Decisões: o item
 * repete na cesta, e aparece no site e na mesa. Estudo em `docs/item-de-escolha-estudo.md`.
 * O cenário é montado pela API e sai no fim (o catálogo é inativado e deixa de ser Vivo).
 *
 *    node scripts/verificar-item-de-escolha.mjs     (API na 9200 e o Next na 3100 de pé)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const API = "http://127.0.0.1:9200";
const WEB = "http://127.0.0.1:3100";
const MARCA = String(Date.now()).slice(-6);
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(metodo, caminho, corpo, token) {
  const r = await fetch(API + caminho, {
    method: metodo,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const texto = await r.text();
  return { status: r.status, dados: texto ? JSON.parse(texto) : null };
}

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;
const { dados: par } = await api("GET", "/unidades/1/parametros", undefined, token);
await api("PUT", "/unidades/1/parametros", { ...par, reservas_ligado: true }, token);

async function produto(nome, preco) {
  const { dados: p } = await api("POST", "/produtos", { nome: `${nome} ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", controla_estoque: false }, token);
  const { dados: atual } = await api("GET", `/produtos/${p.id}`, undefined, token);
  await api("PUT", `/produtos/${p.id}`, { ...atual, integrado_pdv: true, preco_venda: preco }, token);
  return p.id;
}

console.log("0. cenário: chocolates e a cesta, num catálogo que é Cardápio Vivo e aceita pedido");
const PRETO = await produto("CHOC PRETO", 14), BRANCO = await produto("CHOC BRANCO", 16);
const MEDIA = await produto("CESTA MEDIA", 30), GELEIA = await produto("CESTA GELEIA", 12), PAO = await produto("CESTA PAO", 8);
await api("PUT", `/produtos/${MEDIA}/adicionais`, [
  { nome: "Itens da cesta", minimo: 2, maximo: 3, permite_repetir: true,
    opcoes: [{ nome: "Geleia", id_produto_ref: GELEIA }, { nome: "Pão", id_produto_ref: PAO }] }], token);
const { dados: cat } = await api("POST", "/catalogos", { nome: `Escolha ${MARCA}`, origem: "PRODUTOS", situacao: "ATIVO" }, token);
const { dados: g } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Bebidas" }, token);
const { dados: cesta } = await api("POST", `/catalogos/categorias/${g.id}/escolhas`, {
  nome: "Monte sua cesta", opcoes: [{ id_produto: MEDIA, rotulo: "Média" }, { id_produto: BRANCO, rotulo: "Só o chocolate" }],
}, token);
await api("PUT", `/pedidos/config/${cat.id}`, {
  aceita: true, retirada: true, entrega: false, taxa_entrega: 0, pedido_minimo: 0,
  antecedencia_min: 30, antecedencia_max_dias: 7, pagamentos: ["RETIRADA"], texto_pagamento: null,
}, token);
const SLUG = `escolha-${MARCA}`;
await api("PUT", `/cardapio-vivo/vivos/${cat.id}`, { slug: SLUG }, token);

const navegador = await puppeteer.launch({
  executablePath: CHROME, headless: "new", userDataDir: "scripts/_chrome-perfil-site",
  args: ["--no-sandbox"], defaultViewport: { width: 420, height: 900 },
});
let idChoc = null;
try {
  const p = await navegador.newPage();

  console.log("\n1. o cadastro: + item de escolha na seção");
  await p.setViewport({ width: 1280, height: 900 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  await p.goto(`${WEB}/catalogos/${cat.id}?aba=cardapio`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#nova-escolha", { timeout: 20000 }).catch(() => {});
  checar("a seção tem o botão '+ item de escolha'", !!(await p.$("#nova-escolha")));
  await p.click("#nova-escolha");
  await p.waitForSelector("#escolha-nome", { timeout: 8000 }).catch(() => {});
  await p.type("#escolha-nome", "Chocolate Quente");
  checar("sem duas opções, Criar fica desligado",
    await p.$eval("#escolha-criar", (b) => b.disabled).catch(() => false));
  for (const [busca, rotulo] of [[`CHOC PRETO ${MARCA}`, "Preto"], [`CHOC BRANCO ${MARCA}`, "Branco"]]) {
    await p.type("#escolha-busca", busca);
    await p.waitForFunction((b) => [...document.querySelectorAll('[role="dialog"] button')]
      .some((x) => x.textContent.includes(b) && x.textContent.includes("+ pôr")), { timeout: 8000 }, busca).catch(() => {});
    await p.evaluate((b) => [...document.querySelectorAll('[role="dialog"] button')]
      .find((x) => x.textContent.includes(b) && x.textContent.includes("+ pôr"))?.click(), busca);
    await p.waitForSelector(`input[aria-label="rótulo de ${busca}"]`, { timeout: 5000 }).catch(() => {});
    await p.type(`input[aria-label="rótulo de ${busca}"]`, rotulo);
  }
  checar("com duas opções, Criar liga", await p.$eval("#escolha-criar", (b) => !b.disabled).catch(() => false));
  await p.click("#escolha-criar");
  // Criado, a gaveta do item abre com as opções.
  // ⚠️ O título da parte é `.rotulo` (caixa alta por CSS): o innerText já vem em maiúsculas.
  const gaveta = await p.waitForFunction(() => /o item de escolha/i.test(document.body.innerText)
    && /item de escolha · 2 opções/i.test(document.body.innerText)
    && !!document.querySelector("#escolha-salvar"), { timeout: 10000 }).then(() => true).catch(() => false);
  checar("criado, a gaveta do item abre com as duas opções", gaveta);
  const { dados: ct } = await api("GET", `/catalogos/${cat.id}/conteudo`, undefined, token);
  const choc = ct.categorias[0].itens.find((i) => i.produto === "Chocolate Quente");
  idChoc = choc?.id ?? null;
  checar("no servidor: tipo ESCOLHA, Preto e Branco, nessa ordem",
    choc?.tipo === "ESCOLHA" && choc.escolhas.map((o) => o.nome).join() === "Preto,Branco", choc);
  await p.keyboard.press("Escape");
  await esperar(300);
  const linha = await p.evaluate(() => document.body.innerText.includes("item de escolha: Preto, Branco")
    && /a partir de\s*R\$\s*14,00/.test(document.body.innerText));
  checar("a linha do cardápio diz 'item de escolha: Preto, Branco' e 'a partir de R$ 14,00'", linha);

  console.log("\n2. o feed (sem mesa: seleção)");
  await p.setViewport({ width: 420, height: 900 });
  await p.goto(`${WEB}/c/1?cardapio=${SLUG}`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => document.body.innerText.includes("Monte sua cesta")
    || document.body.innerText.includes("Ver cardápio"), { timeout: 20000 }).catch(() => {});
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Ver cardápio")?.click());
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Entendi")?.click());
  await p.waitForFunction(() => document.body.innerText.includes("Monte sua cesta"), { timeout: 15000 }).catch(() => {});
  // O botão do cartão abre o detalhe (o item precisa ser montado).
  await p.evaluate(() => {
    const sec = [...document.querySelectorAll("section")].find((s) => s.innerText.includes("Monte sua cesta"));
    [...(sec?.querySelectorAll("button") ?? [])].find((b) => b.textContent.includes("Adicionar"))?.click();
  });
  const detalhe = await p.waitForSelector('[role="dialog"][aria-label="Monte sua cesta"]', { timeout: 8000 }).then(() => true).catch(() => false);
  checar("tocar em Adicionar abre o detalhe com 'Escolha uma opção'", detalhe
    && await p.evaluate(() => document.querySelector('[role="dialog"]').innerText.includes("Escolha uma opção")));
  const botaoPedir = () => p.evaluate(() => {
    const b = [...document.querySelectorAll('[role="dialog"] button')].find((x) => x.textContent.includes("Adicionar à minha seleção"));
    return b ? { desligado: b.disabled, texto: b.textContent } : null;
  });
  checar("sem escolher, o botão fica desligado", (await botaoPedir())?.desligado === true, await botaoPedir());
  await p.evaluate(() => [...document.querySelectorAll('[role="dialog"] label')].find((l) => l.textContent.includes("Média"))?.querySelector("input")?.click());
  await esperar(200);
  const grupoApareceu = await p.evaluate(() => document.querySelector('[role="dialog"]').innerText.includes("Itens da cesta"));
  checar("escolhida a Média, aparecem os itens da cesta (com contador)", grupoApareceu
    && !!(await p.$('[role="dialog"] button[aria-label="+ Geleia"]')));
  checar("abaixo do mínimo (0 de 2), ainda desligado", (await botaoPedir())?.desligado === true);
  await p.click('[role="dialog"] button[aria-label="+ Geleia"]');
  await p.click('[role="dialog"] button[aria-label="+ Geleia"]');
  await p.click('[role="dialog"] button[aria-label="+ Pão"]');
  const cheio = await p.$eval('[role="dialog"] button[aria-label="+ Pão"]', (b) => b.disabled);
  checar("no máximo (3), o + desliga", cheio);
  const b = await botaoPedir();
  checar("2 geleias + 1 pão na Média: 30 + 24 + 8 = R$ 62,00 no botão",
    b?.desligado === false && /62,00/.test(b.texto), b);
  await p.evaluate(() => [...document.querySelectorAll('[role="dialog"] button')]
    .find((x) => x.textContent.includes("Adicionar à minha seleção"))?.click());
  await esperar(400);
  await p.evaluate(() => [...document.querySelectorAll("header button")].find((x) => x.textContent.includes("★"))?.click());
  await p.waitForFunction(() => document.body.innerText.includes("Fazer encomenda"), { timeout: 8000 }).catch(() => {});
  const sel = await p.evaluate(() => document.body.innerText);
  checar("a seleção mostra 'Monte sua cesta · Média' e '2× Geleia · Pão'",
    sel.includes("Monte sua cesta · Média") && sel.includes("2× Geleia · Pão"), sel.slice(0, 400));

  console.log("\n3. a encomenda leva a escolha ao carrinho do site, e o pedido sai certo");
  await Promise.all([
    p.waitForNavigation({ waitUntil: "networkidle2", timeout: 20000 }).catch(() => {}),
    p.evaluate(() => [...document.querySelectorAll("button")].find((x) => x.textContent.includes("Fazer encomenda"))?.click()),
  ]);
  await p.waitForFunction(() => document.querySelector('[data-tela="carrinho"][data-ativa]'), { timeout: 20000 }).catch(() => {});
  const carrinho = await p.evaluate(() => document.querySelector('[data-tela="carrinho"]')?.innerText ?? "");
  checar("o carrinho do site tem a linha montada, com os adicionais e o preço",
    carrinho.includes("Monte sua cesta · Média") && carrinho.includes("2× Geleia · Pão") && carrinho.includes("62,00"),
    carrinho.slice(0, 400));
  const guardado = await p.evaluate(() => JSON.parse(sessionStorage.getItem("botane.carrinho") || "null"));
  const linhaC = guardado && Object.values(guardado.itens)[0];
  checar("e guarda a escolha (o produto) e os adicionais para o envio",
    linhaC?.escolha === MEDIA_ID() && (linhaC.adicionais || []).length === 2, linhaC);

  console.log("\n4. o site, direto: Escolher abre a janela de montar");
  // ⚠️ Sendo Cardápio Vivo, o site levaria ao feed: tira-se o Vivo para ver as seções do site.
  await api("DELETE", `/cardapio-vivo/vivos/${cat.id}`, undefined, token);
  await p.evaluate(() => sessionStorage.removeItem("botane.carrinho"));
  await p.goto(`${WEB}/portal?loja=1`, { waitUntil: "networkidle2" });
  await p.waitForSelector(`#itens [data-catalogo="${cat.id}"]`, { timeout: 15000 }).catch(() => {});
  await p.click(`#itens [data-catalogo="${cat.id}"]`).catch(() => {});
  await p.waitForSelector(".acessar", { visible: true, timeout: 15000 }).catch(() => {});
  await p.click(".acessar").catch(() => {});
  await p.waitForFunction(() => [...document.querySelectorAll(".pedir button")].some((b) => b.textContent === "Escolher"),
    { timeout: 15000 }).catch(() => {});
  const temEscolher = await p.evaluate(() => [...document.querySelectorAll(".pedir button")].some((b) => b.textContent === "Escolher"));
  checar("o item de escolha mostra 'Escolher' (e 'a partir de')", temEscolher
    && await p.evaluate(() => /a partir de/.test(document.body.innerText)));
  if (temEscolher) {
    await p.evaluate(() => {
      const pr = [...document.querySelectorAll(".prato")].find((x) => x.innerText.includes("Chocolate Quente"));
      pr?.querySelector(".pedir button")?.click();
    });
    await p.waitForSelector("#montar[open]", { timeout: 5000 }).catch(() => {});
    const desl = await p.$eval("#por-montar", (x) => x.disabled).catch(() => null);
    checar("a janela abre, e sem escolher o Adicionar fica desligado", desl === true);
    await p.evaluate(() => [...document.querySelectorAll("#corpo-montar label")].find((l) => l.textContent.includes("Branco"))?.querySelector("input")?.click());
    const t2 = await p.$eval("#por-montar", (x) => ({ d: x.disabled, t: x.textContent })).catch(() => null);
    checar("escolhido o Branco, liga com R$ 16,00", t2 && !t2.d && t2.t.includes("16,00"), t2);
    await p.click("#por-montar");
    await esperar(300);
    const barra = await p.evaluate(() => document.querySelector("#barra-carrinho")?.innerText ?? "");
    checar("vai ao pedido: a barra mostra 1 item · R$ 16,00", /1 item/.test(barra) && barra.includes("16,00"), barra);
  }
} finally {
  await navegador.close();
  await api("DELETE", `/cardapio-vivo/vivos/${cat.id}`, undefined, token);
  await api("PUT", `/catalogos/${cat.id}`, { situacao: "INATIVO" }, token);
  await api("PUT", "/unidades/1/parametros", par, token);
}

function MEDIA_ID() { return MEDIA; }

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((f) => console.log(`  - ${f}`));
process.exit(falhas.length ? 1 : 0);
