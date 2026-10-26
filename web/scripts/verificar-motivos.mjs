/**
 * Documentos ▸ filtro de motivo e a tela "Por motivo", no navegador.
 *
 * 🔑 Pedido do dono (26/10/2026): *"no painel de documentos filtros e quadros por
 * motivos, onde podemos realizar a impressão e comparativos"*. As contas são de
 * `api/tests/smoke_vendas_motivos.py`; aqui se confere a tela: o filtro da lista, os
 * cartões, o clique que filtra, as tabelas e o que sobra no PAPEL.
 *
 *    node scripts/verificar-motivos.mjs   (API na 9200 e web na 3100 de pé;
 *                                          BOTANE_API e BOTANE_WEB mudam as portas)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const API = process.env.BOTANE_API ?? "http://127.0.0.1:9200";
const WEB = process.env.BOTANE_WEB ?? "http://127.0.0.1:3100";
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
  const t = await r.text();
  return { status: r.status, dados: t ? JSON.parse(t) : null };
}

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;
const hoje = new Date().toLocaleDateString("sv-SE");

console.log("0. cenário: um produto a R$ 4,00, uma pessoa e três documentos com motivo");
const { dados: locais } = await api("GET", "/locais", undefined, token);
const local = (locais ?? []).find((l) => l.ativo !== false);
const { dados: prod } = await api("POST", "/produtos", {
  nome: `MOTIVO TELA ${MARCA}`, tipo: "REVENDA", um_estoque: "UN", preco_venda: 10, status: "ATIVO",
}, token);
await api("PUT", `/produtos/${prod.id}`, { id_local_padrao: local.id }, token);
await api("POST", "/estoque/entradas", {
  id_produto: prod.id, quantidade: 20, custo_unitario: 4, id_local: local.id, documento: `NF-MT-${MARCA}`,
}, token);
const { dados: pessoa } = await api("POST", "/fornecedores", { nome: `PESSOA TELA MOTIVO ${MARCA}`, fornecedor: false }, token);
const { dados: mps } = await api("GET", "/estoque/motivos-perda", undefined, token);
const docs = [
  ["MTB", 2, { motivo: "BRINDE", motivo_observacao: `aniversario ${MARCA}` }],
  ["MTP", 1, { motivo: "PERDA", id_motivo_perda: mps[0].id }],
  ["MTO", 3, { motivo: "OUTROS", motivo_observacao: "festa da equipe" }],
];
for (const [doc, quantidade, cab] of docs) {
  const r = await api("POST", "/vendas/importar", { vendas: [{
    data: hoje, documento: `${doc}-${MARCA}`, origem: "MANUAL", id_pessoa: pessoa.id,
    itens: [{ id_produto: prod.id, quantidade, valor_unitario: 10 }], ...cab }] }, token);
  checar(`lança ${doc}`, r.status === 201, r.dados);
}

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1000 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. Documentos: o filtro de motivo e o período");
  await p.goto(`${WEB}/vendas?busca=-${MARCA}&motivo=BRINDE`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#vendas-filtro-motivo", { timeout: 30000 }).catch(() => {});
  await esperar(1500);
  const lista = await p.evaluate(() => ({
    opcoes: [...document.querySelectorAll("#vendas-filtro-motivo option")].map((o) => o.value),
    docs: [...document.querySelectorAll("li")].map((l) => l.innerText).filter((t) => /MT[BPO]-/.test(t)),
    de: !!document.querySelector('input[type="date"][aria-label="De"]'),
    ate: !!document.querySelector('input[type="date"][aria-label="Até"]'),
    botao: !!document.querySelector("#vendas-por-motivo"),
  }));
  checar("o filtro oferece só vendas, qualquer motivo e cada motivo",
    ["", "VENDA", "QUALQUER", "CONSUMO_INTERNO", "PERDA", "PREMIO", "BRINDE", "OUTROS"].every((v) => lista.opcoes.includes(v)), lista.opcoes);
  checar("filtrado em Brinde, a lista traz só o brinde", lista.docs.length === 1 && lista.docs[0].includes("MTB-"), lista.docs);
  checar("o filtro de dia virou período (De e Até)", lista.de && lista.ate);
  checar("e há o botão Por motivo", lista.botao);

  console.log("\n2. a tela Por motivo");
  const base = `${WEB}/vendas/motivos?modo=periodo&de=${hoje}&ate=${hoje}&pessoa=${pessoa.id}&pessoa_nome=${encodeURIComponent(pessoa.nome ?? "")}`;
  await p.goto(base, { waitUntil: "networkidle2" });
  await p.waitForSelector("#motivos-cartoes", { timeout: 30000 }).catch(() => {});
  await esperar(800);
  const tela = await p.evaluate(() => {
    const cartao = (m) => document.querySelector(`[data-cartao-motivo="${m}"]`)?.innerText ?? "";
    return {
      total: cartao("TOTAL"), brinde: cartao("BRINDE"), perda: cartao("PERDA"), outros: cartao("OUTROS"),
      docs: document.querySelector("#motivos-documentos")?.innerText ?? "",
      produtos: document.querySelector("#motivos-produtos")?.innerText ?? "",
      pessoas: document.querySelector("#motivos-pessoas")?.innerText ?? "",
      perdaMotivo: !!document.querySelector("#motivos-perda"),
      imprimir: !!document.querySelector("#motivos-imprimir"),
      perdasAjuste: !!document.querySelector("#motivos-perdas-ajuste"),
    };
  });
  checar("o total é o custo que saiu: 6 × R$ 4 = R$ 24", /24,00/.test(tela.total), tela.total);
  checar("cada motivo no seu cartão (brinde 8, perda 4, outros 12)",
    /8,00/.test(tela.brinde) && /4,00/.test(tela.perda) && /12,00/.test(tela.outros), [tela.brinde, tela.perda, tela.outros]);
  checar("os documentos vêm com a observação", tela.docs.includes(`aniversario ${MARCA}`) && tela.docs.includes("festa da equipe"), tela.docs.slice(0, 300));
  checar("os quadros de produto, pessoa e motivo da perda aparecem",
    tela.produtos.includes(`MOTIVO TELA ${MARCA}`) && tela.pessoas.includes(`PESSOA TELA MOTIVO ${MARCA}`) && tela.perdaMotivo);
  checar("com a pessoa filtrada, a perda de Ajustes não vem como referência", !tela.perdasAjuste);
  checar("e há o botão Imprimir", tela.imprimir);

  console.log("\n3. clicar no cartão filtra pelo motivo");
  await p.click('[data-cartao-motivo="OUTROS"]');
  await p.waitForFunction(() => location.search.includes("motivos=OUTROS"), { timeout: 10000 }).catch(() => {});
  await esperar(1500);
  const filtrado = await p.evaluate(() => ({
    url: location.search,
    total: document.querySelector('[data-cartao-motivo="TOTAL"]')?.innerText ?? "",
    brinde: !!document.querySelector('[data-cartao-motivo="BRINDE"]'),
    marcado: document.querySelector('#motivos-escolha input[data-motivo="OUTROS"]')?.checked,
  }));
  checar("o total vira o de Outros (R$ 12) e os outros cartões somem",
    /12,00/.test(filtrado.total) && !filtrado.brinde && filtrado.marcado, filtrado);

  console.log("\n4. no papel");
  await p.emulateMediaType("print");
  const papel = await p.evaluate(() => {
    const visivel = (el) => !!el && getComputedStyle(el).display !== "none";
    return {
      filtros: visivel(document.querySelector("#motivos-filtros")?.closest(".cartao")),
      cartoes: visivel(document.querySelector("#motivos-cartoes")),
      documentos: visivel(document.querySelector("#motivos-documentos")),
      recorte: [...document.querySelectorAll("p")].some((x) => visivel(x) && /Período: .* Motivos: Outros/.test(x.innerText)),
    };
  });
  await p.emulateMediaType("screen");
  checar("os filtros somem; cartões, documentos e o recorte escrito ficam",
    !papel.filtros && papel.cartoes && papel.documentos && papel.recorte, papel);
  if (process.env.FOTO) await p.screenshot({ path: process.env.FOTO, fullPage: true });
} finally {
  await navegador.close();
  const { dados: meus } = await api("GET", `/vendas?busca=-${MARCA}&limite=50`, undefined, token);
  for (const v of meus ?? []) if (!v.cancelada) await api("DELETE", `/vendas/${v.id}`, undefined, token);
  await api("DELETE", `/produtos/${prod.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
