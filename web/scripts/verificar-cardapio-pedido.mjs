/**
 * Cardápio Vivo, fase 2 (migração 115), no navegador: o cliente pede pela mesa (com um
 * adicional obrigatório) e chama o garçom; a equipe vê os dois no Painel de pedidos e marca o
 * chamado como atendido; o painel Atenção × Vendas abre com os números.
 *
 * 🔑 Pedido do dono (14/10/2026) — ver `docs/cardapio-vivo-estudo.md`.
 * O cenário é montado pela API; no fim o catálogo vira INATIVO, a mesa e o salão saem, e a
 * configuração da loja volta. ⚠️ O pedido de teste FICA (pedido não se apaga pela rota).
 *
 *    node scripts/verificar-cardapio-pedido.mjs     (API na 9200 e web na 3100 de pé)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
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
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), "X-Unidade": "1" },
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

async function produto(nome, preco) {
  const { dados: p } = await api("POST", "/produtos", { nome: `${nome} ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", controla_estoque: false }, token);
  const { dados: atual } = await api("GET", `/produtos/${p.id}`, undefined, token);
  await api("PUT", `/produtos/${p.id}`, { ...atual, integrado_pdv: true, preco_venda: preco }, token);
  return p.id;
}

console.log("0. cenário: modo PEDIDO, um prato com adicional obrigatório, chamar garçom ligado");
const { dados: cat } = await api("POST", "/catalogos", { nome: `Pedido tela vivo ${MARCA}`, origem: "PRODUTOS", situacao: "ATIVO" }, token);
const { dados: g } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Pratos" }, token);
const risoto = await produto("PEDE RISOTO", 58);
await api("POST", `/catalogos/categorias/${g.id}/itens`, { id_produto: risoto }, token);
await api("PUT", `/produtos/${risoto}/adicionais`, [{ nome: "Ponto", minimo: 1, maximo: 1,
  opcoes: [{ nome: "Al dente" }, { nome: "Macio" }] }], token);
const { dados: salao } = await api("POST", "/reservas/saloes", { nome: `Pede ${MARCA}` }, token);
const { dados: mesa } = await api("POST", "/reservas/mesas", { id_salao: salao.id, nome: "P1", lugares: 2 }, token);
await api("PUT", "/cardapio-vivo/config", { ...antes.config, id_catalogo: cat.id, modo: "PEDIDO",
                                            exige_confirmacao: true, chamar_garcom: true,
                                            pedido_hora_de: null, pedido_hora_ate: null }, token);
const { dados: acesso } = await api("GET", "/cardapio-vivo/mesas", undefined, token);
const caminho = new URL(acesso.mesas.find((m) => m.id === mesa.id).link).pathname;

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
const clicarTexto = (pagina, texto, escopo = "button") =>
  pagina.evaluate((texto, escopo) => {
    const b = [...document.querySelectorAll(escopo)].find((x) => x.textContent.trim().includes(texto));
    b?.click();
    return !!b;
  }, texto, escopo);
try {
  const pagina = await navegador.newPage();
  await pagina.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
  const erros = [];
  pagina.on("pageerror", (e) => erros.push(e.message));
  await pagina.evaluateOnNewDocument(() => localStorage.setItem("cardapio.aviso_cookies", "1"));

  console.log("\n1. o cliente pede pela mesa");
  await pagina.goto(WEB + caminho, { waitUntil: "networkidle2" });
  await pagina.waitForSelector(".cv-item", { timeout: 20000 });
  const botao = await pagina.$eval(".cv-item", (s) => s.innerText);
  checar("no modo PEDIDO, o botão é 'Adicionar ao pedido'", botao.includes("Adicionar ao pedido"), botao);
  checar("e o topo tem o carrinho e o 'Chamar'",
         await pagina.evaluate(() => [...document.querySelectorAll("header button")].some((b) => b.textContent.includes("🛒"))
                                     && [...document.querySelectorAll("header button")].some((b) => b.textContent.includes("Chamar"))));
  await clicarTexto(pagina, "Adicionar ao pedido");
  await pagina.waitForSelector('[role="dialog"]');
  const desligado = await pagina.$eval('[role="dialog"] button.flex-1', (b) => b.disabled);
  checar("prato com escolha obrigatória: o detalhe abre e não deixa adicionar antes de escolher", desligado);
  await clicarTexto(pagina, "Al dente", '[role="dialog"] label');
  // ⚠️ O botão do DIÁLOGO: o do prato, atrás dele, tem o mesmo texto.
  await pagina.$eval('[role="dialog"] button.flex-1', (b) => b.click());
  await esperar(300);
  const cart = await pagina.$$eval("header button", (bs) => bs.find((b) => b.textContent.includes("🛒"))?.textContent);
  checar("o carrinho conta 1", cart?.trim() === "🛒 1", cart);
  await pagina.evaluate(() => [...document.querySelectorAll("header button")].find((b) => b.textContent.includes("🛒")).click());
  await pagina.waitForSelector('[role="dialog"][aria-label="Meu pedido"]');
  const tela = await pagina.$eval('[role="dialog"][aria-label="Meu pedido"]', (d) => d.innerText);
  checar("a tela do pedido mostra o prato, a escolha e o pagamento no caixa",
         tela.includes("PEDE RISOTO") && tela.includes("Al dente") && tela.includes("caixa"), tela);
  checar("e oferece somar na fidelidade (opcional)", tela.includes("Somar na fidelidade"), tela);
  await clicarTexto(pagina, "Enviar pedido");
  await pagina.waitForFunction(() => document.body.innerText.includes("aguardando a casa confirmar"), { timeout: 15000 }).catch(() => {});
  const depois = await pagina.evaluate(() => document.body.innerText);
  checar("enviado, o cliente acompanha: 'aguardando a casa confirmar'", depois.includes("aguardando a casa confirmar"), depois.slice(0, 300));
  const zerado = await pagina.$$eval("header button", (bs) => bs.find((b) => b.textContent.includes("🛒"))?.textContent);
  checar("e o carrinho esvazia", zerado?.trim() === "🛒 0", zerado);
  await pagina.evaluate(() => document.querySelector('[aria-label="Meu pedido"] button[aria-label="Fechar"]').click());

  console.log("\n2. chamar o garçom");
  await clicarTexto(pagina, "Chamar");
  await clicarTexto(pagina, "Chamar o garçom", '[role="menuitem"]');
  await pagina.waitForSelector('p[role="status"]', { timeout: 10000 }).catch(() => {});
  const recado = await pagina.$eval('p[role="status"]', (p) => p.textContent).catch(() => "");
  checar("o cliente vê que o garçom já vem", /garçom já vem/.test(recado), recado);
  checar("nenhum erro de JavaScript no feed", erros.length === 0, erros);

  console.log("\n3. a equipe vê no Painel de pedidos");
  const equipe = await navegador.newPage();
  await equipe.setViewport({ width: 1400, height: 1000 });
  await equipe.goto(WEB + "/login");
  await equipe.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                        login.access_token, login.refresh_token);
  await equipe.goto(WEB + "/pedidos/painel", { waitUntil: "networkidle2" });
  await equipe.waitForFunction(() => document.body.innerText.includes("Mesas"), { timeout: 15000 }).catch(() => {});
  const painel = await equipe.evaluate(() => document.body.innerText);
  checar("a coluna Mesas tem o pedido da mesa P1", painel.includes("Mesas") && painel.includes("Mesa P1"), painel.slice(0, 400));
  checar("e o chamado aparece no topo", painel.includes("Garçom · Mesa P1"), painel.slice(0, 400));
  await clicarTexto(equipe, "atendido");
  await esperar(1500);
  const semChamado = await equipe.evaluate(() => document.body.innerText);
  checar("'atendido' tira o chamado do topo", !semChamado.includes("Garçom · Mesa P1"));

  console.log("\n4. o painel Atenção × Vendas");
  await equipe.goto(WEB + "/cardapio-vivo/atencao", { waitUntil: "networkidle2" });
  await equipe.waitForFunction(() => document.body.innerText.includes("Sessões engajadas"), { timeout: 20000 }).catch(() => {});
  const at = await equipe.evaluate(() => document.body.innerText);
  checar("abre com os números do topo e o funil", at.includes("Sessões engajadas") && at.includes("Funil da sessão"), at.slice(0, 300));
  checar("lista os pratos do cardápio", at.includes("PEDE RISOTO"), at.slice(0, 600));
  checar("e explica as métricas", at.includes("O que cada número quer dizer"));
} finally {
  await navegador.close();
  await api("PUT", "/cardapio-vivo/config", antes.config, token);
  await api("PUT", `/catalogos/${cat.id}`, { situacao: "INATIVO" }, token);
  await api("DELETE", `/reservas/mesas/${mesa.id}`, undefined, token);
  await api("DELETE", `/reservas/saloes/${salao.id}`, undefined, token);
  await api("PUT", "/unidades/1/parametros", par, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const f of falhas) console.log("  -", f);
process.exit(falhas.length ? 1 : 0);
