/**
 * "Monte sua cesta" com a embalagem de graça (migração 150) no navegador: cadastro, mesa e site.
 *
 * 🔑 Pedido do dono (06/11/2026): *"opção de Não cobrar o item, aí este preço não é apresentado. E
 * o valor do item selecionado não aparecer na seleção, e sim quando listar os itens a escolher, a
 * embalagem selecionada já vir marcada, não podendo desmarcar, e este item não contabiliza no
 * mínimo e máximo"* — e a embalagem sai de graça. Confere: a chave no "+ item de escolha" grava;
 * no feed e no site a cesta não mostra preço, as opções também não, e a embalagem escolhida vem
 * marcada e travada no topo dos itens; o total é só o dos itens.
 * O cenário é montado pela API e sai no fim (o catálogo é inativado e deixa de ser Vivo).
 *
 *    node scripts/verificar-cesta-nao-cobrar.mjs     (API na 9200 e o Next na 3100 de pé)
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
const { dados: par } = await api("GET", "/unidades/1/parametros", undefined, token);
await api("PUT", "/unidades/1/parametros", { ...par, reservas_ligado: true }, token);

async function produto(nome, preco) {
  const { dados: p } = await api("POST", "/produtos", { nome: `${nome} ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", controla_estoque: false }, token);
  const { dados: atual } = await api("GET", `/produtos/${p.id}`, undefined, token);
  await api("PUT", `/produtos/${p.id}`, { ...atual, integrado_pdv: true, preco_venda: preco }, token);
  return p.id;
}

console.log("0. cenário: Cesta Grande (40) e Média (30), itens Geleia (12) e Pão (8), de 2 a 3");
const GRANDE = await produto("NCB GRANDE", 40), MEDIA = await produto("NCB MEDIA", 30);
const GELEIA = await produto("NCB GELEIA", 12), PAO = await produto("NCB PAO", 8);
for (const c of [GRANDE, MEDIA])
  await api("PUT", `/produtos/${c}/adicionais`, [
    { nome: "Itens da cesta", minimo: 2, maximo: 3, permite_repetir: true,
      opcoes: [{ nome: "Geleia", id_produto_ref: GELEIA }, { nome: "Pão", id_produto_ref: PAO }] }], token);
const { dados: cat } = await api("POST", "/catalogos", { nome: `Cesta gratis ${MARCA}`, origem: "PRODUTOS", situacao: "ATIVO" }, token);
const { dados: g } = await api("POST", `/catalogos/${cat.id}/categorias`, { nome: "Presentes" }, token);
await api("PUT", `/pedidos/config/${cat.id}`, {
  aceita: true, retirada: true, entrega: false, taxa_entrega: 0, pedido_minimo: 0,
  antecedencia_min: 30, antecedencia_max_dias: 7, pagamentos: ["RETIRADA"], texto_pagamento: null,
}, token);
const SLUG = `cesta-${MARCA}`;
await api("PUT", `/cardapio-vivo/vivos/${cat.id}`, { slug: SLUG }, token);

const navegador = await puppeteer.launch({
  executablePath: CHROME, headless: "new", userDataDir: "scripts/_chrome-perfil-site",
  args: ["--no-sandbox"], defaultViewport: { width: 1280, height: 900 },
});
let idCesta = null;
try {
  const p = await navegador.newPage();
  const erros = [];
  p.on("pageerror", (e) => erros.push(e.message));

  console.log("\n1. o cadastro: a chave 'Não cobrar' no + item de escolha");
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  await p.goto(`${WEB}/catalogos/${cat.id}?aba=cardapio`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#nova-escolha", { timeout: 20000 }).catch(() => {});
  await p.click("#nova-escolha");
  await p.waitForSelector("#escolha-nome", { timeout: 8000 }).catch(() => {});
  await p.type("#escolha-nome", "Monte sua cesta");
  for (const [busca, rotulo] of [[`NCB GRANDE ${MARCA}`, "Grande"], [`NCB MEDIA ${MARCA}`, "Média"]]) {
    await p.type("#escolha-busca", busca);
    await p.waitForFunction((b) => [...document.querySelectorAll('[role="dialog"] button')]
      .some((x) => x.textContent.includes(b) && x.textContent.includes("+ pôr")), { timeout: 8000 }, busca).catch(() => {});
    await p.evaluate((b) => [...document.querySelectorAll('[role="dialog"] button')]
      .find((x) => x.textContent.includes(b) && x.textContent.includes("+ pôr"))?.click(), busca);
    await p.waitForSelector(`input[aria-label="rótulo de ${busca}"]`, { timeout: 5000 }).catch(() => {});
    await p.type(`input[aria-label="rótulo de ${busca}"]`, rotulo);
  }
  checar("a janela tem a chave 'Não cobrar a opção escolhida', desligada",
    await p.$eval("#escolha-nao-cobrar", (c) => c.getAttribute("role") === "switch" && !c.checked).catch(() => false));
  await p.$eval("#escolha-nao-cobrar", (c) => c.click());
  await p.click("#escolha-criar");
  await esperar(1500);
  const { dados: ct } = await api("GET", `/catalogos/${cat.id}/conteudo`, undefined, token);
  const it = ct.categorias.flatMap((c) => c.itens).find((i) => i.tipo === "ESCOLHA");
  idCesta = it?.id;
  checar("criada com a marca gravada", it?.nao_cobrar === true, it);
  await p.waitForSelector("#escolha-nao-cobrar-gaveta", { timeout: 8000 }).catch(() => {});
  checar("e a gaveta que abre mostra a chave ligada",
    await p.$eval("#escolha-nao-cobrar-gaveta", (c) => c.checked).catch(() => false));

  console.log("\n2. a mesa (feed): sem preço, e a embalagem travada nos itens");
  await p.setViewport({ width: 420, height: 900 });
  await p.goto(`${WEB}/c/1?cardapio=${SLUG}`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => document.body.innerText.includes("Monte sua cesta")
    || document.body.innerText.includes("Ver cardápio"), { timeout: 20000 }).catch(() => {});
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Ver cardápio")?.click());
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "Entendi")?.click());
  await p.waitForFunction(() => document.body.innerText.includes("Monte sua cesta"), { timeout: 15000 }).catch(() => {});
  const cartao = await p.evaluate(() => [...document.querySelectorAll("section")]
    .find((s) => s.innerText.includes("Monte sua cesta"))?.innerText ?? "");
  checar("o cartão da cesta não mostra preço", cartao && !/R\$|a partir de/i.test(cartao), cartao);
  await p.evaluate(() => {
    const sec = [...document.querySelectorAll("section")].find((s) => s.innerText.includes("Monte sua cesta"));
    [...(sec?.querySelectorAll("button") ?? [])].find((b) => b.textContent.includes("Adicionar"))?.click();
  });
  await p.waitForSelector('[role="dialog"][aria-label="Monte sua cesta"]', { timeout: 8000 }).catch(() => {});
  const escolha = await p.evaluate(() => document.querySelector('[role="dialog"] fieldset')?.innerText ?? "");
  checar("as opções Grande e Média aparecem sem preço", /Grande/.test(escolha) && /Média/.test(escolha)
    && !/R\$|40|30/.test(escolha), escolha);
  await p.evaluate(() => [...document.querySelectorAll('[role="dialog"] label')].find((l) => l.textContent.includes("Grande"))?.querySelector("input")?.click());
  await esperar(300);
  const fixa = await p.$eval('[role="dialog"] [data-embalagem] input', (c) => ({ marcada: c.checked, travada: c.disabled })).catch(() => null);
  checar("escolhida a Grande, ela vem marcada e travada no topo dos itens", fixa?.marcada && fixa?.travada, fixa);
  checar("com o rótulo 'incluso'", await p.$eval('[role="dialog"] [data-embalagem]', (e) => /incluso/.test(e.textContent)).catch(() => false));
  const botao = () => p.evaluate(() => {
    const b = [...document.querySelectorAll('[role="dialog"] button')].find((x) => x.textContent.includes("Adicionar à minha seleção"));
    return b ? { desligado: b.disabled, texto: b.textContent } : null;
  });
  checar("a embalagem não conta no mínimo: com 0 itens o botão segue desligado", (await botao())?.desligado === true);
  await p.click('[role="dialog"] button[aria-label="+ Geleia"]');
  await p.click('[role="dialog"] button[aria-label="+ Geleia"]');
  const b2 = await botao();
  checar("2 geleias: liga com R$ 24,00 (só os itens)", b2?.desligado === false && /24,00/.test(b2.texto), b2);

  console.log("\n3. o site: sem preço no prato e a embalagem travada na janela de montar");
  await api("DELETE", `/cardapio-vivo/vivos/${cat.id}`, undefined, token);
  await p.evaluate(() => sessionStorage.removeItem("botane.carrinho"));
  await p.goto(`${WEB}/portal?loja=1`, { waitUntil: "networkidle2" });
  await p.waitForSelector(`#itens [data-catalogo="${cat.id}"]`, { timeout: 15000 }).catch(() => {});
  await p.click(`#itens [data-catalogo="${cat.id}"]`).catch(() => {});
  await p.waitForSelector(".acessar", { visible: true, timeout: 15000 }).catch(() => {});
  await p.click(".acessar").catch(() => {});
  await p.waitForFunction(() => [...document.querySelectorAll(".prato")].some((x) => x.innerText.includes("Monte sua cesta")),
    { timeout: 15000 }).catch(() => {});
  const prato = await p.evaluate(() => {
    const pr = [...document.querySelectorAll(".prato")].find((x) => x.innerText.includes("Monte sua cesta"));
    return pr ? { preco: !!pr.querySelector(".preco"), pedir: !!pr.querySelector(".pedir button") } : null;
  });
  checar("o prato não mostra preço e tem o botão de pedir", prato && !prato.preco && prato.pedir, prato);
  await p.evaluate(() => [...document.querySelectorAll(".prato")].find((x) => x.innerText.includes("Monte sua cesta"))
    ?.querySelector(".pedir button")?.click());
  await p.waitForSelector("#montar[open]", { timeout: 5000 }).catch(() => {});
  const opcoes = await p.$eval("#corpo-montar fieldset", (f) => f.innerText).catch(() => "");
  checar("as opções sem preço", /Grande/.test(opcoes) && !/R\$/.test(opcoes), opcoes);
  await p.evaluate(() => [...document.querySelectorAll("#corpo-montar label")].find((l) => l.textContent.includes("Grande"))?.querySelector("input")?.click());
  await esperar(200);
  const fixaSite = await p.$eval("#corpo-montar [data-embalagem] input", (c) => ({ marcada: c.checked, travada: c.disabled })).catch(() => null);
  checar("a Grande vem marcada e travada no topo dos itens", fixaSite?.marcada && fixaSite?.travada, fixaSite);
  checar("e não conta no mínimo: Adicionar desligado sem itens", await p.$eval("#por-montar", (x) => x.disabled).catch(() => false));
  await p.evaluate(() => {
    const mais = [...document.querySelectorAll('#corpo-montar button[data-passo="1"]')];
    mais[0]?.click();
  });
  await p.evaluate(() => [...document.querySelectorAll('#corpo-montar button[data-passo="1"]')][0]?.click());
  const t = await p.$eval("#por-montar", (x) => ({ d: x.disabled, t: x.textContent })).catch(() => null);
  checar("2 geleias: Adicionar · R$ 24,00", t && !t.d && t.t.includes("24,00"), t);
  checar("nenhum erro de JavaScript", !erros.length, erros);
} finally {
  await navegador.close();
  await api("DELETE", `/cardapio-vivo/vivos/${cat.id}`, undefined, token);
  await api("PUT", `/catalogos/${cat.id}`, { situacao: "INATIVO" }, token);
  await api("PUT", "/unidades/1/parametros", par, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((f) => console.log(`  - ${f}`));
process.exit(falhas.length ? 1 : 0);
