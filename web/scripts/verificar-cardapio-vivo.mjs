/**
 * O Cardápio Vivo (113) no navegador, em tamanho de celular: o feed abre pela mesa, a rolagem
 * encaixa um prato por tela, a categoria ativa acompanha, a seleção guarda e os eventos saem.
 *
 * 🔑 Pedido do dono (14/10/2026) — ver `docs/cardapio-vivo-estudo.md`.
 * O cenário (catálogo, produtos, salão, mesa) é montado pela API; no fim o catálogo vira
 * INATIVO (catálogo ativo não se apaga), a mesa e o salão saem, e a configuração da loja volta.
 *
 *    node scripts/verificar-cardapio-vivo.mjs     (API na 9200 e web na 3100 de pé)
 */
import puppeteer from "puppeteer-core";
import { devolverVivos, ligarDeTeste } from "./cardapio-vivo-comum.mjs";

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
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}),
               "X-Unidade": "1" },
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
const { dados: lojas } = await api("GET", "/unidades", undefined, token);
const lojaAntes = lojas.find((u) => u.id === 1);

async function produto(nome, preco) {
  const { dados: p } = await api("POST", "/produtos", { nome: `${nome} ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", controla_estoque: false }, token);
  const { dados: atual } = await api("GET", `/produtos/${p.id}`, undefined, token);
  await api("PUT", `/produtos/${p.id}`, { ...atual, integrado_pdv: true, preco_venda: preco }, token);
  return p.id;
}

console.log("0. cenário: um cardápio de duas seções, um salão com uma mesa");
const { dados: cat } = await api("POST", "/catalogos", { nome: `Vivo tela ${MARCA}`, origem: "PRODUTOS", situacao: "ATIVO" }, token);
const { dados: g1 } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Pratos", ordem: 1 }, token);
const { dados: g2 } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Bebidas", ordem: 2 }, token);
const itens = [];
for (const [sec, n, v] of [[g1, "TELA RISOTO", 58], [g1, "TELA BATATA", 32], [g2, "TELA SUCO", 12]]) {
  const { dados: it } = await api("POST", `/catalogos/categorias/${sec.id}/itens`, { id_produto: await produto(n, v) }, token);
  itens.push(it.id);
}
const { dados: salao } = await api("POST", "/reservas/saloes", { nome: `Tela ${MARCA}` }, token);
const { dados: mesa } = await api("POST", "/reservas/mesas", { id_salao: salao.id, nome: "T1", lugares: 2 }, token);
const r = await ligarDeTeste(api, token, antes, cat.id);
checar("a configuração aponta o catálogo", r.status === 200, r.dados);
const { dados: acesso } = await api("GET", "/cardapio-vivo/mesas", undefined, token);
const link = acesso.mesas.find((m) => m.id === mesa.id)?.link ?? "";
checar("a mesa criada pelo salão já nasce com link (token)", /\/c\/1\/[0-9a-f]{16}$/.test(link), link);
const caminho = new URL(link).pathname;

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
const eventos = [];
try {
  const pagina = await navegador.newPage();
  await pagina.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  // ⚠️ O puppeteer não mostra o corpo de um `sendBeacon`: a página guarda uma cópia de cada
  // lote antes de mandá-lo (o envio continua o de verdade).
  await pagina.evaluateOnNewDocument(() => {
    window.__lotes = [];
    const original = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = (url, dados) => {
      if (dados instanceof Blob) dados.text().then((t) => window.__lotes.push(t));
      return original(url, dados);
    };
  });
  const erros = [];
  pagina.on("pageerror", (e) => erros.push(e.message));

  console.log("\n1. abre pela mesa");
  await pagina.goto(WEB + caminho, { waitUntil: "networkidle2" });
  await pagina.waitForSelector(".cv-item", { timeout: 20000 });
  const topo = await pagina.$eval("header", (h) => h.innerText);
  checar("o topo diz a mesa e o salão", topo.includes("T1") && topo.includes(`Tela ${MARCA}`), topo);
  const nomes = await pagina.$$eval(".cv-item h2", (hs) => hs.map((h) => h.textContent));
  checar("três pratos, na ordem do cardápio", nomes.length === 3 && nomes[0].startsWith("TELA RISOTO")
         && nomes[2].startsWith("TELA SUCO"), nomes);
  const ativa = () => pagina.$eval('nav [aria-current="true"]', (b) => b.textContent);
  checar("a categoria ativa é a primeira", (await ativa()) === "Pratos", await ativa());
  const alturas = await pagina.$$eval(".cv-item", (s) => s.map((x) => Math.round(x.getBoundingClientRect().height)));
  checar("cada prato ocupa a tela inteira", alturas.every((h) => h === 844), alturas);
  const rola = await pagina.evaluate(() => { window.scrollTo(9999, 0); return window.scrollX; });
  checar("a página não rola de lado", rola === 0, rola);

  console.log("\n2. o aviso de cookies");
  const aviso = await pagina.$$eval("button", (bs) => bs.some((b) => b.textContent === "Entendi"));
  checar("aparece na primeira visita", aviso);
  await pagina.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Entendi")?.click());

  console.log("\n3. a rolagem encaixa e a categoria acompanha");
  const rolar = (n) => pagina.evaluate((n) => {
    const r = document.querySelector(".snap-y");
    r.scrollTo({ top: n * r.clientHeight });
  }, n);
  await rolar(2);
  await esperar(900);
  checar("no terceiro prato, a categoria ativa vira Bebidas", (await ativa()) === "Bebidas", await ativa());
  await pagina.evaluate(() => [...document.querySelectorAll("nav button")].find((b) => b.textContent === "Pratos").click());
  await esperar(1200);
  checar("tocar em Pratos volta ao primeiro", (await ativa()) === "Pratos", await ativa());

  console.log("\n4. a minha seleção");
  await pagina.evaluate(() => [...document.querySelectorAll(".cv-item button")]
    .find((b) => b.textContent.includes("Adicionar à minha seleção")).click());
  await esperar(300);
  const estrela = await pagina.$$eval("header button", (bs) => bs.find((b) => b.textContent.startsWith("★"))?.textContent);
  checar("o contador sobe para 1", estrela === "★ 1", estrela);
  await pagina.evaluate(() => [...document.querySelectorAll("header button")].find((b) => b.textContent.startsWith("★")).click());
  await pagina.waitForSelector('[aria-label="Minha seleção"]');
  const resumo = await pagina.$eval('[aria-label="Minha seleção"]', (d) => d.innerText);
  checar("o resumo mostra o prato, a mesa e o total", resumo.includes("TELA RISOTO") && resumo.includes("Mesa T1")
         && resumo.includes("58,00"), resumo);
  // O que estava na fila sai no `pagehide`; recolhe antes de a página (e a cópia) sumir.
  await pagina.evaluate(() => window.dispatchEvent(new Event("pagehide")));
  await esperar(300);
  for (const t of await pagina.evaluate(() => window.__lotes)) {
    try { eventos.push(...JSON.parse(t).eventos); } catch { /* lote ilegível */ }
  }
  await pagina.reload({ waitUntil: "networkidle2" });
  await pagina.waitForSelector(".cv-item");
  const depois = await pagina.$$eval("header button", (bs) => bs.find((b) => b.textContent.startsWith("★"))?.textContent);
  checar("a seleção sobrevive a recarregar a página (fica no aparelho)", depois === "★ 1", depois);
  await pagina.evaluate(() => [...document.querySelectorAll("header button")].find((b) => b.textContent.startsWith("★")).click());
  await pagina.waitForSelector('[aria-label="Minha seleção"]');
  await pagina.evaluate(() => [...document.querySelectorAll('[aria-label="Minha seleção"] button')].find((b) => b.textContent === "Remover").click());
  await pagina.evaluate(() => document.querySelector('[aria-label="Minha seleção"] button[aria-label="Fechar"]').click());
  const zerada = await pagina.$$eval("header button", (bs) => bs.find((b) => b.textContent.startsWith("★"))?.textContent);
  checar("remover zera o contador", zerada === "★ 0", zerada);

  console.log("\n4b. favoritos (114)");
  const coracao = () => pagina.$$eval("header button", (bs) => bs.find((b) => b.textContent.startsWith("♥"))?.textContent);
  await pagina.evaluate(() => document.querySelector('.cv-item button[aria-label="Favoritar"]').click());
  await esperar(200);
  checar("o coração do prato favorita, e o topo conta 1", (await coracao()) === "♥ 1", await coracao());
  checar("e não mexe na seleção (favorito não é pedido)",
         (await pagina.$$eval("header button", (bs) => bs.find((b) => b.textContent.startsWith("★"))?.textContent)) === "★ 0");
  await pagina.evaluate(() => [...document.querySelectorAll("header button")].find((b) => b.textContent.startsWith("♥")).click());
  const lista = await pagina.$eval('[role="dialog"][aria-label="Meus favoritos"]', (d) => d.innerText);
  checar("a lista de favoritos mostra o prato", lista.includes("TELA RISOTO"), lista);
  await pagina.evaluate(() => document.querySelector('[role="dialog"][aria-label="Meus favoritos"] button[aria-label="Fechar"]').click());

  console.log("\n5. os eventos saem em lote");
  await rolar(1);
  await esperar(1500);
  await rolar(0);
  await esperar(11000); // o lote sai a cada 10 s
  for (const t of await pagina.evaluate(() => window.__lotes)) {
    try { eventos.push(...JSON.parse(t).eventos); } catch { /* lote ilegível */ }
  }
  const tipos = new Set(eventos.map((e) => e.tipo));
  checar("abriu_cardapio, viu_item, adicionou e removeu chegaram",
         ["abriu_cardapio", "viu_item", "adicionou", "removeu"].every((t) => tipos.has(t)), [...tipos]);
  checar("e os novos: favoritou, deslizou_frente e deslizou_tras",
         ["favoritou", "deslizou_frente", "deslizou_tras"].every((t) => tipos.has(t)), [...tipos]);
  const viu = eventos.find((e) => e.tipo === "viu_item" && e.item);
  checar("o viu_item leva o item, a mídia e a duração", viu && viu.midia && viu.duracao_ms >= 300, viu);
  checar("nenhum erro de JavaScript na página", erros.length === 0, erros);

  console.log("\n5b. a tela de entrada (Hub)");
  await api("PUT", "/unidades/1", { google_avaliacao_url: "https://g.page/r/teste/review",
                                    wifi_rede: `Rede ${MARCA}`, wifi_senha: "senha123" }, token);
  await ligarDeTeste(api, token, antes, cat.id, {}, { hub_avaliacao: true, hub_wifi: true });
  await pagina.evaluate(() => { window.__lotes = []; });
  await pagina.reload({ waitUntil: "networkidle2" });
  await pagina.waitForFunction(() => document.body.innerText.includes("Ver cardápio"), { timeout: 15000 }).catch(() => {});
  const hub = await pagina.evaluate(() => document.body.innerText);
  checar("com Wi-Fi e avaliação ligados, o Hub aparece antes do feed",
         hub.includes("Ver cardápio") && hub.includes("Avaliar no Google") && hub.includes("Wi-Fi"),
         hub.slice(0, 200));
  checar("e o feed ainda não está na tela", (await pagina.$(".cv-item")) === null);
  const link = await pagina.$eval('a[href^="https://g.page"]', (a) => a.target);
  checar("o link do Google abre em outra aba", link === "_blank", link);
  await pagina.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Wi-Fi").click());
  const wifi = await pagina.$eval('[aria-label="Wi-Fi"][role="region"]', (d) => d.innerText);
  checar("o Wi-Fi mostra a rede e a senha", wifi.includes(`Rede ${MARCA}`) && wifi.includes("senha123"), wifi);
  checar("com botão de copiar", (await pagina.$$eval("button", (bs) => bs.some((b) => b.textContent === "Copiar"))));
  await pagina.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Ver cardápio").click());
  await pagina.waitForSelector(".cv-item");
  checar("Ver cardápio leva ao feed", true);
  await pagina.evaluate(() => window.dispatchEvent(new Event("pagehide")));
  await esperar(300);
  const doHub = new Set();
  for (const t of await pagina.evaluate(() => window.__lotes)) {
    try { JSON.parse(t).eventos.forEach((e) => doHub.add(e.tipo)); } catch { /* lote ilegível */ }
  }
  checar("abriu_hub, clicou_wifi e abriu_cardapio chegaram",
         ["abriu_hub", "clicou_wifi", "abriu_cardapio"].every((t) => doHub.has(t)), [...doHub]);

  console.log("\n6. QR antigo");
  await api("POST", `/cardapio-vivo/mesas/${mesa.id}/token`, undefined, token);
  await pagina.goto(WEB + caminho, { waitUntil: "networkidle2" });
  await pagina.waitForFunction(() => document.body.innerText.includes("não vale mais"), { timeout: 15000 }).catch(() => {});
  const texto = await pagina.evaluate(() => document.body.innerText);
  checar("depois de gerar outro acesso, o link antigo explica que não vale mais", texto.includes("não vale mais"), texto.slice(0, 200));
} finally {
  await navegador.close();
  await devolverVivos(api, token, antes, cat.id);
  await api("PUT", "/unidades/1", { google_avaliacao_url: lojaAntes.google_avaliacao_url ?? null,
                                    wifi_rede: lojaAntes.wifi_rede ?? null, wifi_senha: lojaAntes.wifi_senha ?? null }, token);
  await api("PUT", `/catalogos/${cat.id}`, { situacao: "INATIVO" }, token);
  await api("DELETE", `/reservas/mesas/${mesa.id}`, undefined, token);
  await api("DELETE", `/reservas/saloes/${salao.id}`, undefined, token);
  await api("PUT", "/unidades/1/parametros", par, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const f of falhas) console.log("  -", f);
process.exit(falhas.length ? 1 : 0);
