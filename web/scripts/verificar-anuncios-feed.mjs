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
// ⚠️ 125: sem grupo de controle e sem o ritmo que aprende aqui — senão uma visita em dez cairia sem
// anúncio, e rolar rápido mudaria a ordem. As duas coisas têm a seção 1b.
const RITMO = { anuncio_depois_de: 2, anuncio_intervalo: 3, anuncio_maximo: 2, anuncio_maximo_mesa: 1 };
await api("PUT", "/cardapio-vivo/anuncios/regras", { ...RITMO, anuncio_controle: 0, anuncio_recuo: false }, token);
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

  console.log("\n1b. o ritmo que aprende e o grupo de controle (125)");
  await api("PUT", "/cardapio-vivo/anuncios/regras", { ...RITMO, anuncio_controle: 0, anuncio_recuo: true }, token);
  const comRecuo = await abrir();
  checar("com o recuo ligado, quem ainda não viu anúncio vê o mesmo ritmo",
    comRecuo.filter((x) => x.startsWith("anuncio")).length === 2, comRecuo);
  // Passar pelo 1º anúncio em menos de 1,5 s: a distância até o próximo dobra (3 → 6), e não sobra prato.
  const primeiro = comRecuo.findIndex((x) => x.startsWith("anuncio"));
  await p.$eval(`[data-pos='${primeiro}']`, (el) => el.scrollIntoView());
  await esperar(500);
  await p.$eval(`[data-pos='${primeiro + 1}']`, (el) => el.scrollIntoView());
  await p.waitForFunction(() => document.querySelectorAll("[data-anuncio]").length === 1, { timeout: 5000 }).catch(() => {});
  const depoisDePular = await p.$$eval("[data-anuncio]", (els) => els.length);
  checar("pulou o 1º anúncio: o 2º sai da visita (a distância dobrou)", depoisDePular === 1, depoisDePular);
  checar("e o anúncio que já passou continua onde estava",
    await p.$eval(`[data-pos='${primeiro}']`, (el) => !!el.dataset.anuncio).catch(() => false));
  await api("PUT", "/cardapio-vivo/anuncios/regras", { ...RITMO, anuncio_controle: 50, anuncio_recuo: false }, token);
  const achar = async (grupo) => {
    for (let n = 0; n < 60; n++) {
      const s = crypto.randomUUID();
      const r = await fetch(`${API}/publico/cardapio/loja/1?cardapio=${SLUG}&sessao=${s}`).then((x) => x.json());
      if (r.grupo_anuncio === grupo) return s;
    }
    return null;
  };
  const usarSessao = (s) => p.evaluate((id) => localStorage.setItem("cardapio.sessao", JSON.stringify({ id, ultimo: Date.now() })), s);
  const sControle = await achar("CONTROLE");
  await usarSessao(sControle);
  await p.evaluate(() => { window.__lotes = []; });
  const noControle = await abrir();
  checar("a visita do grupo de controle não vê anúncio nenhum", sControle && !noControle.some((x) => x.startsWith("anuncio")), noControle);
  await p.evaluate(() => window.dispatchEvent(new Event("pagehide")));
  await esperar(400);
  const gruposDoLote = (await p.evaluate(() => window.__lotes)).map((t) => { try { return JSON.parse(t).grupo_anuncio; } catch { return "?"; } });
  checar("e o lote dela vai marcado como controle", gruposDoLote.length > 0 && gruposDoLote.every((g) => g === "CONTROLE"), gruposDoLote);
  const sExposta = await achar("EXPOSTO");
  await usarSessao(sExposta);
  const naExposta = await abrir();
  checar("a exposta vê os anúncios", naExposta.some((x) => x.startsWith("anuncio")), naExposta);
  await api("PUT", "/cardapio-vivo/anuncios/regras", { ...RITMO, anuncio_controle: 0, anuncio_recuo: false }, token);

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
  // 🔑 (17/10/2026) O anúncio que não aparece diz por quê, em vez de "no ar".
  const { dados: vazioAd } = await api("POST", "/cardapio-vivo/anuncios", { nome: `Vazio ${MARCA}` }, token);
  await e.goto(`${WEB}/cardapio-vivo/anuncios`, { waitUntil: "networkidle2" });
  await e.waitForSelector(`[data-anuncio-linha='${externo.id}']`, { timeout: 20000 }).catch(() => {});
  const tela = await e.evaluate(() => document.body.innerText);
  checar("a tela mostra o ritmo e os anúncios", tela.includes("O ritmo dos anúncios") && tela.includes(`Cerveja ${MARCA}`)
    && (await e.$eval("#regra-anuncio_depois_de", (i) => i.value)) === "2", tela.slice(0, 300));
  // 🔑 125: o grupo de controle, o ritmo que aprende e o efeito.
  checar("as regras têm o grupo de controle e o ritmo que aprende",
    (await e.$("#regra-anuncio_controle")) !== null && (await e.$("#regra-anuncio_recuo")) !== null);
  checar("e a tela mostra o efeito dos anúncios, controle × expostas",
    tela.includes("O efeito dos anúncios") && ((await e.$("#efeito-anuncios")) !== null || (await e.$("#efeito-vazio")) !== null),
    tela.slice(0, 300));
  const linhaVazio = await e.$eval(`[data-anuncio-linha='${vazioAd.id}']`, (tr) => tr.innerText).catch(() => "");
  checar("o anúncio sem conteúdo aparece COM PROBLEMA, dizendo por quê",
    /com problema/i.test(linhaVazio) && /não aparece no cardápio/.test(linhaVazio), linhaVazio);
  await e.click("#anuncio-novo");
  await e.waitForSelector("#anuncio-nome", { timeout: 5000 });
  await e.type("#anuncio-nome", `Novo ${MARCA}`);
  await e.type("#anuncio-titulo", "Sobremesa do dia");
  await e.click("#anuncio-gravar");
  await e.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent === "Pôr vídeo"), { timeout: 10000 }).catch(() => {});
  checar("criar deixa a janela aberta, já com foto e vídeo",
    await e.evaluate(() => [...document.querySelectorAll("button")].some((b) => b.textContent === "Pôr vídeo")));
  // 🔑 (1.1.109) A prévia do cadastro mostra os anúncios só quando se pede.
  const contarNaPrevia = async (sufixo) => {
    await e.goto(`${WEB}/c/previa/${cat.id}${sufixo}`, { waitUntil: "networkidle2" });
    await e.waitForSelector("[data-pos]", { timeout: 20000 }).catch(() => {});
    await e.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Ver cardápio")?.click());
    await esperar(800);
    return e.$$eval("[data-anuncio]", (els) => els.length);
  };
  const semAds = await contarNaPrevia("");
  const comAds = await contarNaPrevia("?anuncios=1");
  checar("a prévia segue sem anúncio, e com '?anuncios=1' mostra os de agora", semAds === 0 && comAds > 0, { semAds, comAds });
  await e.goto(`${WEB}/cardapio-vivo/anuncios/${daCasa.id}/relatorio`, { waitUntil: "networkidle2" });
  await e.waitForFunction(() => document.body.innerText.includes("Pessoas que viram"), { timeout: 20000 }).catch(() => {});
  const rel = await e.evaluate(() => document.body.innerText);
  checar("o relatório abre, com as pessoas, a taxa de toque e o dia a dia",
    rel.includes("Pessoas que viram") && rel.includes("Taxa de toque") && rel.includes("Dia a dia")
    && rel.includes("Imprimir / salvar em PDF"), rel.slice(0, 400));
  const { dados: relApi } = await api("GET", `/cardapio-vivo/anuncios/${daCasa.id}/relatorio`, undefined, token);
  checar("e, quando foi visto, em qual cardápio (122)",
    relApi.por_cardapio.length === 0 || (await e.$("#relatorio-por-cardapio")) !== null, relApi.por_cardapio);

  // 🔑 125: a variação do texto, criada pela janela, e os textos em teste no relatório.
  await e.goto(`${WEB}/cardapio-vivo/anuncios`, { waitUntil: "networkidle2" });
  await e.waitForSelector(`[data-anuncio-linha='${externo.id}']`, { timeout: 20000 }).catch(() => {});
  await e.evaluate((id) => document.querySelector(`[data-anuncio-linha='${id}'] button`)?.click(), externo.id);
  await e.waitForSelector("#variante-nova", { timeout: 10000 }).catch(() => {});
  await e.click("#variante-nova").catch(() => {});
  await e.waitForSelector("#variante-titulo", { timeout: 5000 }).catch(() => {});
  await e.type("#variante-titulo", `Cerveja trincando ${MARCA}`).catch(() => {});
  await e.click("#variante-gravar").catch(() => {});
  await e.waitForSelector("#anuncio-variantes [data-variante]", { timeout: 10000 }).catch(() => {});
  const { dados: vsApi } = await api("GET", `/cardapio-vivo/anuncios/${externo.id}/variantes`, undefined, token);
  checar("a janela do anúncio cria uma variação do texto", vsApi.some((v) => v.titulo === `Cerveja trincando ${MARCA}`)
    && (await e.$("#anuncio-variantes [data-variante]")) !== null, vsApi);
  await e.goto(`${WEB}/cardapio-vivo/anuncios/${externo.id}/relatorio`, { waitUntil: "networkidle2" });
  await e.waitForSelector("#relatorio-variantes", { timeout: 20000 }).catch(() => {});
  const textos = await e.$eval("#relatorio-variantes", (t) => t.innerText).catch(() => "");
  checar("o relatório mostra os textos em teste, com o aplicar", /Original/.test(textos) && /Variação B/.test(textos)
    && /aplicar/.test(textos), textos.slice(0, 300));

  // A varredura dos arquivos sem dono (Administração ▸ Empresa): procurar e MOSTRAR, sem apagar.
  await e.goto(`${WEB}/empresa`, { waitUntil: "networkidle2" });
  await e.waitForSelector("#orfaos-procurar", { timeout: 20000 }).catch(() => {});
  await e.click("#orfaos-procurar").catch(() => {});
  await e.waitForFunction(() => document.querySelector("#orfaos-resultado")
    || document.body.innerText.includes("Nenhum arquivo sem dono"), { timeout: 30000 }).catch(() => {});
  const orf = await e.evaluate(() => (document.querySelector("#orfaos-resultado")?.innerText
    ?? (document.body.innerText.includes("Nenhum arquivo sem dono") ? "nenhum" : "")));
  checar("a Empresa procura os arquivos sem dono e mostra o que achou, sem apagar",
    orf === "nenhum" || (/não têm dono/.test(orf) && /Apagar os \d+/.test(orf)), orf.slice(0, 200));
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
