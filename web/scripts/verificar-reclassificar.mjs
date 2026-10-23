/**
 * Produtos ▸ Reclassificar por planilha, no navegador; e a categoria sem tipo.
 *
 * 🔑 Pedido do dono (23/10/2026), a reestruturação de tipos, categorias, setores e
 * locais. A regra é coberta por `api/tests/smoke_reclassificacao.py`; aqui se confere
 * que a tela manda a planilha, mostra a prévia sem gravar, aplica, e que a categoria
 * pode nascer sem tipo.
 *
 *    node scripts/verificar-reclassificar.mjs   (API na 9200 e web na 3100 de pé;
 *                                                BOTANE_API e BOTANE_WEB mudam as portas)
 */
import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const API = process.env.BOTANE_API ?? "http://127.0.0.1:9200";
const WEB = process.env.BOTANE_WEB ?? "http://127.0.0.1:3100";
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
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), "X-Unidade": "1" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const t = await r.text();
  return { status: r.status, dados: t ? JSON.parse(t) : null };
}

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;

console.log("0. cenário: uma categoria sem tipo e um produto para mudar de lugar");
const { dados: cat } = await api("POST", "/categorias", { nome: `HORTIFRUTI TELA ${MARCA}` }, token);
const { dados: prod } = await api("POST", "/produtos", {
  nome: `CEBOLA TELA ${MARCA}`, tipo: "PRODUZIDO", um_estoque: "UN", status: "ATIVO",
}, token);
const { dados: antes } = await api("GET", `/produtos/${prod.id}`, undefined, token);
// ⚠️ Num arquivo de verdade, no D: (o projeto não usa a pasta temporária do C:).
const pasta = path.resolve("scripts/_fotos");
fs.mkdirSync(pasta, { recursive: true });
const arquivo = path.join(pasta, `reclassificar-${MARCA}.csv`);
fs.writeFileSync(arquivo, `\ufeffCódigo;Tipo;Categoria\r\n${antes.codigo};Insumo;hortifruti tela ${MARCA}\r\n`);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1000 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. a lista de produtos leva à reclassificação");
  await p.goto(`${WEB}/produtos`, { waitUntil: "networkidle2" });
  const temLink = await p.waitForSelector('a[href="/produtos/reclassificar"]', { timeout: 30000 })
    .then(() => true).catch(() => false);
  checar("o botão Reclassificar por planilha aparece", temLink);

  console.log("\n2. prévia e aplicação");
  await p.goto(`${WEB}/produtos/reclassificar`, { waitUntil: "networkidle2" });
  const entrada = await p.waitForSelector("#planilha-reclassificar", { timeout: 30000 });
  await entrada.uploadFile(arquivo);
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Ver prévia").click());
  await p.waitForSelector("#reclassificar-mudam", { timeout: 20000 }).catch(() => {});
  const previa = await p.evaluate(() => document.querySelector("#reclassificar-mudam")?.innerText ?? "");
  checar("a prévia mostra o de-para do produto", previa.includes(`CEBOLA TELA`) && /INSUMO/.test(previa), previa.slice(0, 300));
  const { dados: depoisPrevia } = await api("GET", `/produtos/${prod.id}`, undefined, token);
  checar("e não grava", depoisPrevia.tipo === "PRODUZIDO", depoisPrevia.tipo);
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => /^Aplicar em/.test(b.textContent.trim())).click());
  await p.waitForFunction(() => /Aplicado/.test(document.body.innerText), { timeout: 20000 }).catch(() => {});
  const { dados: depois } = await api("GET", `/produtos/${prod.id}`, undefined, token);
  checar("aplicar grava tipo e categoria", depois.tipo === "INSUMO" && depois.id_categoria === cat.id,
    { tipo: depois.tipo, cat: depois.id_categoria });

  console.log("\n3. categoria sem tipo nas Tabelas de apoio");
  await p.goto(`${WEB}/cadastros?aba=categorias`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#form-apoio select", { timeout: 30000 }).catch(() => {});
  const opcoes = await p.evaluate(() => [...document.querySelectorAll("#form-apoio select")].at(-1)
    ?.options ? [...[...document.querySelectorAll("#form-apoio select")].at(-1).options].map((o) => o.textContent) : []);
  checar("o tipo da categoria oferece “qualquer tipo”", opcoes.some((o) => /qualquer tipo/.test(o)), opcoes);
  if (process.env.FOTO) await p.screenshot({ path: process.env.FOTO, fullPage: true });
} finally {
  await navegador.close();
  fs.rmSync(arquivo, { force: true });
  await api("DELETE", `/produtos/${prod.id}`, undefined, token);
  await api("PUT", `/produtos/${prod.id}`, { id_categoria: null }, token);
  await api("DELETE", `/categorias/${cat.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
