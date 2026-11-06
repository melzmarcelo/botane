/**
 * Nota com produto INATIVO, na tela (pedido do dono, 06/11/2026).
 *
 * 🔑 *"quando vem um produto desativado em alguma nota ele não encontra … pode apontar isto e
 * caso quiser, pode dar entrada mesmo inativado"*. Confere: a linha pendente diz qual produto
 * existe e está inativo, "usar mesmo inativo" vincula e marca a linha, e o Lançar pede
 * confirmação listando o produto antes de dar entrada.
 * O cenário é montado pela API e sai no fim (nota estornada e excluída).
 *
 *    node scripts/verificar-nota-produto-inativo.mjs     (API na 9200 e o Next na 3100 de pé)
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

console.log("0. cenário: produto com código no fornecedor, desativado; nota com esse código");
const CODIGO = `NI${MARCA}`;
const { dados: forn } = await api("POST", "/fornecedores", { nome: `Fornecedor Inativo ${MARCA}`, fornecedor: true }, token);
const { dados: prod } = await api("POST", "/produtos", {
  nome: `Farinha Inativa ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", status: "ATIVO", controla_estoque: true,
  fornecedores: [{ id_fornecedor: forn.id, codigo_no_fornecedor: CODIGO, fator: 1 }],
}, token);
await api("DELETE", `/produtos/${prod.id}`, undefined, token);
const { dados: nota } = await api("POST", "/notas", {
  id_fornecedor: forn.id, numero: `I${MARCA}`, serie: "1", data_emissao: "2026-11-05",
  itens: [{ descricao: "FARINHA TIPO 1", codigo_fornecedor: CODIGO, quantidade: 2, valor_unitario: 5, um: "UN" }],
}, token);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"],
                                           defaultViewport: { width: 1366, height: 900 } });
try {
  const p = await navegador.newPage();
  const erros = [];
  p.on("pageerror", (e) => erros.push(e.message));
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  await p.goto(`${WEB}/compras/${nota.id}`, { waitUntil: "networkidle2" });
  await p.waitForSelector("[data-inativo-encontrado]", { timeout: 30000 }).catch(() => {});

  console.log("1. a linha pendente aponta o inativo");
  const texto = await p.$eval("[data-inativo-encontrado]", (e) => e.textContent).catch(() => "");
  checar("diz que o produto existe e está inativo, com o nome", /inativo/.test(texto) && texto.includes(MARCA), texto);
  checar("o Lançar fica travado enquanto a linha está pendente",
    await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Lançar no estoque")?.disabled));

  console.log("\n2. usar mesmo inativo");
  // ⚠️ Clique pelo elemento: a barra fixa do rodapé cobre a linha no fim da tabela.
  await p.$eval('[data-acao="usar-inativo"]', (b) => { b.scrollIntoView({ block: "center" }); b.click(); });
  await p.waitForSelector("[data-produto-inativo]", { timeout: 10000 }).catch(() => {});
  checar("a linha passa a mostrar o produto, marcado como inativo",
    await p.$eval("[data-produto-inativo]", (e) => /inativo/.test(e.textContent)).catch(() => false));

  console.log("\n3. lançar pede confirmação");
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Lançar no estoque")?.click());
  await p.waitForSelector("[data-lista-inativos]", { timeout: 5000 }).catch(() => {});
  checar("a confirmação lista o produto inativo",
    await p.$eval("[data-lista-inativos]", (e) => e.textContent).then((t) => t.includes(MARCA)).catch(() => false));
  const { dados: antes } = await api("GET", `/notas/${nota.id}`, undefined, token);
  checar("e nada foi lançado ainda", antes.status !== "LANCADA", antes.status);
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Lançar mesmo assim")?.click());
  await esperar(2500);
  const { dados: depois } = await api("GET", `/notas/${nota.id}`, undefined, token);
  checar("confirmado, a nota é lançada", depois.status === "LANCADA", depois.status);
  checar("nenhum erro de JavaScript", !erros.length, erros);
} finally {
  await navegador.close();
  await api("POST", `/notas/${nota.id}/estornar`, {}, token);
  await api("DELETE", `/notas/${nota.id}`, undefined, token);
  await api("DELETE", `/fornecedores/${forn.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((x) => console.log(`  - ${x}`));
process.exit(falhas.length ? 1 : 0);
