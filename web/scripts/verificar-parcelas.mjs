/**
 * Inventário ▸ contagem em PARCELAS ("3 UN + 948 ML"), no navegador.
 *
 * 🔑 Pedido do dono (27/10/2026), no teste do CAMPARI: as garrafas fechadas em UN e a
 * aberta em ML, somadas pelo sistema. As contas são de
 * `api/tests/smoke_contagem_parcelas.py`; aqui se confere o cartão: o "+ somar outra
 * unidade", a linha nova, o total convertido e o que volta depois de recarregar.
 *
 *    node scripts/verificar-parcelas.mjs   (API na 9200 e web na 3100 de pé)
 */
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
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

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

console.log("0. cenário: destilado em UN com ML (garrafa de 1 L), contagem aberta");
const { dados: locais } = await api("GET", "/locais", undefined, token);
const local = (locais ?? []).find((l) => l.principal) ?? locais[0];
const { dados: prod } = await api("POST", "/produtos", {
  nome: `GARRAFA PARCELA ${MARCA}`, tipo: "REVENDA", um_estoque: "UN", status: "ATIVO",
}, token);
await api("PUT", `/produtos/${prod.id}/unidades`, { itens: [{ um: "ML", fator: 0.001 }] }, token);
await api("POST", "/estoque/entradas", {
  id_produto: prod.id, quantidade: 4, custo_unitario: 50, id_local: local.id, documento: `NF-PC-${MARCA}`,
}, token);
const { status: stInv, dados: inv } = await api("POST", "/inventarios",
  { locais: [local.id], produtos: [prod.id], cega: false }, token);
checar("a contagem abre", stInv === 201, inv);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 420, height: 900 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  await p.goto(`${WEB}/inventario/${inv.id}`, { waitUntil: "networkidle2" });
  await p.waitForSelector("input[data-parcela='0']", { timeout: 30000 }).catch(() => {});
  await esperar(800);

  console.log("1. a primeira parcela e o somar");
  checar("há o '+ somar outra unidade'", !!(await p.$("[data-somar-parcela]")));
  await p.type("input[data-parcela='0']", "3");
  await p.click("[data-somar-parcela]");
  await p.waitForSelector("input[data-parcela='1']", { timeout: 10000 }).catch(() => {});
  await esperar(1500);
  const segunda = await p.evaluate(() => ({
    existe: !!document.querySelector("input[data-parcela='1']"),
    um: document.querySelector("select[data-parcela-um='1']")?.value,
  }));
  checar("a segunda linha aparece, já em ML", segunda.existe && segunda.um === "ML", segunda);

  console.log("\n2. 948 ML na garrafa aberta");
  await p.type("input[data-parcela='1']", "948");
  await p.evaluate(() => document.querySelector("input[data-parcela='1']")?.blur());
  await esperar(2000);
  const tela = await p.evaluate(() => document.querySelector("li")?.innerText ?? "");
  checar("o cartão mostra o total: = 3,948 UN", /=\s*3,948\s*UN/.test(tela), tela.slice(0, 300));
  const { dados: depois } = await api("GET", `/inventarios/${inv.id}`, undefined, token);
  const item = depois.itens.find((i) => i.id_produto === prod.id);
  checar("o servidor gravou 3,948 com as duas parcelas",
    Math.abs(Number(item.qtd_contada) - 3.948) < 0.0001 && item.parcelas?.length === 2, item);

  console.log("\n3. recarregar traz as parcelas de volta");
  await p.reload({ waitUntil: "networkidle2" });
  await p.waitForSelector("input[data-parcela='1']", { timeout: 30000 }).catch(() => {});
  await esperar(800);
  const volta = await p.evaluate(() => ({
    a: document.querySelector("input[data-parcela='0']")?.value,
    ua: document.querySelector("select[data-parcela-um='0']")?.value,
    b: document.querySelector("input[data-parcela='1']")?.value,
    ub: document.querySelector("select[data-parcela-um='1']")?.value,
  }));
  checar("3 UN + 948 ML, como digitado", volta.a === "3" && volta.ua === "UN" && volta.b === "948" && volta.ub === "ML", volta);

  if (process.env.FOTO) await p.screenshot({ path: process.env.FOTO, fullPage: true });

  console.log("\n4. tirar a parcela");
  await p.click("button[aria-label='tirar a parcela 2']");
  await esperar(2000);
  const { dados: tirado } = await api("GET", `/inventarios/${inv.id}`, undefined, token);
  const it2 = tirado.itens.find((i) => i.id_produto === prod.id);
  checar("volta a ser 3 UN, sem parcelas", Math.abs(Number(it2.qtd_contada) - 3) < 0.0001 && !it2.parcelas, it2);
} finally {
  await navegador.close();
  await api("DELETE", `/inventarios/${inv.id}`, undefined, token);
  await api("DELETE", `/produtos/${prod.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
