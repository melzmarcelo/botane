/**
 * Vários WhatsApps por loja (um principal), o número do catálogo e o "entre em contato".
 *
 * 🔑 Pedido do dono (30/10/2026), estudo em `docs/whatsapp-numeros-estudo.md`.
 * A lista da loja é fotografada e devolvida no fim; o catálogo do cenário é apagado.
 *
 *    node scripts/verificar-whatsapps.mjs     (API na 9200 e o Next na 3100 de pé)
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
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const texto = await r.text();
  return { status: r.status, dados: texto ? JSON.parse(texto) : null };
}

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;
const loja = async () => (await api("GET", "/unidades?incluir_inativas=true", undefined, token)).dados.find((u) => u.id === 1);
const antes = (await loja()).whatsapps;
const { dados: par } = await api("GET", "/unidades/1/parametros", undefined, token);
await api("PUT", "/unidades/1/parametros", { ...par, reservas_ligado: true }, token);

// O cenário: a loja com um número conhecido (os dela ficam, com os mesmos ids — é o que os
// catálogos de verdade guardam); um catálogo com um prato.
await api("PUT", "/unidades/1", { whatsapps: [
  ...antes.map((w) => ({ ...w, principal: false })),
  { rotulo: "Atendimento", numero: "(99) 99999-0101", principal: true }] }, token);
const N = antes.length;  // o índice da linha "Atendimento"; a nova entra depois dela
const { dados: cat } = await api("POST", "/catalogos", { nome: `Zap ${MARCA}`, origem: "PRODUTOS" }, token);
const { dados: g } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Doces" }, token);
const { dados: p0 } = await api("POST", "/produtos", { nome: `ZAP BOLO ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", controla_estoque: false }, token);
const { dados: pa } = await api("GET", `/produtos/${p0.id}`, undefined, token);
await api("PUT", `/produtos/${p0.id}`, { ...pa, integrado_pdv: true, preco_venda: 10 }, token);
await api("POST", `/catalogos/categorias/${g.id}/itens`, { id_produto: p0.id }, token);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"],
                                           defaultViewport: { width: 1280, height: 900 } });
try {
  const p = await navegador.newPage();
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. o cadastro da loja: mais um número, e ele vira o principal");
  await p.goto(`${WEB}/lojas/1`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#whatsapps-da-loja", { timeout: 20000 }).catch(() => {});
  checar("a loja mostra a lista, com o principal primeiro",
    await p.evaluate(() => document.querySelector('#whatsapps-da-loja input[aria-label="número do WhatsApp"]')?.value)
      === "(99) 99999-0101");
  await p.click("#novo-whatsapp");
  await p.type(`[data-zap="${N + 1}"] input[aria-label="nome do número"]`, "Encomendas");
  await p.type(`[data-zap="${N + 1}"] input[aria-label="número do WhatsApp"]`, "(99) 99999-0202");
  await p.click(`[data-zap="${N + 1}"] button[aria-label="tornar o principal"]`);
  checar("a estrela passa para o número novo (um principal só)",
    await p.evaluate(() => [...document.querySelectorAll("#whatsapps-da-loja [aria-pressed]")]
      .filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.closest("[data-zap]").dataset.zap)
      .join(",")) === String(N + 1));
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => /^Salvar/.test(b.textContent.trim()))?.click());
  await esperar(1500);
  const depois = await loja();
  checar("gravou os dois, com o novo como principal (e o campo da loja espelha)",
    depois.whatsapps.length === N + 2 && depois.whatsapps[0].rotulo === "Encomendas" && depois.whatsapps[0].principal
      && depois.whatsapp === "(99) 99999-0202", depois.whatsapps);
  const atendimento = depois.whatsapps.find((w) => w.rotulo === "Atendimento");

  console.log("\n2. o catálogo escolhe o número e liga o 'entre em contato'");
  await p.goto(`${WEB}/catalogos/${cat.id}?aba=publicacao`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#catalogo-whatsapp", { timeout: 20000 }).catch(() => {});
  const opcoes = await p.$$eval("#catalogo-whatsapp option", (os) => os.map((o) => o.textContent));
  checar("o seletor lista 'o principal da loja' e os números",
    opcoes.length === N + 3 && /principal da loja/.test(opcoes[0]) && opcoes.some((o) => /Atendimento/.test(o)), opcoes);
  await p.select("#catalogo-whatsapp", String(atendimento.id));
  await p.click("#catalogo-permite-contato");
  await p.evaluate(() => [...document.querySelectorAll("button[type=submit]")].find((b) => /Salvar/.test(b.textContent))?.click());
  await esperar(1500);
  const { dados: c } = await api("GET", `/catalogos/${cat.id}`, undefined, token);
  checar("gravou o número e o botão de contato", c.id_whatsapp === atendimento.id && c.permite_contato === true, c);

  console.log("\n3. o site mostra o botão no cabeçalho, para o número do catálogo");
  await p.goto(`${WEB}/catalogos/${cat.id}?aba=previa`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#previa-catalogo", { timeout: 15000 }).catch(() => {});
  const f = await (await p.$("#previa-catalogo"))?.contentFrame();
  await f?.waitForFunction(() => document.querySelector('[data-tela="cardapio"] .contato-catalogo:not([hidden])'), { timeout: 20000 }).catch(() => {});
  const href = await f?.evaluate(() => document.querySelector('[data-tela="cardapio"] .contato-catalogo')?.getAttribute("href") ?? "");
  checar("o botão abre o WhatsApp do catálogo (Atendimento), não o principal",
    (href ?? "").startsWith("https://wa.me/99999990101?text=") && decodeURIComponent(href).includes(`Zap ${MARCA}`), href);

  console.log("\n4. o Cardápio Vivo leva o botão no topo");
  await p.goto(`${WEB}/c/previa/${cat.id}`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#cv-contato", { timeout: 20000 }).catch(() => {});
  const cv = await p.$eval("#cv-contato", (a) => a.getAttribute("href")).catch(() => "");
  checar("o feed tem o botão de WhatsApp do catálogo", (cv ?? "").startsWith("https://wa.me/99999990101"), cv);

  console.log("\n5. desligado, o botão some");
  await api("PUT", `/catalogos/${cat.id}`, { permite_contato: false }, token);
  await p.goto(`${WEB}/c/previa/${cat.id}`, { waitUntil: "networkidle2" });
  await esperar(1500);
  checar("o feed sem o botão", !(await p.$("#cv-contato")));
} finally {
  await navegador.close();
  await api("PUT", "/unidades/1", { whatsapps: antes }, token);
  await api("PUT", `/catalogos/${cat.id}`, { situacao: "INATIVO" }, token);
  await api("PUT", "/unidades/1/parametros", par, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((x) => console.log(`  - ${x}`));
process.exit(falhas.length ? 1 : 0);
