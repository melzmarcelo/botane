/**
 * O assistente pelo WhatsApp, etapa 1 (migração 151): o número da casa em Integrações ▸
 * Assistente e o vínculo do próprio telefone no Perfil — gerar o código, o webhook ligar,
 * desvincular.
 *
 * 🔑 Pedido do dono (06/11/2026), com o número compartilhado entre as lojas. Estudo em
 * `docs/assistente-whatsapp-estudo.md`. A configuração é fotografada e devolvida no fim (⚠️ a
 * chave secreta, se havia uma, fica a do teste — o roteiro avisa). Tudo em modo simulado.
 *
 *    node scripts/verificar-assistente-whatsapp.mjs     (API na 9200 e o Next na 3100 de pé)
 */
import { createHmac } from "node:crypto";
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const API = "http://127.0.0.1:9200";
const WEB = "http://127.0.0.1:3100";
const MARCA = String(Date.now()).slice(-6);
const PNID = `PNIDTELA${MARCA}`;
const SEGREDO = `segredo-tela-${MARCA}`;
const NUMERO = `(99) 6${MARCA.slice(0, 4)}-${MARCA.slice(2, 6)}`;
const FONE_DONO = `55479${MARCA}33`;
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(metodo, caminho, corpo, token, cabecalhos = {}) {
  const r = await fetch(API + caminho, {
    method: metodo,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...cabecalhos },
    body: corpo === undefined ? undefined : (typeof corpo === "string" ? corpo : JSON.stringify(corpo)),
  });
  const texto = await r.text();
  try { return { status: r.status, dados: texto ? JSON.parse(texto) : null }; }
  catch { return { status: r.status, dados: texto }; }
}

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;
const antes = (await api("GET", "/assistente/config", undefined, token)).dados;
const vinculoAntes = (await api("GET", "/assistente/vinculo", undefined, token)).dados;

function webhook(texto) {
  const corpo = JSON.stringify({ entry: [{ changes: [{ value: { metadata: { phone_number_id: PNID },
    messages: [{ from: FONE_DONO, id: `wamid.tela.${MARCA}.${Math.random()}`, type: "text", text: { body: texto } }] } }] }] });
  const assinatura = "sha256=" + createHmac("sha256", SEGREDO).update(corpo).digest("hex");
  return api("POST", "/publico/whatsapp/webhook", corpo, undefined, { "X-Hub-Signature-256": assinatura });
}

async function digitar(p, seletor, valor) {
  await p.$eval(seletor, (el) => { el.value = ""; });
  await p.type(seletor, valor);
}

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"],
                                           defaultViewport: { width: 1280, height: 900 } });
try {
  const p = await navegador.newPage();
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. Integrações ▸ Assistente: o número da casa");
  await p.goto(`${WEB}/integracoes?aba=assistente`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#config-assistente", { timeout: 20000 }).catch(() => {});
  checar("a aba Assistente existe em Integrações", !!(await p.$("#config-assistente")));
  checar("mostra o webhook e o token de verificação para colar na Meta",
    await p.evaluate(() => document.querySelector("#config-assistente").textContent.includes("/publico/whatsapp/webhook")));
  if (!(await p.$eval('input[aria-label="ligar o assistente"]', (c) => c.checked)))
    await p.click('input[aria-label="ligar o assistente"]');
  await p.click('[data-modo="simulado"]');
  await digitar(p, 'input[aria-label="número do assistente"]', NUMERO);
  await digitar(p, 'input[aria-label="Phone number ID"]', PNID);
  await digitar(p, 'input[aria-label="chave secreta"]', SEGREDO);
  await p.$eval("#salvar-assistente", (b) => b.click());
  await esperar(1200);
  const gravado = (await api("GET", "/assistente/config", undefined, token)).dados;
  checar("salvar grava o número ligado, em modo simulado, com a chave secreta",
    gravado.ativa && gravado.modo === "simulado" && gravado.numero === NUMERO && gravado.segredo_configurado, gravado);
  checar("a chave secreta volta como “configurada”, nunca o valor",
    await p.$eval('input[aria-label="chave secreta"]', (i) => i.value === "" && i.placeholder.includes("•")));

  console.log("\n2. o Perfil: vincular pelo código");
  await api("DELETE", "/assistente/vinculo", undefined, token);
  await p.goto(`${WEB}/perfil`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#gerar-codigo-assistente", { timeout: 20000 }).catch(() => {});
  checar("o cartão do assistente aparece, sem WhatsApp vinculado",
    await p.evaluate(() => document.querySelector("[data-vinculado]")?.dataset.vinculado === "false"));
  await p.$eval("#gerar-codigo-assistente", (b) => b.click());
  await p.waitForSelector("#codigo-assistente", { timeout: 10000 }).catch(() => {});
  const gerado = await p.evaluate(() => {
    const c = document.querySelector("#codigo-assistente");
    return { mensagem: c?.querySelector(".mono")?.textContent ?? "",
             link: c?.querySelector("a[href*='wa.me']")?.getAttribute("href") ?? "",
             texto: c?.textContent ?? "" };
  });
  const codigo = (gerado.mensagem.match(/BOTANE ([A-Z0-9]{8})/) || [])[1];
  checar("o código aparece com a mensagem pronta", !!codigo, gerado);
  checar("o botão abre o WhatsApp do número da casa com o texto",
    gerado.link.includes(`?text=BOTANE%20${codigo}`) && gerado.texto.includes(NUMERO), gerado);

  const r = await webhook(`BOTANE ${codigo}`);
  checar("o WhatsApp manda o código e o webhook aceita", r.status === 200 && r.dados?.respostas === 1, r);
  await p.evaluate(() => [...document.querySelectorAll("#codigo-assistente button")]
    .find((b) => b.textContent.includes("atualiza"))?.click());
  await p.waitForSelector('[data-vinculado="true"]', { timeout: 10000 }).catch(() => {});
  checar("a tela passa a mostrar o telefone vinculado",
    await p.evaluate(() => document.querySelector('[data-vinculado="true"]')?.textContent.includes("+55 (47)")));

  console.log("\n3. desvincular");
  await p.evaluate(() => [...document.querySelectorAll("#assistente-whatsapp button")]
    .find((b) => b.textContent.trim() === "desvincular")?.click());
  await esperar(200);
  await p.evaluate(() => [...document.querySelectorAll("#assistente-whatsapp button")]
    .find((b) => b.textContent.trim() === "Desvincular")?.click());
  await p.waitForSelector('[data-vinculado="false"]', { timeout: 10000 }).catch(() => {});
  checar("desvincula, com confirmação", !!(await p.$('[data-vinculado="false"]')));
} finally {
  await navegador.close();
  await api("DELETE", "/assistente/vinculo", undefined, token);
  await api("PUT", "/assistente/config", { ativa: antes.ativa, modo: antes.modo, numero: antes.numero,
    phone_number_id: antes.phone_number_id, waba_id: antes.waba_id, api_versao: antes.api_versao,
    token: "", app_secret: "" }, token);
  if (antes.segredo_configurado) console.log("  ⚠️ havia chave secreta do assistente: cole a verdadeira de novo em Integrações");
  if (vinculoAntes?.vinculado) console.log("  ⚠️ o admin tinha WhatsApp vinculado antes: vincule de novo em Perfil");
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const f of falhas) console.log("  -", f);
process.exit(falhas.length ? 1 : 0);
