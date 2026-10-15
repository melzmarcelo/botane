/**
 * Cardápio Vivo, fase 3 (migração 116), no navegador: a sessão que cai no braço B de um teste
 * de ORDEM vê a ordem sugerida no feed; a tela Testes A/B mostra o teste e aplica a variante;
 * e o painel Atenção × Vendas sugere destaque e aplica o que o gerente aprova.
 *
 * 🔑 Decisões do dono (15/10/2026) — ver `docs/cardapio-vivo-estudo.md`, seção 9.
 * O braço de uma sessão é descoberto pela própria API (feed com `?sessao=`), nunca recalculado
 * aqui: a conta é do banco.
 *
 *    node scripts/verificar-cardapio-testes.mjs     (API na 9200 e web na 3100 de pé)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
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
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), "X-Unidade": "1" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const texto = await r.text();
  return { status: r.status, dados: texto ? JSON.parse(texto) : null };
}

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;
const { dados: par } = await api("GET", "/unidades/1/parametros", undefined, token);
await api("PUT", "/unidades/1/parametros", { ...par, reservas_ligado: true }, token);
const { dados: antes } = await api("GET", "/cardapio-vivo/config", undefined, token);

async function produto(nome, preco) {
  const { dados: p } = await api("POST", "/produtos", { nome: `${nome} ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", controla_estoque: false }, token);
  const { dados: atual } = await api("GET", `/produtos/${p.id}`, undefined, token);
  await api("PUT", `/produtos/${p.id}`, { ...atual, integrado_pdv: true, preco_venda: preco }, token);
  return p.id;
}

console.log("0. cenário: três pratos, o terceiro em destaque, e um teste de ordem aberto");
const { dados: cat } = await api("POST", "/catalogos", { nome: `AB tela ${MARCA}`, origem: "PRODUTOS", situacao: "ATIVO" }, token);
const { dados: g } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Pratos" }, token);
const itens = [];
for (const [n, v] of [["ABT PRIMEIRO", 10], ["ABT SEGUNDO", 11], ["ABT TERCEIRO", 12]]) {
  const { dados: it } = await api("POST", `/catalogos/categorias/${g.id}/itens`, { id_produto: await produto(n, v) }, token);
  itens.push(it.id);
}
await api("PUT", "/cardapio-vivo/config", { ...antes.config, id_catalogo: cat.id, modo: "VITRINE" }, token);
await api("PUT", `/catalogos/itens/${itens[2]}/marcas`, { destaque: true }, token);
const { status: stT, dados: teste } = await api("POST", "/cardapio-vivo/testes", { tipo: "ORDEM" }, token);
checar("o teste de ordem começa pela API", stT === 201, teste);

// Uma sessão de cada braço, descoberta pelo feed (a conta é do banco).
const sessoes = {};
for (let i = 0; i < 60 && Object.keys(sessoes).length < 2; i++) {
  const s = crypto.randomUUID();
  const { dados: f } = await api("GET", `/publico/cardapio/loja/1?sessao=${s}`);
  sessoes[f.itens[0].id === itens[2] ? "B" : "A"] ??= s;
}
checar("há sessões dos dois braços", sessoes.A && sessoes.B, sessoes);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  console.log("\n1. o feed respeita o braço da sessão do aparelho");
  for (const braco of ["A", "B"]) {
    const p = await navegador.newPage();
    await p.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
    await p.evaluateOnNewDocument((s) => {
      localStorage.setItem("cardapio.sessao", JSON.stringify({ id: s, ultimo: Date.now() }));
      localStorage.setItem("cardapio.aviso_cookies", "1");
    }, sessoes[braco]);
    await p.goto(`${WEB}/c/1`, { waitUntil: "networkidle2" });
    await p.waitForSelector(".cv-item", { timeout: 20000 });
    const primeiro = await p.$eval(".cv-item h2", (h) => h.textContent);
    checar(`braço ${braco}: o primeiro prato é ${braco === "A" ? "o da ordem do catálogo" : "o destaque (ordem sugerida)"}`,
           primeiro.startsWith(braco === "A" ? "ABT PRIMEIRO" : "ABT TERCEIRO"), primeiro);
    await p.close();
  }

  console.log("\n2. a tela Testes A/B");
  const e = await navegador.newPage();
  await e.setViewport({ width: 1366, height: 1000 });
  await e.goto(WEB + "/login");
  await e.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  await e.goto(WEB + "/cardapio-vivo/testes", { waitUntil: "networkidle2" });
  await e.waitForFunction(() => document.body.innerText.includes("Ordem atual × ordem sugerida"), { timeout: 15000 }).catch(() => {});
  const tela = await e.evaluate(() => document.body.innerText);
  checar("o teste aparece aberto, com os dois braços", tela.includes("Ordem atual × ordem sugerida") && tela.includes("Aberto desde")
         && tela.includes("Ordem sugerida"), tela.slice(0, 400));
  checar("e diz que a amostra ainda é pequena", tela.includes("Amostra pequena"), tela.slice(0, 600));
  await e.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Aplicar B").click());
  await e.waitForFunction(() => document.body.innerText.includes("aplicado"), { timeout: 10000 }).catch(() => {});
  checar("aplicar B marca o teste como aplicado", (await e.evaluate(() => document.body.innerText)).includes("aplicado"));
  const { dados: f } = await api("GET", "/publico/cardapio/loja/1");
  checar("e a ordem sugerida passa a valer para todos", f.itens[0].id === itens[2], f.itens.map((i) => i.nome));

  console.log("\n3. sugestões de destaque no painel");
  await api("PUT", `/catalogos/itens/${itens[1]}/marcas`, { objetivo: "LANCAMENTO" }, token);
  await e.goto(WEB + "/cardapio-vivo/atencao", { waitUntil: "networkidle2" });
  await e.waitForFunction(() => document.body.innerText.includes("Sugestões de destaque"), { timeout: 20000 }).catch(() => {});
  const at = await e.evaluate(() => document.body.innerText);
  checar("o painel sugere pôr o lançamento em destaque", at.includes("ABT SEGUNDO") && at.includes("pôr em destaque"), at.slice(0, 500));
  await e.evaluate(() => document.querySelector('input[aria-label^="Aprovar ABT SEGUNDO"]').click());
  await e.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.startsWith("Aplicar 1")).click());
  await esperar(1500);
  const { dados: f2 } = await api("GET", "/publico/cardapio/loja/1");
  checar("aprovado, o prato entra em destaque no feed", f2.itens.find((i) => i.id === itens[1])?.destaque === true,
         f2.itens.map((i) => [i.nome, i.destaque]));
} finally {
  await navegador.close();
  await api("PUT", "/cardapio-vivo/config", antes.config, token);
  await api("PUT", `/catalogos/${cat.id}`, { situacao: "INATIVO" }, token);
  await api("PUT", "/unidades/1/parametros", par, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
