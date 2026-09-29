/**
 * O pedido pelo cardápio, no SITE do cliente (porta 3200): adicionar, barra do carrinho,
 * escolher dia e hora, identificar pelo telefone, enviar e ver em "Meus pedidos".
 *
 * 🔑 Pedido do dono (28/09/2026) — ver `docs/pedidos-estudo.md`. A bateria `verificar.mjs`
 * cobre o sistema interno; o site do cliente é outro endereço, e o carrinho mora só nele.
 * O cenário (catálogo, itens, cliente) é montado pela API; o catálogo sai no fim.
 * ⚠️ O pedido e a cliente de teste (nome "Site Pedido") FICAM — não há rota para apagá-los,
 * de propósito. Limpar: `DELETE FROM pedidos WHERE nome = 'Site Pedido'` e o mesmo em
 * `reserva_clientes`.
 *
 *    node scripts/verificar-pedido-site.mjs     (API na 9200 e site na 3200 de pé)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const API = "http://127.0.0.1:9200";
const SITE = "http://127.0.0.1:3200";
const MARCA = String(Date.now()).slice(-6);
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};

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

console.log("0. cenário: um cardápio que aceita pedido, e uma cliente cadastrada");
const { dados: cat } = await api("POST", "/catalogos", { nome: `Pedido site ${MARCA}`, origem: "PRODUTOS", situacao: "ATIVO" }, token);
const { dados: g } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Doces" }, token);
for (const [n, v] of [["SITE BRIGADEIRO", 6], ["SITE BOLO FATIA", 14]]) {
  await api("POST", `/catalogos/categorias/${g.id}/itens`, { id_produto: await produto(n, v) }, token);
}
await api("PUT", `/pedidos/config/${cat.id}`, {
  aceita: true, retirada: true, entrega: false, taxa_entrega: 0, pedido_minimo: 0,
  antecedencia_min: 30, antecedencia_max_dias: 7, pagamentos: ["RETIRADA", "WHATSAPP"],
  texto_pagamento: "Pagamento na retirada.",
}, token);
const FONE = `4798${String(Date.now()).slice(-7)}`;
const cad = await api("POST", "/publico/1/cliente", {
  telefone: FONE, nome: "Site Pedido", genero: "FEMININO", cidade: "Blumenau",
  nascimento: "1992-03-04", aceite_termo: true });
checar("a cliente de teste existe", cad.status === 200, cad);

const navegador = await puppeteer.launch({
  executablePath: CHROME, headless: "new", userDataDir: "scripts/_chrome-perfil-site",
  args: ["--no-sandbox"], defaultViewport: { width: 420, height: 900 },
});
try {
  const p = await navegador.newPage();
  await p.goto(`${SITE}/?loja=1`, { waitUntil: "networkidle2" });
  await p.waitForSelector(`#itens [data-catalogo="${cat.id}"]`, { timeout: 15000 });

  console.log("\n1. o carrinho no cardápio");
  await p.click(`#itens [data-catalogo="${cat.id}"]`);
  await p.waitForSelector(".acessar", { visible: true, timeout: 15000 });
  await p.click(".acessar");
  await p.waitForSelector(".pedir .adicionar", { visible: true, timeout: 10000 });
  checar("cada item com preço tem 'Adicionar'", (await p.$$(".pedir .adicionar")).length === 2);
  checar("a barra do carrinho começa escondida", await p.$eval("#barra-carrinho", (b) => b.hidden));
  await p.click(".pedir .adicionar");
  await p.waitForSelector(".contador", { timeout: 5000 });
  await p.evaluate(() => document.querySelector('.contador button[aria-label="pôr mais um"]').click());
  const barra = await p.$eval("#barra-carrinho", (b) => ({ hidden: b.hidden, texto: b.innerText }));
  checar("dois toques: a barra aparece com 2 itens e o total", !barra.hidden && /2 itens/.test(barra.texto) && /12,00/.test(barra.texto), barra);

  console.log("\n2. o pedido");
  await p.click("#barra-carrinho");
  await p.waitForSelector('[data-tela="carrinho"][data-ativa]', { timeout: 5000 });
  const tela = await p.$eval('[data-tela="carrinho"]', (t) => t.innerText);
  checar("o carrinho mostra o item, a retirada, o pagamento e o texto da casa",
    /BRIGADEIRO|Brigadeiro/i.test(tela) && /Retirar na loja/.test(tela) && /Pagamento na retirada/.test(tela), tela.slice(0, 300));
  await p.click('#quando-pedido [data-quando="agendar"]');
  const agendado = await p.evaluate(() => {
    const sel = document.querySelector("#dia-pedido");
    // O último dia da lista é longe o bastante para qualquer hora do dia de hoje.
    sel.value = sel.options[sel.options.length - 1].value;
    document.querySelector("#hora-pedido").value = "12:00";
    return sel.value;
  });
  await p.click("#enviar-pedido");
  await p.waitForSelector('[data-tela="quem"][data-ativa]', { timeout: 5000 });
  checar("sem identificação, pede o telefone antes de enviar",
    /Seu pedido/.test(await p.$eval("#t-quem", (h) => h.textContent)));
  await p.type("#fone", FONE);
  await p.click("#avancar");
  await p.waitForSelector('[data-tela="pedido-pronto"][data-ativa]', { timeout: 15000 });
  const recibo = await p.$eval("#recibo-pedido", (r) => r.innerText);
  checar("o pedido é enviado e o recibo diz o número", /Pedido nº/.test(recibo) && /\d+/.test(recibo), recibo);
  checar("e a barra some depois do envio", await p.$eval("#barra-carrinho", (b) => b.hidden));

  const { dados: lista } = await api("GET", `/pedidos?situacao=novos&busca=${FONE}`, undefined, token);
  const meu = (lista || [])[0];
  checar("o pedido chegou NOVO na casa, com os 2 brigadeiros e para o dia escolhido",
    meu && meu.itens === 1 && meu.total === 12 && meu.para_quando.startsWith(agendado), { meu, agendado });

  console.log("\n3. meus pedidos");
  await p.click("#pronto-meus-pedidos");
  await p.waitForSelector("#lista-meus-pedidos .pedido-meu", { timeout: 10000 });
  const meus = await p.$eval("#lista-meus-pedidos", (l) => l.innerText);
  checar("'Meus pedidos' mostra o pedido aguardando a casa", /Aguardando a casa confirmar/.test(meus), meus.slice(0, 200));
} finally {
  await navegador.close();
  await api("PUT", "/unidades/1/parametros", par, token);
  await api("DELETE", `/catalogos/${cat.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const f of falhas) console.log("  -", f);
process.exit(falhas.length ? 1 : 0);
