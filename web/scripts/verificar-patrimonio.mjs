/**
 * Patrimônio no navegador: a lista com o resumo por setor, a ficha, a manutenção, o
 * cadastro novo, o QR e a importação por planilha.
 *
 * 🔑 Pedido do dono (27/10/2026): *"um processo para inventariar o patrimônio"* — etapas 1
 * e 2 (cadastro com plaqueta e importação; manutenção com plano e alertas). Confere:
 *   1. a lista mostra o quadro por setor e filtra pela URL (o link do alerta);
 *   2. a ficha diz "Vencida", e registrar a preventiva de hoje a põe "Em dia";
 *   3. "Novo bem" cadastra e abre a ficha do bem criado;
 *   4. o endereço do QR (/patrimonio/b/PAT-…) abre a ficha;
 *   5. a importação mostra a prévia e só grava no segundo clique;
 *   6. o produto Patrimônio que entra aparece em "falta cadastrar"; o "Cadastrar bem" chega
 *      com o produto e a última entrada; o cadastro do produto lista o bem.
 * O que o roteiro cria é apagado no fim.
 *
 *    node scripts/verificar-patrimonio.mjs   (API na 9200 e web na 3100 de pé)
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const API = process.env.BOTANE_API ?? "http://127.0.0.1:9200";
const WEB = process.env.BOTANE_WEB ?? "http://127.0.0.1:3100";
const MARCA = String(Date.now()).slice(-6);
const AQUI = path.dirname(fileURLToPath(import.meta.url));
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
const hoje = new Date().toLocaleDateString("sv-SE");
const seteMeses = new Date(Date.now() - 215 * 86400000).toLocaleDateString("sv-SE");

console.log("0. cenário: um bem crítico com a preventiva vencida");
const { dados: setor } = await api("POST", "/setores", { nome: `SETOR PATWEB ${MARCA}` }, token);
const { status: st0, dados: bem } = await api("POST", "/patrimonio", {
  descricao: `Forno web ${MARCA}`, marca: `Marca${MARCA}`, id_setor: setor.id, criticidade: "ALTA",
  preventiva_meses: 6, ultima_preventiva: seteMeses,
}, token);
checar("o bem de teste nasce", st0 === 201, bem);
const csv = path.join(AQUI, `_patrimonio_${MARCA}.csv`);
const criados = [bem.id];
const produtos = [];

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1100 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. a lista");
  await p.goto(`${WEB}/patrimonio?preventiva=VENCIDA&busca=Marca${MARCA}`, { waitUntil: "networkidle2" });
  await p.waitForFunction((c) => document.querySelector("#patrimonio-lista")?.innerText.includes(c),
                          { timeout: 20000 }, bem.codigo).catch(() => {});
  const lista = await p.evaluate(() => ({
    linhas: [...document.querySelectorAll("#patrimonio-lista tbody tr")].map((tr) => tr.innerText),
    resumo: document.querySelector("#patrimonio-resumo")?.innerText ?? "",
    prev: document.querySelector("#patrimonio-preventiva")?.value,
  }));
  checar("o filtro da URL (o link do alerta) traz só o bem vencido",
    lista.linhas.length === 1 && lista.linhas[0].includes(bem.codigo) && lista.prev === "VENCIDA", lista);
  checar("e a linha diz Vencida", /Vencida/.test(lista.linhas[0] ?? ""), lista.linhas);
  checar("o quadro por setor mostra o setor do bem", lista.resumo.includes(`SETOR PATWEB ${MARCA}`), lista.resumo.slice(0, 300));

  console.log("\n2. a ficha e a manutenção");
  await p.goto(`${WEB}/patrimonio/${bem.id}`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#manutencao-registrar", { timeout: 20000 }).catch(() => {});
  const cab = await p.evaluate(() => document.querySelector("main header")?.innerText ?? "");
  checar("o cabeçalho traz o código e 'Vencida'", cab.includes(bem.codigo) && /Vencida/.test(cab), cab);
  await p.select("#manutencao-tipo", "PREVENTIVA");
  await p.$eval("#manutencao-descricao", (e) => { e.value = ""; });
  await p.type("#manutencao-descricao", "limpeza e calibração");
  await p.click("#manutencao-registrar");
  await p.waitForFunction(() => /Em dia/.test(document.querySelector("main header")?.innerText ?? ""),
                          { timeout: 15000 }).catch(() => {});
  const depois = await p.evaluate(() => ({
    cab: document.querySelector("main header")?.innerText ?? "",
    hist: document.querySelector("#manutencao-lista")?.innerText ?? "",
  }));
  checar("registrar a preventiva de hoje põe 'Em dia'", /Em dia/.test(depois.cab), depois.cab);
  checar("e o histórico mostra o registro", depois.hist.includes("limpeza e calibração"), depois.hist);

  console.log("\n3. novo bem");
  await p.goto(`${WEB}/patrimonio/novo`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#bem-descricao", { timeout: 20000 });
  await p.type("#bem-descricao", `Batedeira web ${MARCA}`);
  await p.type("#bem-apelido", `W${MARCA}`);
  await p.click("#bem-salvar");
  await p.waitForFunction(() => /\/patrimonio\/\d+$/.test(location.pathname), { timeout: 15000 }).catch(() => {});
  const idNovo = Number((p.url().match(/\/patrimonio\/(\d+)$/) ?? [])[1]);
  if (idNovo) criados.push(idNovo);
  checar("cadastra e abre a ficha do bem criado", !!idNovo, p.url());
  await p.waitForFunction(() => /PAT-\d+/.test(document.querySelector("h1")?.innerText ?? ""), { timeout: 15000 }).catch(() => {});
  const titulo = await p.evaluate(() => document.querySelector("h1")?.innerText ?? "");
  checar("com o código da plaqueta no título", /PAT-\d+/.test(titulo) && titulo.includes(`Batedeira web ${MARCA}`), titulo);

  console.log("\n4. o QR");
  await p.goto(`${WEB}/patrimonio/b/${bem.codigo}`, { waitUntil: "networkidle2" });
  await p.waitForFunction((id) => location.pathname === `/patrimonio/${id}`, { timeout: 15000 }, bem.id).catch(() => {});
  checar("o endereço da plaqueta abre a ficha", p.url().endsWith(`/patrimonio/${bem.id}`), p.url());

  console.log("\n5. importar planilha");
  fs.writeFileSync(csv, `Código;Equipamento;Setor;Marca\nIMP-${MARCA};Liquidificador web ${MARCA};SETOR PATWEB ${MARCA};Walita\n`, "utf8");
  await p.goto(`${WEB}/patrimonio/importar`, { waitUntil: "networkidle2" });
  const entrada = await p.waitForSelector("#patrimonio-arquivo", { timeout: 20000 });
  await entrada.uploadFile(csv);
  await p.click("#patrimonio-previa");
  await p.waitForSelector("#patrimonio-novos", { timeout: 15000 }).catch(() => {});
  const previa = await p.evaluate(() => ({
    novos: document.querySelector("#patrimonio-novos")?.innerText ?? "",
    botao: !!document.querySelector("#patrimonio-aplicar"),
  }));
  const { dados: antes } = await api("GET", `/patrimonio?busca=Liquidificador web ${MARCA}`, undefined, token);
  checar("a prévia mostra o novo e não grava", previa.novos.includes(`Liquidificador web ${MARCA}`)
    && previa.botao && antes.length === 0, { previa, antes });
  await p.click("#patrimonio-aplicar");
  await p.waitForFunction(() => /Importado/.test(document.body.innerText), { timeout: 15000 }).catch(() => {});
  const { dados: depoisImp } = await api("GET", `/patrimonio?busca=Liquidificador web ${MARCA}`, undefined, token);
  checar("o segundo clique grava, com o código da casa como apelido",
    depoisImp.length === 1 && depoisImp[0].apelido === `IMP-${MARCA}` && depoisImp[0].marca === "Walita", depoisImp);
  for (const b of depoisImp) criados.push(b.id);

  console.log("\n6. o produto Patrimônio que entra vira bem");
  const { dados: prod } = await api("POST", "/produtos", {
    nome: `CAFETEIRA PATWEB ${MARCA}`, tipo: "PATRIMONIO", um_estoque: "UN", status: "ATIVO",
  }, token);
  produtos.push(prod.id);
  await api("POST", "/estoque/entradas", {
    id_produto: prod.id, quantidade: 2, custo_unitario: 900, documento: `NF-WEB-${MARCA}`,
  }, token);
  await p.goto(`${WEB}/patrimonio`, { waitUntil: "networkidle2" });
  await p.waitForFunction((n) => document.querySelector("#patrimonio-a-cadastrar")?.innerText.includes(n),
                          { timeout: 20000 }, `CAFETEIRA PATWEB ${MARCA}`).catch(() => {});
  const pendente = await p.evaluate((n) => [...document.querySelectorAll("#patrimonio-a-cadastrar tbody tr")]
    .map((tr) => tr.innerText).find((t) => t.includes(n)) ?? "", `CAFETEIRA PATWEB ${MARCA}`);
  checar("a lista mostra o que entrou e falta cadastrar (faltam 2)", /\b2\b/.test(pendente), pendente);
  await p.goto(`${WEB}/patrimonio/novo?produto=${prod.id}`, { waitUntil: "networkidle2" });
  await p.waitForFunction((n) => document.querySelector("#bem-descricao")?.value === n,
                          { timeout: 20000 }, `CAFETEIRA PATWEB ${MARCA}`).catch(() => {});
  const pre = await p.evaluate(() => ({
    descricao: document.querySelector("#bem-descricao")?.value,
    produto: document.querySelector("#bem-produto")?.value ?? document.querySelector("#bem-produto")?.textContent,
  }));
  checar("o Cadastrar bem chega com o produto e o nome dele", pre.descricao === `CAFETEIRA PATWEB ${MARCA}`, pre);
  await p.click("#bem-salvar");
  await p.waitForFunction(() => /\/patrimonio\/\d+$/.test(location.pathname), { timeout: 15000 }).catch(() => {});
  const idDoProduto = Number((p.url().match(/\/patrimonio\/(\d+)$/) ?? [])[1]);
  if (idDoProduto) criados.push(idDoProduto);
  const { dados: criado } = await api("GET", `/patrimonio/${idDoProduto}`, undefined, token);
  checar("o bem nasce ligado ao produto, com a nota da última entrada",
    criado?.id_produto === prod.id && criado?.nota_fiscal === `NF-WEB-${MARCA}`, criado);
  await p.goto(`${WEB}/produtos/${prod.id}`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#produto-bens", { timeout: 20000 }).catch(() => {});
  const noProduto = await p.evaluate(() => document.body.innerText);
  checar("o cadastro do produto lista o bem e diz que falta 1",
    noProduto.includes(criado?.codigo ?? "??") && /Faltam\s+1/.test(noProduto), noProduto.slice(0, 200));
} finally {
  await navegador.close();
  try { fs.unlinkSync(csv); } catch { /* já não existe */ }
  for (const id of criados) {
    const { dados: d } = await api("GET", `/patrimonio/${id}`, undefined, token);
    for (const m of d?.manutencoes ?? []) await api("DELETE", `/patrimonio/manutencoes/${m.id}`, undefined, token);
    await api("DELETE", `/patrimonio/${id}`, undefined, token);
  }
  for (const id of produtos) await api("DELETE", `/produtos/${id}`, undefined, token);
  await api("DELETE", `/setores/${setor.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
