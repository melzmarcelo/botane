/**
 * A encomenda do CATERING (15/10/2026): um segundo Cardápio Vivo, aberto pelo link próprio,
 * cuja seleção vira o carrinho do site — no mesmo endereço, sem passar pelo garçom.
 *
 * 🔑 Pedido do dono: "no Botané vai ter um que é o da cafeteria, e ela pode configurar outro
 * que é destinado ao Catering". A mesa abre o principal; o catering abre por
 * `/c/{loja}?cardapio=…`, e "Fazer encomenda" leva ao carrinho do site (`/portal`).
 * O cenário é montado pela API e sai no fim (o catálogo é inativado e deixa de ser Vivo).
 *
 *    node scripts/verificar-encomenda-feed.mjs     (API na 9200 e o Next na 3100 de pé)
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

console.log("0. cenário: o catering como segundo Cardápio Vivo, aceitando pedido pelo site");
const { dados: cat } = await api("POST", "/catalogos", { nome: `Catering ${MARCA}`, origem: "PRODUTOS", situacao: "ATIVO" }, token);
const { dados: g } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Kits" }, token);
await api("POST", `/catalogos/categorias/${g.id}/itens`, { id_produto: await produto("KIT COFFEE BREAK", 120) }, token);
await api("PUT", `/pedidos/config/${cat.id}`, {
  aceita: true, retirada: true, entrega: false, taxa_entrega: 0, pedido_minimo: 0,
  antecedencia_min: 30, antecedencia_max_dias: 7, pagamentos: ["RETIRADA"], texto_pagamento: null,
}, token);
const SLUG = `catering-${MARCA}`;
const r = await api("PUT", `/cardapio-vivo/vivos/${cat.id}`, { slug: SLUG }, token);
const meu = (r.dados?.vivos ?? []).find((v) => v.id_catalogo === cat.id);
checar("o catering liga como Cardápio Vivo", r.status === 200 && !!meu, r.dados);

const navegador = await puppeteer.launch({
  executablePath: CHROME, headless: "new", userDataDir: "scripts/_chrome-perfil-site",
  args: ["--no-sandbox"], defaultViewport: { width: 420, height: 900 },
});
try {
  const p = await navegador.newPage();
  console.log("\n1. o link do catering abre o feed DELE");
  await p.goto(`${WEB}/c/1?cardapio=${SLUG}`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => document.body.innerText.includes("KIT COFFEE BREAK")
    || document.body.innerText.includes("Ver cardápio"), { timeout: 20000 }).catch(() => {});
  // A entrada (Hub), se a loja a tiver ligada: segue ao feed.
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Ver cardápio")?.click());
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Entendi")?.click());
  checar("o feed mostra o prato do catering", await p.waitForFunction(
    () => document.body.innerText.includes("KIT COFFEE BREAK"), { timeout: 15000 }).then(() => true).catch(() => false));

  console.log("\n2. a seleção vira encomenda");
  await p.evaluate(() => [...document.querySelectorAll("button")]
    .find((b) => b.textContent.includes("Adicionar à minha seleção"))?.click());
  await new Promise((res) => setTimeout(res, 400));
  await p.evaluate(() => [...document.querySelectorAll("header button")].find((b) => b.textContent.includes("★"))?.click());
  const temBotao = await p.waitForFunction(
    () => [...document.querySelectorAll("button")].some((b) => b.textContent.includes("Fazer encomenda")),
    { timeout: 8000 }).then(() => true).catch(() => false);
  checar("sem mesa, num catálogo que aceita pedido, a seleção oferece 'Fazer encomenda'", temBotao);
  await Promise.all([
    p.waitForNavigation({ waitUntil: "networkidle2", timeout: 20000 }).catch(() => {}),
    p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.includes("Fazer encomenda"))?.click()),
  ]);
  await p.waitForFunction(() => document.querySelector('[data-tela="carrinho"][data-ativa]'), { timeout: 20000 }).catch(() => {});
  const carrinho = await p.evaluate(() => ({
    url: location.pathname + location.hash,
    tela: !!document.querySelector('[data-tela="carrinho"][data-ativa]'),
    texto: document.querySelector('[data-tela="carrinho"]')?.innerText ?? "",
  }));
  checar("e o SITE abre o carrinho, no mesmo endereço, com o prato do feed",
    carrinho.tela && carrinho.url.startsWith("/portal") && carrinho.texto.includes("KIT COFFEE BREAK"), carrinho);
  checar("com o jeito de receber e o pagamento do catálogo",
    carrinho.texto.includes("Retirar na loja") && carrinho.texto.includes("Enviar pedido"), carrinho.texto.slice(0, 300));

  console.log("\n3. o voltar devolve ao feed");
  // ⚠️ O site primeiro troca o hash para `#inicio` (o "voltar" do celular não pode cair no
  // carrinho de novo) e SÓ DEPOIS vai ao feed: espera-se o endereço, não a primeira navegação.
  await p.evaluate(() => document.querySelector("#voltar-carrinho")?.click());
  await p.waitForFunction((s) => location.href.includes(`/c/1?cardapio=${s}`), { timeout: 20000 }, SLUG).catch(() => {});
  checar("'‹ cardápio' no carrinho volta ao feed do catering", p.url().includes(`/c/1?cardapio=${SLUG}`), p.url());
} finally {
  await navegador.close();
  await api("DELETE", `/cardapio-vivo/vivos/${cat.id}`, undefined, token);
  await api("PUT", `/catalogos/${cat.id}`, { situacao: "INATIVO" }, token);
  await api("PUT", "/unidades/1/parametros", par, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((f) => console.log(`  - ${f}`));
process.exit(falhas.length ? 1 : 0);
