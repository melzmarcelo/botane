/**
 * O site do cliente em três idiomas (porta 3200): o seletor PT · EN · DE, os textos da tela
 * no idioma escolhido, o cardápio com a tradução do servidor e o PORTUGUÊS onde ela faltar.
 *
 * 🔑 Pedido do dono (29/09/2026): "Claude Haiku, categorias também e o site nos três idiomas".
 * A tradução do cardápio é gravada à mão pela API (nenhuma chamada à Anthropic sai daqui).
 * O catálogo de teste é INATIVADO no fim.
 *
 *    node scripts/verificar-idioma-site.mjs     (API na 9200 e site na 3200 de pé)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const API = "http://127.0.0.1:9200";
const SITE = "http://127.0.0.1:3200";
const MARCA = String(Date.now()).slice(-6);
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};

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

console.log("0. cenário: um cardápio com o nome e um prato traduzidos, e a categoria sem inglês");
const NOME_CAT = `Idioma ${MARCA}`;
const { dados: cat } = await api("POST", "/catalogos", { nome: NOME_CAT, origem: "PRODUTOS", situacao: "ATIVO" }, token);
const { dados: g } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: `Salgados ${MARCA}` }, token);
const { dados: p } = await api("POST", "/produtos", { nome: `PAO QUEIJO IDIOMA ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", controla_estoque: false }, token);
const { dados: atual } = await api("GET", `/produtos/${p.id}`, undefined, token);
await api("PUT", `/produtos/${p.id}`, { ...atual, integrado_pdv: true, preco_venda: 8, nome_catalogo: "Pão de queijo" }, token);
await api("POST", `/catalogos/categorias/${g.id}/itens`, { id_produto: p.id }, token);
await api("PUT", `/traducao/catalogo/${cat.id}`, { en: { nome: `Language ${MARCA}` }, de: { nome: `Sprache ${MARCA}` } }, token);
await api("PUT", `/traducao/produto/${p.id}`, { en: { nome: "Cheese bread" }, de: { nome: "Käsebrot" } }, token);
await api("PUT", `/traducao/categoria/${g.id}`, { de: { nome: "Herzhaftes" } }, token);

const navegador = await puppeteer.launch({
  executablePath: CHROME, headless: "new", userDataDir: "scripts/_chrome-perfil-site",
  args: ["--no-sandbox", "--lang=pt-BR"], defaultViewport: { width: 420, height: 900 },
});
const texto = (pg, sel) => pg.$eval(sel, (e) => e.textContent.trim());
try {
  const pg = await navegador.newPage();
  await pg.goto(`${SITE}/?loja=1`, { waitUntil: "networkidle2" });
  await pg.waitForSelector(`#itens [data-catalogo="${cat.id}"]`, { timeout: 15000 });

  console.log("\n1. em português, o padrão");
  checar("o seletor mostra PT · EN · DE", (await pg.$$eval("#idiomas button", (bs) => bs.map((b) => b.textContent))).join() === "PT,EN,DE");
  checar("PT marcado", await pg.$eval('#idiomas [data-idioma="pt"]', (b) => b.getAttribute("aria-pressed")) === "true");
  checar("o botão da reserva em português", await texto(pg, "#ir-reservar") === "Reserve sua Mesa");
  checar("o catálogo com o nome em português", await texto(pg, `#itens [data-catalogo="${cat.id}"]`) === NOME_CAT);

  console.log("\n2. trocar para inglês");
  await Promise.all([pg.waitForNavigation({ waitUntil: "networkidle2" }), pg.click('#idiomas [data-idioma="en"]')]);
  await pg.waitForSelector(`#itens [data-catalogo="${cat.id}"]`, { timeout: 15000 });
  checar("EN marcado depois de recarregar", await pg.$eval('#idiomas [data-idioma="en"]', (b) => b.getAttribute("aria-pressed")) === "true");
  checar("<html lang> acompanha", await pg.$eval("html", (h) => h.lang) === "en-GB");
  checar("o botão da reserva em inglês", await texto(pg, "#ir-reservar") === "Book a table");
  checar("o nome do catálogo vem traduzido do servidor", await texto(pg, `#itens [data-catalogo="${cat.id}"]`) === `Language ${MARCA}`);
  const estado = await texto(pg, "#estado");
  checar("a tarja de aberto/fechado em inglês", /^(Open now|Closed today|Closed · opens )/.test(estado), estado);
  checar("placeholder traduzido", await pg.$eval("#observacao", (e) => e.placeholder) === "Birthday, high chair, dietary restrictions…");

  await pg.click(`#itens [data-catalogo="${cat.id}"]`);
  await pg.waitForSelector(".acessar", { visible: true, timeout: 15000 });
  checar("o título do cardápio traduzido", await texto(pg, "#t-cardapio") === `Language ${MARCA}`);
  checar("o texto que o JavaScript desenha também ('Open ›')", await texto(pg, ".acessar") === "Open ›");
  checar("🔑 a categoria sem inglês cai no PORTUGUÊS", await texto(pg, ".secao h3") === `Salgados ${MARCA}`);
  await pg.click(".acessar");
  await pg.waitForSelector(".prato .nome", { visible: true, timeout: 10000 });
  checar("o prato em inglês", await texto(pg, ".prato .nome") === "Cheese bread");
  checar("o voltar em inglês", await texto(pg, '[data-tela="secao"] .voltar') === "‹ menu");

  console.log("\n3. alemão");
  await pg.goto(`${SITE}/?loja=1`, { waitUntil: "networkidle2" });
  await Promise.all([pg.waitForNavigation({ waitUntil: "networkidle2" }), pg.click('#idiomas [data-idioma="de"]')]);
  await pg.waitForSelector(`#itens [data-catalogo="${cat.id}"]`, { timeout: 15000 });
  checar("o botão da reserva em alemão", await texto(pg, "#ir-reservar") === "Tisch reservieren");
  await pg.click(`#itens [data-catalogo="${cat.id}"]`);
  await pg.waitForSelector(".secao h3", { visible: true, timeout: 15000 });
  checar("a categoria com o alemão corrigido à mão", await texto(pg, ".secao h3") === "Herzhaftes");
  await pg.click(".acessar");
  await pg.waitForSelector(".prato .nome", { visible: true, timeout: 10000 });
  checar("o prato em alemão", await texto(pg, ".prato .nome") === "Käsebrot");
  checar("o preço no formato alemão", /^8,00$/.test(await texto(pg, ".prato .preco")));

  console.log("\n4. de volta ao português");
  await pg.goto(`${SITE}/?loja=1`, { waitUntil: "networkidle2" });
  await Promise.all([pg.waitForNavigation({ waitUntil: "networkidle2" }), pg.click('#idiomas [data-idioma="pt"]')]);
  await pg.waitForSelector(`#itens [data-catalogo="${cat.id}"]`, { timeout: 15000 });
  checar("tudo em português de novo", await texto(pg, "#ir-reservar") === "Reserve sua Mesa"
    && await texto(pg, `#itens [data-catalogo="${cat.id}"]`) === NOME_CAT);
} finally {
  await navegador.close();
  await api("PUT", `/catalogos/${cat.id}`, { situacao: "INATIVO" }, token);
  await api("PUT", "/unidades/1/parametros", { reservas_ligado: par.reservas_ligado }, token);
}
console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const f of falhas) console.log("  -", f);
process.exit(falhas.length ? 1 : 0);
