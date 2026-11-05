/**
 * Tirar vários pratos do cardápio de uma vez (pedido do dono, 05/11/2026).
 *
 * 🔑 *"para tirar do catálogo, poderia ter esta opção também, check box para seleção e botão
 * para retirar, não sendo necessário entrar no item"*. Confere: a caixa em cada linha não abre a
 * gaveta, "Marcar todos", a confirmação lista os marcados, só eles saem, e trocar de seção limpa.
 * O cenário é montado pela API e sai no fim (o catálogo é inativado).
 *
 *    node scripts/verificar-tirar-varios.mjs     (API na 9200 e o Next na 3100 de pé)
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
    headers: { "Content-Type": "application/json", "X-Unidade": "1", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const texto = await r.text();
  return { status: r.status, dados: texto ? JSON.parse(texto) : null };
}

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;

async function produto(nome) {
  const { dados: p } = await api("POST", "/produtos", { nome: `${nome} ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", controla_estoque: false }, token);
  // ⚠️ O cardápio só aceita o que é vendido no PDV.
  const { dados: atual } = await api("GET", `/produtos/${p.id}`, undefined, token);
  await api("PUT", `/produtos/${p.id}`, { ...atual, integrado_pdv: true, preco_venda: 10 }, token);
  return p.id;
}

console.log("0. cenário: um catálogo com 4 pratos em Doces e 1 em Salgados");
const { dados: cat } = await api("POST", "/catalogos", { nome: `Tirar ${MARCA}`, origem: "PRODUTOS" }, token);
const { dados: doces } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Doces" }, token);
const { dados: salg } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Salgados" }, token);
for (const n of ["TV BOLO", "TV TORTA", "TV PUDIM", "TV MOUSSE"])
  await api("POST", `/catalogos/categorias/${doces.id}/itens`, { id_produto: await produto(n) }, token);
await api("POST", `/catalogos/categorias/${salg.id}/itens`, { id_produto: await produto("TV COXINHA") }, token);
const pratosEm = async (nome) => {
  const { dados } = await api("GET", `/catalogos/${cat.id}/conteudo`, undefined, token);
  return (dados.categorias.find((c) => c.nome === nome)?.itens ?? []).map((i) => i.produto.replace(` ${MARCA}`, ""));
};

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"],
                                           defaultViewport: { width: 1280, height: 900 } });
try {
  const p = await navegador.newPage();
  const erros = [];
  p.on("pageerror", (e) => erros.push(e.message));
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  await p.goto(`${WEB}/catalogos/${cat.id}?aba=cardapio`, { waitUntil: "networkidle2" });
  await p.waitForSelector("[data-marcar-prato]", { timeout: 30000 }).catch(() => {});

  console.log("1. marcar");
  const caixa = (nome) => p.evaluate((n) => {
    const c = [...document.querySelectorAll("[data-marcar-prato]")].find((x) => x.getAttribute("aria-label").startsWith(`marcar ${n}`));
    c?.click();
    return !!c;
  }, nome);
  checar("cada prato tem uma caixa de marcar", await p.$$eval("[data-marcar-prato]", (x) => x.length) === 4);
  checar("sem marcar, não há botão de tirar", !(await p.$("#tirar-marcados")));
  await caixa("TV BOLO");
  await caixa("TV PUDIM");
  await esperar(300);
  checar("marcar não abre a gaveta do prato", !(await p.evaluate(() => document.body.innerText.includes("Tirar deste cardápio"))));
  checar("a barra conta os marcados e mostra 'Tirar do cardápio'",
    await p.evaluate(() => /2 marcados/.test(document.querySelector("#marcar-pratos")?.innerText ?? "")) && !!(await p.$("#tirar-marcados")));
  const alvo = await p.$eval("#marcar-pratos label", (l) => l.getBoundingClientRect().height);
  checar("o alvo de 'Marcar todos' tem pelo menos 44px", alvo >= 44, alvo);

  console.log("\n2. confirmar e tirar");
  await p.$eval("#tirar-marcados", (b) => b.click());
  await esperar(300);
  const janela = await p.evaluate(() => document.querySelector('[role="dialog"]')?.innerText ?? "");
  checar("a confirmação diz quantos e lista os dois", /Tirar 2 pratos/.test(janela) && /TV BOLO/.test(janela) && /TV PUDIM/.test(janela) && !/TV TORTA/.test(janela), janela);
  await p.evaluate(() => [...document.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent === "Tirar do cardápio")?.click());
  await p.waitForFunction(() => document.querySelectorAll("[data-marcar-prato]").length === 2, { timeout: 15000 }).catch(() => {});
  const ficaram = await pratosEm("Doces");
  checar("só os marcados saíram (no servidor)", ficaram.length === 2 && ficaram.includes("TV TORTA") && ficaram.includes("TV MOUSSE"), ficaram);
  checar("a tela mostra os dois que ficaram e limpa as marcas",
    await p.$$eval("[data-marcar-prato]", (x) => x.length === 2 && x.every((c) => !c.checked)) && !(await p.$("#tirar-marcados")));
  checar("o produto continua cadastrado",
    (await api("GET", `/produtos?busca=${encodeURIComponent(`TV BOLO ${MARCA}`)}`, undefined, token)).status === 200);

  console.log("\n3. marcar todos e trocar de seção");
  await p.evaluate(() => document.querySelector('[aria-label="marcar todos os pratos desta seção"]')?.click());
  await esperar(200);
  checar("'Marcar todos' marca os da seção", await p.$$eval("[data-marcar-prato]", (x) => x.every((c) => c.checked)));
  await p.evaluate(() => [...document.querySelectorAll('nav[aria-label="seções do cardápio"] button')].find((b) => b.textContent.includes("Salgados"))?.click());
  await esperar(400);
  checar("trocar de seção limpa as marcas", !(await p.$("#tirar-marcados"))
    && await p.$$eval("[data-marcar-prato]", (x) => x.length === 1 && !x[0].checked));
  checar("nenhum erro de JavaScript", !erros.length, erros);
} finally {
  await navegador.close();
  await api("PUT", `/catalogos/${cat.id}`, { situacao: "INATIVO" }, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((x) => console.log(`  - ${x}`));
process.exit(falhas.length ? 1 : 0);
