/**
 * Mover códigos para outro produto, no navegador.
 *
 * 🔑 Pedido do dono (10/11/2026), o caso CATCHUP × KETCHUP: a fusão recusou porque os dois
 * tinham movimento, e os códigos do CATCHUP ficaram presos nele.
 *   1. aba Vinculados → "Mover códigos para outro produto" → escolhe o destino, a
 *      conversão vem sugerida, move — e o servidor confirma
 *   2. a fusão travada oferece "mover os códigos de … para cá"
 *
 *    node scripts/verificar-mover-codigos.mjs     (API na 9200 e web na 3100 de pé)
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
const texto = (p) => p.evaluate(() => document.body.innerText);
const clicarTexto = (p, inicio) => p.evaluate((i) => {
  const b = [...document.querySelectorAll("button,a")].find((x) => x.textContent.trim().startsWith(i));
  if (b) b.click();
  return !!b;
}, inicio);

// O campo de busca de produto da janela aberta: o último com esse placeholder (a página
// por trás tem outros campos, e o "último input" não é o da janela).
const campoDeBusca = async (p) => (await p.$$('input[placeholder="código ou nome"]')).at(-1);

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

console.log("0. cenário: dois cadastros do mesmo produto, os dois com movimento");
const { dados: locais } = await api("GET", "/locais", undefined, token);
async function produto(prefixo, nome, omie, fator) {
  const { dados } = await api("POST", "/produtos", {
    codigo: `${prefixo}${MARCA}`, nome: `${nome} ${MARCA}`, tipo: "INSUMO", um_estoque: "KG",
    um_compra: "UN", fator_compra: fator, status: "ATIVO", controla_estoque: true, codigo_omie: omie,
  }, token);
  await api("POST", "/estoque/entradas", { id_produto: dados.id, quantidade: 1, custo_unitario: 10,
                                           id_local: locais[0].id }, token);
  return dados;
}
const origem = await produto("VMC", "CATCHUP VERIFICAR", `71${MARCA}`, 2);
const destino = await produto("VMK", "KETCHUP VERIFICAR", `72${MARCA}`, 3.8);
const outra = await produto("VMO", "CATSUP VERIFICAR", `73${MARCA}`, 1);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1000 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("\n1. pela aba Vinculados");
  await p.goto(`${WEB}/produtos/${origem.id}`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => [...document.querySelectorAll("button,a")].some((b) => b.textContent.trim().startsWith("Vinculados")), { timeout: 30000 });
  await clicarTexto(p, "Vinculados");
  await p.waitForFunction(() => document.body.innerText.includes("Mover códigos para outro produto"), { timeout: 15000 }).catch(() => {});
  checar("o botão aparece mesmo sem código vinculado na tabela", await clicarTexto(p, "Mover códigos para outro produto"));
  await p.waitForFunction(() => document.body.innerText.includes("Produto de destino"), { timeout: 10000 }).catch(() => {});
  await (await campoDeBusca(p)).type(`VMK${MARCA}`);
  await p.keyboard.press("Enter");
  await p.waitForSelector("#codigos-a-mover", { timeout: 15000 }).catch(() => {});
  let t = await texto(p);
  checar("a prévia lista o código do Omie da coluna", t.includes(`71${MARCA}`) && t.includes("principal do cadastro"), t.slice(-900));
  const sugerido = await p.$eval(`input[aria-label="conversão de 71${MARCA}"]`, (i) => i.value).catch(() => null);
  checar("a conversão vem sugerida (mesma unidade: o fator da origem, 2)", sugerido === "2", sugerido);
  checar("o botão diz quantos vão", await clicarTexto(p, "Mover 1 código"));
  await p.waitForFunction(() => !document.querySelector("#codigos-a-mover"), { timeout: 15000 }).catch(() => {});
  const { dados: k } = await api("GET", `/produtos/${destino.id}`, undefined, token);
  const linha = k.codigos_externos.find((c) => c.codigo === `71${MARCA}`);
  checar("o servidor gravou no destino, com a conversão confirmada",
         linha?.fator === 2 && linha?.fator_confirmado === true && linha?.origem_vinculo === "MOVIDO", linha);
  const { dados: o } = await api("GET", `/produtos/${origem.id}`, undefined, token);
  checar("e a coluna da origem ficou vazia", !o.codigo_omie, o.codigo_omie);

  console.log("\n2. pela fusão travada");
  await p.goto(`${WEB}/produtos/${destino.id}`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent.trim() === "Vincular"), { timeout: 30000 });
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Vincular").click());
  await p.waitForFunction(() => document.body.innerText.includes("Acrescentar cadastro"), { timeout: 10000 });
  await (await campoDeBusca(p)).type(`VMO${MARCA}`);
  await p.keyboard.press("Enter");
  await p.waitForFunction(() => document.body.innerText.includes("não pode ser absorvido"), { timeout: 15000 }).catch(() => {});
  t = await texto(p);
  checar("a fusão diz que não pode", t.includes("não pode ser absorvido"), t.slice(-900));
  checar("e oferece mover os códigos para cá", await clicarTexto(p, "mover os códigos de"));
  await p.waitForSelector("#codigos-a-mover", { timeout: 15000 }).catch(() => {});
  t = await texto(p);
  checar("a janela já vem com o destino desta tela", t.includes(`Para VMK${MARCA}`) && t.includes(`73${MARCA}`), t.slice(-900));
  if (process.env.FOTO) await p.screenshot({ path: process.env.FOTO });
} finally {
  await navegador.close();
  for (const pr of [origem, destino, outra]) await api("DELETE", `/produtos/${pr.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
