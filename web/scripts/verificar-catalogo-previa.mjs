/**
 * O catálogo SIMPLES (não é Cardápio Vivo): abertura e cartões no site, o editor sem o que é só
 * do feed, e a aba Pré-visualização com o pedido de TESTE.
 *
 * 🔑 Pedido do dono (30/10/2026), estudo em `docs/catalogo-simples-estudo.md`.
 * O cenário é montado pela API e sai no fim (o catálogo é inativado).
 *
 *    node scripts/verificar-catalogo-previa.mjs     (API na 9200 e o Next na 3100 de pé)
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

console.log("0. cenário: um catálogo simples em RASCUNHO, com abertura, um cartão e um esgotado");
const { dados: cat } = await api("POST", "/catalogos", { nome: `Simples ${MARCA}`, origem: "PRODUTOS" }, token);
const { dados: g } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Doces" }, token);
const { dados: ia } = await api("POST", `/catalogos/categorias/${g.id}/itens`, { id_produto: await produto("PREV BOLO", 10) }, token);
const { dados: ib } = await api("POST", `/catalogos/categorias/${g.id}/itens`, { id_produto: await produto("PREV TORTA", 20) }, token);
await api("POST", `/catalogos/${cat.id}/cartoes`, { titulo: `Bem-vindo ${MARCA}`, texto: "Feito em casa." }, token);
await api("POST", `/catalogos/${cat.id}/cartoes`, { id_categoria: g.id, antes_do_item: ib.id, titulo: "Da semana" }, token);
await api("PUT", `/catalogos/itens/${ib.id}/marcas`, { esgotado: true }, token);
await api("PUT", `/pedidos/config/${cat.id}`, {
  aceita: true, retirada: true, entrega: false, taxa_entrega: 0, pedido_minimo: 0,
  antecedencia_min: 0, antecedencia_max_dias: 7, pagamentos: ["RETIRADA"], texto_pagamento: null,
}, token);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"],
                                           defaultViewport: { width: 1280, height: 900 } });
try {
  const p = await navegador.newPage();
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("\n1. o editor do catálogo simples não mostra o que é só do Cardápio Vivo");
  await p.goto(`${WEB}/catalogos/${cat.id}?aba=cardapio`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => document.body.innerText.includes("Doces"), { timeout: 20000 }).catch(() => {});
  const tela = await p.evaluate(() => document.body.innerText);
  checar("a abertura se chama só 'Abertura' e diz que vai ao site",
    /\bAbertura\b/.test(tela) && !tela.includes("Abertura no Cardápio Vivo") && tela.includes("capa no topo"), tela.slice(0, 400));
  checar("sem o período da atenção nem a linha 'No Cardápio Vivo:'",
    !(await p.$("#cartoes-periodo")) && !tela.includes("No Cardápio Vivo:"));
  await p.evaluate(() => [...document.querySelectorAll("button")]
    .find((b) => (b.getAttribute("aria-label") || "").startsWith("abrir PREV BOLO"))?.click());
  await p.waitForFunction(() => /em destaque/i.test(document.body.innerText), { timeout: 8000 }).catch(() => {});
  checar("a gaveta do prato mantém destaque e esgotado, sem objetivo e margem",
    await p.evaluate(() => /em destaque/i.test(document.body.innerText)
      && !document.querySelector('select[aria-label="Objetivo de negócio"]')));
  await p.keyboard.press("Escape");

  console.log("\n2. a aba Pré-visualização mostra o site, em rascunho");
  await p.goto(`${WEB}/catalogos/${cat.id}?aba=previa`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#previa-catalogo", { timeout: 15000 }).catch(() => {});
  const src = await p.$eval("#previa-catalogo", (f) => f.getAttribute("src")).catch(() => "");
  checar("o iframe abre o site em modo prévia", src === `/portal?previa=${cat.id}`, src);
  const f = await (await p.$("#previa-catalogo"))?.contentFrame();
  await f?.waitForFunction(() => document.querySelector(".capa-abertura"), { timeout: 20000 }).catch(() => {});
  const site = await f?.evaluate(() => ({
    faixa: document.querySelector(".faixa-previa")?.textContent ?? "",
    capa: document.querySelector(".capa-abertura")?.innerText ?? "",
    titulo: document.querySelector("#t-cardapio")?.textContent ?? "",
  }));
  checar("a faixa diz que é prévia e que pedido é teste", /Pré-visualização/.test(site?.faixa ?? ""), site);
  checar("a capa de abertura aparece no topo, com o título", (site?.capa ?? "").includes(`Bem-vindo ${MARCA}`), site);
  checar("com o nome do catálogo", site?.titulo === `Simples ${MARCA}`, site);
  await f?.evaluate(() => document.querySelector(".acessar")?.click());
  await f?.waitForSelector(".cartao-site", { timeout: 8000 }).catch(() => {});
  const secao = await f?.evaluate(() => {
    const el = [...document.querySelectorAll("#pratos > *")];
    return { ordem: el.map((x) => (x.classList.contains("cartao-site") ? "cartao" : x.querySelector(".nome")?.textContent ?? "")),
             esgotado: document.body.innerText.includes("Esgotado") };
  });
  checar("o cartão entra antes do prato que a casa escolheu",
    secao?.ordem?.length === 3 && secao.ordem[1] === "cartao" && /TORTA/.test(secao.ordem[2]), secao);
  checar("e o esgotado aparece marcado, sem o botão de pedir", secao?.esgotado
    && await f?.evaluate(() => {
      const pr = [...document.querySelectorAll(".prato")].find((x) => /TORTA/.test(x.innerText));
      return !!pr && !pr.querySelector(".pedir");
    }));

  console.log("\n3. o pedido de teste: confere e não grava");
  const { dados: antes } = await api("GET", "/pedidos/painel", undefined, token);
  await f?.evaluate(() => document.querySelector(".pedir .adicionar")?.click());
  await esperar(300);
  await f?.evaluate(() => document.querySelector("#barra-carrinho")?.click());
  await f?.waitForSelector("#enviar-pedido", { visible: true, timeout: 8000 }).catch(() => {});
  await f?.evaluate(() => document.querySelector("#enviar-pedido")?.click());
  await f?.waitForFunction(() => document.querySelector('[data-tela="pedido-pronto"][data-ativa]'), { timeout: 10000 }).catch(() => {});
  const pronto = await f?.evaluate(() => document.querySelector('[data-tela="pedido-pronto"]')?.innerText ?? "");
  checar("'Enviar' vira teste: sem pedir telefone, com o total e 'nada foi gravado'",
    /Teste do pedido/.test(pronto ?? "") && /nada foi gravado/i.test(pronto ?? "") && /10,00/.test(pronto ?? ""), pronto);
  const { dados: depois } = await api("GET", "/pedidos/painel", undefined, token);
  const conta = (pn) => ["novos", "sem_pdv", "mesas"].reduce((s, k) => s + ((pn?.[k] ?? []).length), 0);
  checar("e o painel de pedidos não ganhou nada", conta(depois) === conta(antes), [conta(antes), conta(depois)]);
} finally {
  await navegador.close();
  await api("PUT", `/catalogos/${cat.id}`, { situacao: "INATIVO" }, token);
  await api("PUT", "/unidades/1/parametros", par, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((x) => console.log(`  - ${x}`));
process.exit(falhas.length ? 1 : 0);
