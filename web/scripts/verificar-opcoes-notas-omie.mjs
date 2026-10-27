/**
 * Integrações ▸ Omie, no navegador: "Somente recebidas" e "Lançar notas recebidas".
 *
 * 🔑 Pedido do dono (23/10/2026). A regra é coberta por `api/tests/smoke_notas_recebidas.py`;
 * aqui só se confere que a tela mostra, grava e devolve as duas opções.
 * ⚠️ Volta a configuração como estava no fim — a conta daqui pode ser a real.
 *
 *    node scripts/verificar-opcoes-notas-omie.mjs   (API na 9200 e web na 3100 de pé;
 *                                                    BOTANE_API e BOTANE_WEB mudam as portas)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const API = process.env.BOTANE_API ?? "http://127.0.0.1:9200";
const WEB = process.env.BOTANE_WEB ?? "http://127.0.0.1:3100";
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
const { dados: antes } = await api("GET", "/omie/config", undefined, token);
// ⚠️ O PUT regrava tudo: volta com o que estava (a chave em branco mantém a guardada).
const corpo = {
  modo: antes.modo, ativa: antes.ativa, tag_fornecedor: antes.tag_fornecedor,
  agenda_frequencia: antes.agenda_frequencia, agenda_hora: antes.agenda_hora,
  agenda_janela_dias: antes.agenda_janela_dias,
};
await api("PUT", "/omie/config", { ...corpo, so_recebidas: false, lancar_recebidas: false }, token);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1000 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  await p.goto(`${WEB}/integracoes`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#opcoes-notas-omie", { timeout: 30000 }).catch(() => {});

  console.log("1. as duas opções na tela do Omie");
  const caixas = () => p.evaluate(() => [...document.querySelectorAll("#opcoes-notas-omie input[type=checkbox]")]
    .map((c) => ({ marcada: c.checked, texto: c.closest("label")?.innerText ?? "" })));
  let c = await caixas();
  checar("Somente recebidas e Lançar notas recebidas aparecem, desmarcadas",
    c.length === 2 && /somente recebidas/i.test(c[0].texto) && /lançar notas recebidas/i.test(c[1].texto)
      && !c[0].marcada && !c[1].marcada, c);
  // 🔑 Desde 27/10/2026 as que já esperavam também entram, e o recebimento desfeito estorna.
  checar("a tela diz que as que já esperavam também entram, e que o desfeito estorna",
    /também as que já esperavam/i.test(c[1]?.texto ?? "")
      && /estornado/i.test(c[1]?.texto ?? ""), c[1]?.texto);

  // 🔑 O corte de data (136): o campo aparece com o que o servidor tem.
  const corte = await p.evaluate(() => document.querySelector("#lancar-recebidas-corte")?.value ?? null);
  checar("o corte de data aparece, com o valor do servidor",
    corte !== null && corte === (antes.lancar_recebidas_corte ?? "").slice(0, 10),
    { corte, servidor: antes.lancar_recebidas_corte });

  console.log("\n2. marcar e salvar");
  await p.click("#opcoes-notas-omie label:nth-of-type(1) input");
  await p.click("#opcoes-notas-omie label:nth-of-type(2) input");
  await p.evaluate(() => document.querySelector("#opcoes-notas-omie").closest("form")
    .querySelector("button[type=submit]").click());
  await p.waitForFunction(() => /Ligado em/.test(document.querySelector("#opcoes-notas-omie")?.innerText ?? ""),
                          { timeout: 15000 }).catch(() => {});
  const { dados: depois } = await api("GET", "/omie/config", undefined, token);
  checar("o servidor gravou as duas", depois.so_recebidas === true && depois.lancar_recebidas === true,
    { so: depois.so_recebidas, lancar: depois.lancar_recebidas });
  c = await caixas();
  checar("recarregada, a tela mostra marcadas e desde quando o lançamento vale",
    c[0]?.marcada && c[1]?.marcada && /Ligado em/.test(c[1]?.texto ?? ""), c);
  if (process.env.FOTO) await p.screenshot({ path: process.env.FOTO, fullPage: true });
} finally {
  await navegador.close();
  await api("PUT", "/omie/config", {
    ...corpo, so_recebidas: !!antes.so_recebidas, lancar_recebidas: !!antes.lancar_recebidas,
  }, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
