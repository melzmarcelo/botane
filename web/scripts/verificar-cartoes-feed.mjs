/**
 * Os cartões de conteúdo do Cardápio Vivo (120): a abertura do cardápio, a abertura
 * automática de seção e o cartão entre os pratos — no feed e no editor.
 *
 * 🔑 Pedido do dono (16/10/2026): "um cardápio de massas, e antes postar um vídeo, texto ou
 * foto com uma introdução, bem como seções entre os pratos". Só no feed.
 * O cenário é montado pela API (um Cardápio Vivo pelo link, sem tocar no principal da loja)
 * e sai no fim.
 *
 *    node scripts/verificar-cartoes-feed.mjs     (API na 9200 e o Next na 3100 de pé)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const API = "http://127.0.0.1:9200";
const WEB = "http://127.0.0.1:3100";
const MARCA = String(Date.now()).slice(-6);
const FOTO = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAAABlBMVEX///+/v7+jQ3Y5AAAADklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5CYII=", "base64");
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
const { dados: par } = await api("GET", "/unidades/1/parametros", undefined, token);
await api("PUT", "/unidades/1/parametros", { ...par, reservas_ligado: true }, token);

async function produto(nome, preco) {
  const { dados: p } = await api("POST", "/produtos", { nome: `${nome} ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", controla_estoque: false }, token);
  const { dados: atual } = await api("GET", `/produtos/${p.id}`, undefined, token);
  await api("PUT", `/produtos/${p.id}`, { ...atual, integrado_pdv: true, preco_venda: preco }, token);
  return p.id;
}

console.log("0. cenário: um cardápio de massas com abertura, seção com foto e um cartão entre os pratos");
const { dados: cat } = await api("POST", "/catalogos", { nome: `Massas ${MARCA}`, origem: "PRODUTOS", situacao: "ATIVO" }, token);
const { dados: g } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Frescas" }, token);
const itens = [];
for (const n of ["CARTAO TALHARIM", "CARTAO PAPPARDELLE", "CARTAO RAVIOLI"]) {
  const { dados: it } = await api("POST", `/catalogos/categorias/${g.id}/itens`, { id_produto: await produto(n, 50) }, token);
  itens.push(it.id);
}
const corpo = new FormData();
corpo.append("arquivo", new Blob([FOTO], { type: "image/png" }), "frescas.png");
await fetch(`${API}/catalogos/secoes/categoria/${g.id}/foto`, { method: "POST", body: corpo, headers: { Authorization: `Bearer ${token}` } });
const { dados: abertura } = await api("POST", `/catalogos/${cat.id}/cartoes`,
  { titulo: `Massas frescas ${MARCA}`, texto: "Farinha 00 e 48 h de descanso." }, token);
const { dados: meio } = await api("POST", `/catalogos/${cat.id}/cartoes`,
  { id_categoria: g.id, antes_do_item: itens[1], titulo: "Vai bem com o Chianti", id_item_link: itens[2] }, token);
const SLUG = `massas-${MARCA}`;
const r = await api("PUT", `/cardapio-vivo/vivos/${cat.id}`, { slug: SLUG }, token);
checar("o cardápio de massas liga pelo link, com dois cartões", r.status === 200 && abertura?.id && meio?.id, r.dados);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"],
                                           defaultViewport: { width: 390, height: 844 } });
try {
  const p = await navegador.newPage();
  await p.evaluateOnNewDocument(() => {
    window.__lotes = [];
    const original = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = (url, dados) => {
      if (dados instanceof Blob) dados.text().then((t) => window.__lotes.push(t));
      return original(url, dados);
    };
  });
  console.log("\n1. o feed na ordem: abertura, seção, prato, cartão, prato, prato");
  await p.goto(`${WEB}/c/1?cardapio=${SLUG}`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => document.querySelector("[data-pos]") || document.body.innerText.includes("Ver cardápio"), { timeout: 20000 }).catch(() => {});
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Ver cardápio")?.click());
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Entendi")?.click());
  await p.waitForSelector("[data-pos]", { timeout: 15000 }).catch(() => {});
  const ordem = await p.$$eval("[data-pos]", (els) => els.map((e) =>
    e.classList.contains("cv-item") ? `prato:${e.dataset.item}` : e.dataset.cartao ? `cartao:${e.dataset.cartao}` : `secao:${e.dataset.categoria}`));
  const esperado = [`cartao:${abertura.id}`, `secao:${g.id}`, `prato:${itens[0]}`, `cartao:${meio.id}`, `prato:${itens[1]}`, `prato:${itens[2]}`];
  checar("a sequência é a esperada", JSON.stringify(ordem) === JSON.stringify(esperado), { ordem, esperado });
  const primeira = await p.$eval("[data-pos='0']", (e) => e.innerText);
  checar("a abertura mostra o título e o texto", primeira.includes(`Massas frescas ${MARCA}`) && primeira.includes("48 h"), primeira);
  const secao = await p.$eval("[data-pos='1']", (e) => e.innerText);
  checar("a abertura da seção mostra o nome dela", secao.includes("Frescas"), secao);
  const alturas = await p.$$eval("[data-pos]", (els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
  checar("cada cartão ocupa a tela inteira, como o prato", alturas.every((h) => h === 844), alturas);
  const semAdicionar = await p.$eval(`[data-cartao='${meio.id}']`, (e) => !e.innerText.includes("Adicionar"));
  checar("o cartão não tem botão de adicionar", semAdicionar);

  console.log("\n2. o 'Ver o prato'");
  await p.$eval(`[data-cartao='${meio.id}']`, (e) => e.scrollIntoView());
  await esperar(800);
  await p.evaluate((id) => [...document.querySelectorAll(`[data-cartao='${id}'] button`)].find((b) => b.textContent.includes("Ver o prato"))?.click(), meio.id);
  await esperar(1000);
  const noPrato = await p.$eval(`[data-item='${itens[2]}']`, (e) => Math.abs(e.getBoundingClientRect().top) < 5);
  checar("leva ao prato citado", noPrato);

  console.log("\n3. a medição");
  await p.$eval("[data-pos='0']", (e) => e.scrollIntoView());
  await esperar(900);
  // ⚠️ Parar NA abertura da seção: pular dela direto para o prato não é "ver" (menos de 300 ms).
  await p.$eval("[data-pos='1']", (e) => e.scrollIntoView());
  await esperar(900);
  await p.$eval("[data-pos='2']", (e) => e.scrollIntoView());
  await esperar(500);
  await p.evaluate(() => window.dispatchEvent(new Event("pagehide")));
  await esperar(400);
  const tipos = [];
  for (const t of await p.evaluate(() => window.__lotes)) {
    try { JSON.parse(t).eventos.forEach((e) => tipos.push(`${e.tipo}:${e.cartao ?? e.categoria ?? ""}`)); } catch { /* lote ilegível */ }
  }
  checar("viu_cartao (a abertura), viu_secao e clicou_cartao chegam",
    tipos.includes(`viu_cartao:${abertura.id}`) && tipos.some((x) => x.startsWith("viu_secao:")) && tipos.includes(`clicou_cartao:${meio.id}`), tipos);

  console.log("\n4. no editor");
  const e = await navegador.newPage();
  await e.setViewport({ width: 1366, height: 1000 });
  await e.goto(WEB + "/login");
  await e.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  await e.goto(`${WEB}/catalogos/${cat.id}`, { waitUntil: "networkidle2" });
  await e.waitForFunction(() => document.body.innerText.includes("Abertura no Cardápio Vivo"), { timeout: 20000 }).catch(() => {});
  const tela = await e.evaluate(() => document.body.innerText);
  checar("o editor mostra a abertura do cardápio, com o cartão dela", tela.includes("Abertura no Cardápio Vivo") && tela.includes(`Massas frescas ${MARCA}`), tela.slice(0, 300));
  const naLista = await e.evaluate((ids) => {
    const linhas = [...document.querySelectorAll("section[aria-label^='seção'] li")];
    const iCartao = linhas.findIndex((l) => l.dataset.cartaoEditor === String(ids.meio));
    return { iCartao, total: linhas.length, depois: linhas[iCartao + 1]?.innerText ?? "" };
  }, { meio: meio.id });
  checar("o cartão aparece na lista, antes do prato dele", naLista.iCartao > 0 && naLista.depois.includes("PAPPARDELLE"), naLista);
  checar("e a seção diz que abre com a foto", tela.includes("abre com a foto"));
  // 🔑 1.1.111: a atenção da abertura da seção aparece, e o período é escolhido.
  const atencao = await e.$eval("[data-abertura-atencao]", (x) => x.textContent).catch(() => "");
  checar("a seção mostra quantas vezes a abertura dela foi vista", /abertura vista \d+×/.test(atencao) && atencao.includes("30 dias"), atencao);
  const pedido90 = e.waitForResponse((r) => r.url().includes(`/catalogos/${cat.id}/cartoes?dias=90`), { timeout: 10000 }).catch(() => null);
  await e.select("#cartoes-periodo", "90");
  const r90 = await pedido90;
  await e.waitForFunction(() => document.querySelector("[data-abertura-atencao]")?.textContent?.includes("90 dias"), { timeout: 10000 }).catch(() => {});
  const atencao90 = await e.$eval("[data-abertura-atencao]", (x) => x.textContent).catch(() => "");
  checar("trocar o período para 90 dias pede de novo e a seção diz de quando é", r90?.status() === 200 && atencao90.includes("90 dias"), atencao90);
  await e.click("#novo-cartao");
  await e.waitForSelector("#cartao-titulo", { timeout: 5000 });
  await e.type("#cartao-titulo", `Cartão novo ${MARCA}`);
  await e.click("#cartao-gravar");
  await e.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent === "Pôr vídeo"), { timeout: 10000 }).catch(() => {});
  const aberta = await e.evaluate(() => [...document.querySelectorAll("button")].some((b) => b.textContent === "Pôr vídeo"));
  checar("criar deixa a janela aberta, já com foto e vídeo", aberta);
  // 🔑 16/10/2026: a correção da tradução do cartão, na mesma janela.
  await e.click("#cartao-traducoes");
  await e.waitForFunction(() => document.body.innerText.includes("Para o site em inglês e alemão"), { timeout: 10000 }).catch(() => {});
  const traducoes = await e.evaluate(() => {
    const janela = document.querySelector('[role="dialog"]')?.innerText ?? "";
    return { tem: janela.includes("Para o site em inglês e alemão"), titulo: janela.includes("Título"), ingles: janela.includes("Inglês") };
  });
  checar("o cartão abre as traduções do título, em inglês e alemão", traducoes.tem && traducoes.titulo && traducoes.ingles, traducoes);
  const { dados: lista } = await api("GET", `/catalogos/${cat.id}/cartoes`, undefined, token);
  checar("e o cartão novo está gravado, no fim da seção",
    lista.cartoes.some((c) => c.titulo === `Cartão novo ${MARCA}` && c.id_categoria === g.id && c.antes_do_item === null), lista.cartoes);
} finally {
  await navegador.close();
  await api("DELETE", `/cardapio-vivo/vivos/${cat.id}`, undefined, token);
  await api("PUT", `/catalogos/${cat.id}`, { situacao: "INATIVO" }, token);
  await api("PUT", "/unidades/1/parametros", par, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((f) => console.log(`  - ${f}`));
process.exit(falhas.length ? 1 : 0);
