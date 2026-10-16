/**
 * Os anúncios do Cardápio Vivo (121, fase 1): o ritmo da casa no feed, a etiqueta, o botão, a
 * medição, as aberturas de seção configuráveis, a tela dos anúncios e o relatório.
 *
 * 🔑 Pedido do dono (16/10/2026): anúncios da casa ou de outra marca no meio do cardápio, "nada
 * pesado, algo orgânico", e um relatório para apresentar ao parceiro.
 * O cenário é montado pela API (Cardápios Vivos pelo link, sem tocar no principal da loja), com
 * um ritmo curto para caber em 8 pratos, e sai no fim — as regras da casa voltam a ser as de antes.
 *
 *    node scripts/verificar-anuncios-feed.mjs     (API na 9200 e o Next na 3100 de pé)
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
const { dados: antes } = await api("GET", "/cardapio-vivo/anuncios", undefined, token);
const regrasAntes = antes.regras;

async function produto(nome, preco) {
  const { dados: p } = await api("POST", "/produtos", { nome: `${nome} ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", controla_estoque: false }, token);
  const { dados: atual } = await api("GET", `/produtos/${p.id}`, undefined, token);
  await api("PUT", `/produtos/${p.id}`, { ...atual, integrado_pdv: true, preco_venda: preco }, token);
  return p.id;
}

console.log("0. cenário: um cardápio de 8 pratos, um catálogo de data especial e dois anúncios");
const { dados: cat } = await api("POST", "/catalogos", { nome: `Anuncio ${MARCA}`, origem: "PRODUTOS", situacao: "ATIVO" }, token);
const { dados: esp } = await api("POST", "/catalogos", { nome: `Especial ${MARCA}`, origem: "PRODUTOS", situacao: "ATIVO" }, token);
const { dados: g } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Pratos" }, token);
const { dados: ge } = await api("POST", `/catalogos/${esp.id}/categorias`, { nome: "Para dois" }, token);
const corpo = new FormData();
corpo.append("arquivo", new Blob([FOTO], { type: "image/png" }), "pratos.png");
await fetch(`${API}/catalogos/secoes/categoria/${g.id}/foto`, { method: "POST", body: corpo, headers: { Authorization: `Bearer ${token}` } });
for (let n = 1; n <= 8; n++) await api("POST", `/catalogos/categorias/${g.id}/itens`, { id_produto: await produto(`ANUNCIO PRATO ${n}`, 30 + n) }, token);
await api("POST", `/catalogos/categorias/${ge.id}/itens`, { id_produto: await produto("ANUNCIO FONDUE", 120) }, token);
const SLUG = `anuncio-${MARCA}`;
const SLUG_ESP = `especial-${MARCA}`;
await api("PUT", `/cardapio-vivo/vivos/${cat.id}`, { slug: SLUG }, token);
await api("PUT", `/cardapio-vivo/vivos/${esp.id}`, { slug: SLUG_ESP }, token);
await api("PUT", "/cardapio-vivo/anuncios/regras", { anuncio_depois_de: 2, anuncio_intervalo: 3, anuncio_maximo: 2, anuncio_maximo_mesa: 1 }, token);
const { dados: daCasa } = await api("POST", "/cardapio-vivo/anuncios", { nome: `Especial ${MARCA}`, origem: "CASA",
  titulo: `Data especial ${MARCA}`, texto: "Fondue para dois.", acao: "CATALOGO", acao_catalogo: esp.id, cardapios: [cat.id] }, token);
const { dados: externo } = await api("POST", "/cardapio-vivo/anuncios", { nome: `Cerveja ${MARCA}`, origem: "EXTERNO",
  anunciante: "Cervejaria X", titulo: `Cerveja ${MARCA}`, acao: "LINK", acao_url: "https://exemplo.com.br/", cardapios: [cat.id] }, token);
checar("o cenário existe", daCasa?.id && externo?.id, [daCasa, externo]);

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
  const abrir = async () => {
    await p.goto(`${WEB}/c/1?cardapio=${SLUG}`, { waitUntil: "networkidle2" });
    await p.waitForFunction(() => document.querySelector("[data-pos]") || document.body.innerText.includes("Ver cardápio"), { timeout: 20000 }).catch(() => {});
    await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Ver cardápio")?.click());
    await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Entendi")?.click());
    await p.waitForSelector("[data-pos]", { timeout: 15000 }).catch(() => {});
    return p.$$eval("[data-pos]", (els) => els.map((e) =>
      e.dataset.anuncio ? `anuncio:${e.dataset.anuncio}` : e.classList.contains("cv-item") ? "prato" : e.dataset.cartao ? "cartao" : "secao"));
  };

  console.log("\n1. o ritmo: o 1º depois do 2º prato, 3 pratos entre eles, no máximo 2");
  const ordem = await abrir();
  const forma = ordem.map((x) => (x.startsWith("anuncio") ? "A" : x === "prato" ? "P" : "S")).join("");
  checar("a sequência é abertura, P P, anúncio, P P P, anúncio, P P P", forma === "SPPAPPPAPPP", { forma, ordem });
  const anuncios = ordem.filter((x) => x.startsWith("anuncio"));
  checar("e os dois anúncios são diferentes", new Set(anuncios).size === 2, anuncios);
  const deNovo = await abrir();
  checar("a mesma visita vê a mesma ordem (o sorteio é da sessão)", JSON.stringify(deNovo) === JSON.stringify(ordem), { ordem, deNovo });

  console.log("\n2. a etiqueta e o botão");
  const texto = async (id) => p.$eval(`[data-anuncio='${id}']`, (e) => e.innerText);
  const ext = await texto(externo.id);
  checar("o de outra marca diz 'Patrocinado · Cervejaria X'", /patrocinado · cervejaria x/i.test(ext), ext);
  const casa = await texto(daCasa.id);
  checar("o da casa diz 'Da casa', com o botão do cardápio", /da casa/i.test(casa) && casa.includes("Ver o cardápio"), casa);
  await p.$eval(`[data-anuncio='${daCasa.id}']`, (e) => e.scrollIntoView());
  await esperar(900);
  await Promise.all([
    p.waitForNavigation({ waitUntil: "networkidle2", timeout: 20000 }).catch(() => {}),
    p.evaluate((id) => [...document.querySelectorAll(`[data-anuncio='${id}'] button`)].find((b) => b.textContent.includes("Ver o cardápio"))?.click(), daCasa.id),
  ]);
  checar("o botão leva ao Cardápio Vivo do catálogo anunciado", p.url().includes(`cardapio=${SLUG_ESP}`), p.url());
  const tipos = [];
  for (const t of await p.evaluate(() => window.__lotes)) {
    try { JSON.parse(t).eventos.forEach((e) => tipos.push(`${e.tipo}:${e.anuncio ?? ""}`)); } catch { /* lote ilegível */ }
  }
  // ⚠️ Os lotes da página anterior foram copiados ANTES de navegar; aqui a página é nova, então
  // a conferência é no servidor.
  const { dados: lista } = await api("GET", "/cardapio-vivo/anuncios", undefined, token);
  const m = lista.anuncios.find((a) => a.id === daCasa.id);
  checar("o servidor contou a aparição e o toque do anúncio da casa", m.aparicoes >= 1 && m.toques >= 1, { m, tipos });

  console.log("\n3. as aberturas de seção configuráveis");
  await api("PUT", `/cardapio-vivo/vivos/${cat.id}`, { slug: SLUG, aberturas: "NUNCA" }, token);
  const semAbertura = await abrir();
  checar("com 'Nenhuma', a seção com foto não abre", !semAbertura.includes("secao") && semAbertura[0] === "prato", semAbertura);

  console.log("\n4. a tela dos anúncios e o relatório");
  const e = await navegador.newPage();
  await e.setViewport({ width: 1366, height: 1000 });
  await e.goto(WEB + "/login");
  await e.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  await e.goto(`${WEB}/cardapio-vivo/anuncios`, { waitUntil: "networkidle2" });
  await e.waitForSelector(`[data-anuncio-linha='${externo.id}']`, { timeout: 20000 }).catch(() => {});
  const tela = await e.evaluate(() => document.body.innerText);
  checar("a tela mostra o ritmo e os anúncios", tela.includes("O ritmo dos anúncios") && tela.includes(`Cerveja ${MARCA}`)
    && (await e.$eval("#regra-anuncio_depois_de", (i) => i.value)) === "2", tela.slice(0, 300));
  await e.click("#anuncio-novo");
  await e.waitForSelector("#anuncio-nome", { timeout: 5000 });
  await e.type("#anuncio-nome", `Novo ${MARCA}`);
  await e.type("#anuncio-titulo", "Sobremesa do dia");
  await e.click("#anuncio-gravar");
  await e.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent === "Pôr vídeo"), { timeout: 10000 }).catch(() => {});
  checar("criar deixa a janela aberta, já com foto e vídeo",
    await e.evaluate(() => [...document.querySelectorAll("button")].some((b) => b.textContent === "Pôr vídeo")));
  await e.goto(`${WEB}/cardapio-vivo/anuncios/${daCasa.id}/relatorio`, { waitUntil: "networkidle2" });
  await e.waitForFunction(() => document.body.innerText.includes("Pessoas que viram"), { timeout: 20000 }).catch(() => {});
  const rel = await e.evaluate(() => document.body.innerText);
  checar("o relatório abre, com as pessoas, a taxa de toque e o dia a dia",
    rel.includes("Pessoas que viram") && rel.includes("Taxa de toque") && rel.includes("Dia a dia")
    && rel.includes("Imprimir / salvar em PDF"), rel.slice(0, 400));
} finally {
  await navegador.close();
  const { dados: agora } = await api("GET", "/cardapio-vivo/anuncios", undefined, token);
  for (const a of agora.anuncios.filter((x) => x.nome.includes(MARCA))) await api("DELETE", `/cardapio-vivo/anuncios/${a.id}`, undefined, token);
  await api("PUT", "/cardapio-vivo/anuncios/regras", regrasAntes, token);
  await api("DELETE", `/cardapio-vivo/vivos/${cat.id}`, undefined, token);
  await api("DELETE", `/cardapio-vivo/vivos/${esp.id}`, undefined, token);
  await api("PUT", `/catalogos/${cat.id}`, { situacao: "INATIVO" }, token);
  await api("PUT", `/catalogos/${esp.id}`, { situacao: "INATIVO" }, token);
  await api("PUT", "/unidades/1/parametros", par, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((f) => console.log(`  - ${f}`));
process.exit(falhas.length ? 1 : 0);
