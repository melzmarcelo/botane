/**
 * Vinculados, no navegador: o rótulo do código de fora mostra o que a nota mais nova diz e
 * se corrige à mão.
 *
 * 🔑 Relatado pelo dono (23/10/2026): o PÃO BOTANE aparecia em Vinculados como "COSTELA
 * PONTA DESOSSADA KG" — o rótulo que o Omie mandou na nota em que se vinculou.
 *
 *    node scripts/verificar-codigos-do-produto.mjs     (API na 9200 e web na 3100 de pé;
 *                                                       BOTANE_API e BOTANE_WEB mudam as portas)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const API = process.env.BOTANE_API ?? "http://127.0.0.1:9200";
const WEB = process.env.BOTANE_WEB ?? "http://127.0.0.1:3100";
const MARCA = String(Date.now()).slice(-6);
const CODIGO = `V${MARCA}`;
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};
const texto = (p) => p.evaluate(() => document.body.innerText);

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

console.log("0. cenário: um pão vinculado por uma nota que o chamou de costela");
const { dados: forn } = await api("POST", "/fornecedores", { nome: `Panificadora ${MARCA}`, fornecedor: true }, token);
const { dados: pao } = await api("POST", "/produtos", {
  nome: `PAO VERIFICAR ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", status: "ATIVO", controla_estoque: true,
}, token);
const notas = [];
async function nota(descricao, data) {
  const { dados: n } = await api("POST", "/notas", {
    id_fornecedor: forn.id, numero: `N${MARCA}${notas.length}`, serie: "1", data_emissao: data,
    itens: [{ descricao, codigo_fornecedor: CODIGO, quantidade: 2, valor_unitario: 5, um: "UN" }],
  }, token);
  notas.push(n.id);
  const { dados: completa } = await api("GET", `/notas/${n.id}`, undefined, token);
  return completa.itens[0];
}
const item = await nota(`COSTELA PONTA DESOSSADA KG ${MARCA}`, "2026-10-13");
const { status: stV } = await api("POST", `/notas/itens/${item.id}/vincular`, { id_produto: pao.id, aprender: true }, token);
checar("o item de rótulo errado vincula ao pão", stV === 200, stV);
await nota(`Pao Verificar ${MARCA}`, "2026-10-20");

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1000 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  await p.goto(`${WEB}/produtos/${pao.id}`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => [...document.querySelectorAll("button,a")].some((b) => b.textContent.trim().startsWith("Vinculados")), { timeout: 30000 });
  await p.evaluate(() => [...document.querySelectorAll("button,a")].find((b) => b.textContent.trim().startsWith("Vinculados")).click());
  await p.waitForFunction((c) => document.body.innerText.includes(c), { timeout: 15000 }, CODIGO).catch(() => {});

  console.log("\n1. a aba Vinculados");
  let t = await texto(p);
  checar("mostra o rótulo gravado no vínculo", t.includes(`COSTELA PONTA DESOSSADA KG ${MARCA}`), t.slice(0, 600));
  checar("e o que a nota mais nova diz, com a data", t.includes("Na última nota (20/10/2026)") && t.includes(`Pao Verificar ${MARCA}`),
         t.slice(0, 600));

  console.log("\n2. corrigir o rótulo");
  await p.click(`button[aria-label="corrigir a descrição de ${CODIGO}"]`);
  const campo = `input[aria-label="descrição de ${CODIGO}"]`;
  await p.waitForSelector(campo);
  await p.focus(campo);
  await p.keyboard.down("Control"); await p.keyboard.press("KeyA"); await p.keyboard.up("Control");
  await p.keyboard.press("Backspace");
  await p.type(campo, `PAO BOTANE ${MARCA}`);
  await p.keyboard.press("Enter");
  // ⚠️ Espera a TABELA, não o texto da página: o aviso de sucesso já diz "PAO BOTANE …"
  // antes de a lista recarregar.
  await p.waitForFunction((m) => [...document.querySelectorAll("td")].some((td) => td.innerText.startsWith(`PAO BOTANE ${m}`)),
                          { timeout: 15000 }, MARCA).catch(() => {});
  t = await texto(p);
  checar("a tabela mostra o rótulo corrigido", !t.includes(`COSTELA PONTA DESOSSADA KG ${MARCA}`)
         && await p.evaluate((m) => [...document.querySelectorAll("td")].some((td) => td.innerText.startsWith(`PAO BOTANE ${m}`)), MARCA),
         t.slice(0, 600));
  const { dados: depois } = await api("GET", `/produtos/${pao.id}`, undefined, token);
  const linha = depois.codigos_externos.find((c) => c.codigo === CODIGO);
  checar("e o servidor gravou", linha?.descricao_externa === `PAO BOTANE ${MARCA}`, linha);
  if (process.env.FOTO) await p.screenshot({ path: process.env.FOTO });
} finally {
  await navegador.close();
  for (const id of notas.reverse()) await api("DELETE", `/notas/${id}`, undefined, token);
  await api("POST", `/produtos/${pao.id}/codigos/desvincular`,
            { sistema: "OMIE", codigo: CODIGO, id_fornecedor: forn.id, devolver: false }, token);
  await api("DELETE", `/produtos/${pao.id}`, undefined, token);
  await api("DELETE", `/fornecedores/${forn.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
