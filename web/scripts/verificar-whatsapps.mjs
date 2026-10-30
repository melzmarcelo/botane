/**
 * Vários WhatsApps por loja (um principal), o número do catálogo e o "entre em contato"; e,
 * desde a 146, a conexão de cada número com a Meta e o número de cada aviso — tudo na aba
 * WhatsApp da loja.
 *
 * 🔑 Pedidos do dono (30/10/2026), estudo em `docs/whatsapp-numeros-estudo.md`.
 * A lista da loja e os avisos são fotografados e devolvidos no fim; o catálogo do cenário é
 * apagado.
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
const zapAntes = (await api("GET", "/unidades/1/whatsapp", undefined, token)).dados;
const avisosAntes = zapAntes.avisos.map((a) => ({ evento: a.evento, ativo: a.ativo, modelo: a.modelo,
  idioma: a.idioma, antecedencia: a.antecedencia, whatsapp: a.id_whatsapp ? String(a.id_whatsapp) : null }));
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

  console.log("1. a aba WhatsApp da loja: mais um número, principal e conectado");
  await p.goto(`${WEB}/lojas/1`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#whatsapps-na-aba", { timeout: 20000 }).catch(() => {});
  checar("o cadastro da loja não tem mais a lista: aponta para a aba WhatsApp",
    !!(await p.$("#whatsapps-na-aba")) && !(await p.$("#whatsapps-da-loja")));
  await p.goto(`${WEB}/lojas/1?aba=whatsapp`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#whatsapps-da-loja", { timeout: 20000 }).catch(() => {});
  checar("a aba mostra a lista, com o principal primeiro",
    await p.evaluate(() => document.querySelector('#whatsapps-da-loja input[aria-label="número do WhatsApp"]')?.value)
      === "(99) 99999-0101");
  // ⚠️ Clique pelo elemento: o indicador do Next, no canto da tela, cobre o "+ número" quando a
  // rolagem o deixa no pé da janela, e o clique por coordenada cai nele.
  await p.$eval("#novo-whatsapp", (b) => b.click());
  const nova = `[data-zap="${N + 1}"]`;
  await p.type(`${nova} input[aria-label="nome do número"]`, "Encomendas");
  await p.type(`${nova} input[aria-label="número do WhatsApp"]`, "(99) 99999-0202");
  await p.click(`${nova} button[aria-label="tornar o principal"]`);
  checar("a estrela passa para o número novo (um principal só)",
    await p.evaluate(() => [...document.querySelectorAll("#whatsapps-da-loja [aria-pressed]")]
      .filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.closest("[data-zap]").dataset.zap)
      .join(",")) === String(N + 1));
  // A conexão do número novo: abre o bloco, liga, identificador e token.
  await p.click(`${nova} details summary`);
  await p.click(`${nova} input[aria-label="conectar este número"]`);
  await p.type(`${nova} input[aria-label="Phone number ID"]`, `PNID${MARCA}`);
  await p.type(`${nova} input[aria-label="token"]`, `tok-${MARCA}`);
  checar("o número sem ★ oferece usar a conta do principal",
    !!(await p.$(`[data-zap="${N}"] input[aria-label="usar a conta do principal"]`))
      && !(await p.$(`${nova} input[aria-label="usar a conta do principal"]`)));
  // O lembrete sai pelo "Atendimento" (o número que deixou de ser o principal).
  const valorAtd = await p.$eval('[data-aviso-numero="RESERVA_LEMBRETE"]',
    (s) => [...s.options].find((o) => /Atendimento/.test(o.textContent))?.value ?? "");
  await p.select('[data-aviso-numero="RESERVA_LEMBRETE"]', valorAtd);
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Salvar WhatsApp")?.click());
  await esperar(2000);
  const depois = await loja();
  checar("gravou os dois, com o novo como principal (e o campo da loja espelha)",
    depois.whatsapps.length === N + 2 && depois.whatsapps[0].rotulo === "Encomendas" && depois.whatsapps[0].principal
      && depois.whatsapp === "(99) 99999-0202", depois.whatsapps);
  const atendimento = depois.whatsapps.find((w) => w.rotulo === "Atendimento");
  const { dados: zap } = await api("GET", "/unidades/1/whatsapp", undefined, token);
  const enc = zap.numeros.find((n) => n.rotulo === "Encomendas") ?? {};
  checar("e a conexão do novo: ligado, simulado, com o identificador e o token (que não volta)",
    enc.conectado && enc.modo === "simulado" && enc.phone_number_id === `PNID${MARCA}` && enc.token_configurado
      && !JSON.stringify(zap).includes(`tok-${MARCA}`), enc);
  checar("o lembrete sai pelo Atendimento",
    zap.avisos.find((a) => a.evento === "RESERVA_LEMBRETE")?.id_whatsapp === atendimento.id,
    zap.avisos.find((a) => a.evento === "RESERVA_LEMBRETE"));
  await p.reload({ waitUntil: "networkidle2" });
  await p.waitForSelector("#whatsapps-da-loja", { timeout: 20000 }).catch(() => {});
  checar("recarregada, a aba mostra o novo conectado e o webhook dele",
    await p.evaluate(() => {
      const linha = document.querySelector('[data-zap="0"]');
      return /modo simulado/.test(linha?.textContent ?? "") && /Token de verificação/.test(linha?.textContent ?? "");
    }));

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
  await api("PUT", "/unidades/1/whatsapp", { avisos: avisosAntes }, token);
  await api("PUT", `/catalogos/${cat.id}`, { situacao: "INATIVO" }, token);
  await api("PUT", "/unidades/1/parametros", par, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((x) => console.log(`  - ${x}`));
process.exit(falhas.length ? 1 : 0);
