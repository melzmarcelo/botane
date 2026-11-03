/**
 * O documento com motivo Prêmio e o resgate da fidelidade, no navegador (migração 147).
 *
 * 🔑 Pedido do dono (03/11/2026): *"vincular o documento com o resgate de prêmios"*, com o
 * código obrigatório. As regras são de `api/tests/smoke_premio_no_documento.py`; aqui se
 * confere a tela: o filtro "Sem documento", o botão que abre o lançamento já preenchido, o
 * campo do código só no motivo Prêmio, o documento e o custo no grid, o custo no Painel e o
 * prêmio no detalhe da venda.
 *
 *    node scripts/verificar-premio-documento.mjs   (API na 9200 e web na 3100 de pé)
 */
import { execFileSync } from "node:child_process";
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const API = process.env.BOTANE_API ?? "http://127.0.0.1:9200";
const WEB = process.env.BOTANE_WEB ?? "http://127.0.0.1:3100";
const PYTHON = process.env.PYTHON ?? "python";
const MARCA = String(Date.now()).slice(-6);
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
const cenario = (acao) => execFileSync(PYTHON, ["tests/cenario_premio.py", acao, "1"],
  { cwd: "../api", encoding: "utf8", env: { ...process.env, PYTHONUTF8: "1" } });

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
const hoje = new Date().toLocaleDateString("sv-SE");

console.log("0. cenário: um prêmio entregue no balcão, sem documento, e um prato a R$ 12,00");
const { codigo } = JSON.parse(cenario("montar").trim().split(/\r?\n/).pop());
const { dados: locais } = await api("GET", "/locais", undefined, token);
const local = (locais ?? []).find((l) => l.ativo !== false);
const { dados: prod } = await api("POST", "/produtos", {
  nome: `PREMIO TELA ${MARCA}`, tipo: "REVENDA", um_estoque: "UN", preco_venda: 30, status: "ATIVO",
}, token);
await api("PUT", `/produtos/${prod.id}`, { id_local_padrao: local.id }, token);
await api("POST", "/estoque/entradas", {
  id_produto: prod.id, quantidade: 5, custo_unitario: 12, id_local: local.id, documento: `NF-PT-${MARCA}`,
}, token);
checar("o cenário tem um código", /^[A-Z]{6}$/.test(codigo ?? ""), codigo);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
let idVenda = null;
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1000 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. Prêmios ▸ Sem documento");
  await p.goto(`${WEB}/fidelidade/premios?status=SEM_DOCUMENTO&busca=${codigo}`, { waitUntil: "networkidle2" });
  await p.waitForSelector(`[data-lancar-documento="${codigo}"]`, { timeout: 30000 }).catch(() => {});
  const grid = await p.evaluate((c) => ({
    aba: [...document.querySelectorAll('[role="tab"]')].find((b) => b.getAttribute("aria-selected") === "true")?.innerText,
    linha: [...document.querySelectorAll("tbody tr")].find((tr) => tr.innerText.includes(c))?.innerText ?? "",
    botao: document.querySelector(`[data-lancar-documento="${c}"]`)?.getAttribute("href") ?? "",
  }), codigo);
  checar("a aba 'Sem documento' mostra o prêmio entregue com a etiqueta",
    grid.aba === "Sem documento" && /sem documento/.test(grid.linha), grid);
  checar("e o botão 'Lançar documento' aponta para o lançamento com motivo e código",
    grid.botao === `/vendas/lancar?motivo=PREMIO&premio=${codigo}`, grid);

  console.log("\n2. Vendas ▸ Lançar, vindo do botão");
  await p.$eval(`[data-lancar-documento="${codigo}"]`, (a) => a.click());
  await p.waitForSelector("#venda-codigo-premio", { timeout: 30000 }).catch(() => {});
  await esperar(800);
  const form = await p.evaluate(() => ({
    motivo: document.querySelector("#venda-motivo-campo")?.value,
    codigo: document.querySelector("#venda-codigo-premio")?.value,
    obrigatorio: document.querySelector("#venda-codigo-premio")?.required,
    aviso: document.querySelector("#motivo-do-documento")?.parentElement?.innerText ?? "",
  }));
  checar("chega com o motivo Prêmio e o código preenchidos, e o código é obrigatório",
    form.motivo === "PREMIO" && form.codigo === codigo && form.obrigatorio === true, form);
  checar("o aviso explica que o prêmio fica ligado ao documento",
    /fica ligado a este documento/.test(form.aviso), form.aviso.slice(-300));
  await p.select("#venda-motivo-campo", "BRINDE");
  await esperar(300);
  checar("com outro motivo, o campo do código some",
    !(await p.$("#venda-codigo-premio")));

  console.log("\n3. o documento lançado aparece nos dois lados");
  const r = await api("POST", "/vendas/importar", { vendas: [{
    data: hoje, documento: `PT-${MARCA}`, origem: "MANUAL", motivo: "PREMIO", codigo_premio: codigo,
    itens: [{ id_produto: prod.id, quantidade: 1, valor_unitario: 30 }] }] }, token);
  checar("o documento entra ligado ao prêmio", r.status === 201 && /ligado ao documento/.test(r.dados?.message ?? ""), r.dados);
  await p.goto(`${WEB}/fidelidade/premios?status=USADO&busca=${codigo}`, { waitUntil: "networkidle2" });
  await p.waitForSelector(`[data-premio-documento="${codigo}"]`, { timeout: 30000 }).catch(() => {});
  const doc = await p.evaluate((c) => ({
    texto: document.querySelector(`[data-premio-documento="${c}"]`)?.innerText ?? "",
    href: document.querySelector(`[data-premio-documento="${c}"]`)?.getAttribute("href") ?? "",
    botao: !!document.querySelector(`[data-lancar-documento="${c}"]`),
  }), codigo);
  checar("o grid mostra o documento e o custo, sem o botão de lançar",
    doc.texto.includes(`PT-${MARCA}`) && /12,00/.test(doc.texto) && !doc.botao, doc);
  idVenda = Number((doc.href.match(/\/vendas\/(\d+)/) ?? [])[1]) || null;

  await p.goto(`${WEB}/fidelidade/painel`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#fidelidade-custo", { timeout: 30000 }).catch(() => {});
  const custo = await p.evaluate(() => document.querySelector("#fidelidade-custo")?.innerText ?? "");
  checar("o Painel diz o custo dos prêmios no mês", /Custo dos prêmios no mês: R\$/.test(custo), custo);

  if (idVenda) {
    await p.goto(`${WEB}/vendas/${idVenda}`, { waitUntil: "networkidle2" });
    await p.waitForSelector("#venda-premio", { timeout: 30000 }).catch(() => {});
    const det = await p.evaluate(() => document.querySelector("#venda-premio")?.innerText ?? "");
    checar("o detalhe da venda mostra o prêmio, de quem e que foi entregue no balcão",
      det.includes(codigo) && /Cliente Prêmio Tela/.test(det) && /balcão/.test(det), det);
  } else {
    checar("o link do documento leva à venda", false, doc.href);
  }
  if (process.env.FOTO) await p.screenshot({ path: process.env.FOTO, fullPage: true });
} finally {
  await navegador.close();
  if (idVenda) await api("DELETE", `/vendas/${idVenda}`, undefined, token);
  cenario("limpar");
  await api("DELETE", `/produtos/${prod.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
