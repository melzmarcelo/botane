/**
 * A tela de Relatórios e o Estúdio BI (layout novo, fases 3 e 4 — 05/11/2026).
 *
 * 🔑 Pedido do dono: relatórios padrão num lugar só, e um estúdio para o administrador criar os
 * seus, com ligações configuráveis. Confere: o menu Análise, o catálogo por área com a prévia em
 * folha, montar um relatório no estúdio (fontes → ligações → campos), o aviso de fonte solta, as três
 * formas de ver, a consulta montada, salvar e abrir o salvo em Relatórios.
 * ⚠️ O relatório salvo aqui chama `Smoke BI tela` e é apagado no fim.
 *
 *    node scripts/verificar-bi-relatorios.mjs   (API na 9200 e web na 3100 de pé)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const API = process.env.BOTANE_API ?? "http://127.0.0.1:9200";
const WEB = process.env.BOTANE_WEB ?? "http://127.0.0.1:3100";
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

const login = await (await fetch(API + "/auth/login", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: "admin@botane.com.br", senha: "botane123" }),
})).json();
const token = login.access_token;
const api = async (metodo, caminho, corpo) => {
  const r = await fetch(API + caminho, { method: metodo, body: corpo ? JSON.stringify(corpo) : undefined,
    headers: { Authorization: `Bearer ${token}`, "X-Unidade": "1", "Content-Type": "application/json" } });
  return { status: r.status, dados: await r.json().catch(() => null) };
};
const limpar = async () => {
  const { dados } = await api("GET", "/bi/relatorios");
  for (const r of dados ?? []) if (r.nome.startsWith("Smoke BI")) await api("DELETE", `/bi/relatorios/${r.id}`);
};
await limpar();

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  p.setDefaultNavigationTimeout(180000);
  const erros = [];
  p.on("pageerror", (e) => erros.push(e.message));
  await p.setViewport({ width: 1440, height: 1000 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. o menu Análise");
  await p.goto(WEB + "/", { waitUntil: "networkidle2" });
  await p.waitForSelector("aside nav", { timeout: 60000 });
  const hrefs = await p.evaluate(() => [...document.querySelectorAll("aside a")].map((a) => a.getAttribute("href")));
  const grupo = await p.evaluate(() => [...document.querySelectorAll("aside .menu-grupo")].map((g) => g.innerText.trim()));
  checar("o grupo Análise existe, com Relatórios e Estúdio BI",
    grupo.includes("Análise") && hrefs.includes("/relatorios") && hrefs.includes("/bi"), { grupo });

  console.log("\n2. Relatórios: catálogo e prévia em folha");
  await p.goto(WEB + "/relatorios", { waitUntil: "networkidle2" });
  await p.waitForSelector("[data-relatorio]", { timeout: 60000 });
  const areas = await p.evaluate(() => [...document.querySelectorAll('aside[aria-label="Catálogo de relatórios"] .rotulo')].map((x) => x.textContent));
  checar("o catálogo vem por área (Estoque, Vendas, Custos…)", ["ESTOQUE", "VENDAS", "CUSTOS E CMV"].every((a) => areas.map((x) => x.toUpperCase()).includes(a)), areas);
  await p.$eval('[data-relatorio="saldos"]', (b) => b.click());
  await p.waitForFunction(() => location.search.includes("r=saldos"), { timeout: 5000 }).catch(() => {});
  await p.waitForSelector("#relatorio-previa", { timeout: 10000 });
  await p.$eval("#relatorio-previa", (b) => b.click());
  await p.waitForSelector("#folha-relatorio", { timeout: 60000 }).catch(() => {});
  const { dados: d } = await api("GET", "/exportar/saldos/dados");
  const folha = await p.evaluate(() => ({
    titulo: document.querySelector("#folha-relatorio h2")?.textContent,
    linhas: document.querySelectorAll("#folha-relatorio tbody tr").length,
    rodape: document.querySelector("#folha-relatorio p:last-child")?.textContent ?? "",
  }));
  checar("Ver prévia mostra a folha com o título e as linhas do servidor (até 200)",
    folha.titulo === d.titulo && folha.linhas === d.linhas.length, { folha, servidor: d.linhas.length });
  checar("e diz quantas linhas o arquivo terá", folha.rodape.includes(d.total.toLocaleString("pt-BR")), folha.rodape);
  checar("Imprimir e Gerar planilha estão lá",
    await p.evaluate(() => ["Imprimir", "Gerar planilha"].every((t) => [...document.querySelectorAll("main button")].some((b) => b.textContent === t))));

  console.log("\n3. o Estúdio BI: montar");
  await p.goto(WEB + "/bi", { waitUntil: "networkidle2" });
  await p.waitForSelector("#bi-fontes button", { timeout: 60000 });
  const clicar = (sel) => p.$eval(sel, (b) => b.click());
  await clicar('[data-fonte="itens"]');
  await esperar(300);
  checar("marcar Itens da venda marca Vendas junto",
    await p.$eval('[data-fonte="vendas"]', (b) => b.getAttribute("aria-pressed") === "true"));
  await clicar('[data-fonte="produtos"]');
  await esperar(300);
  const ligs = await p.evaluate(() => [...document.querySelectorAll("[data-ligacao]")].map((x) => x.dataset.ligacao));
  checar("as ligações conhecidas aparecem sugeridas",
    ligs.includes("itens.id_venda-vendas.id") && ligs.includes("itens.id_produto-produtos.id"), ligs);
  await clicar('[data-campo="produtos.categoria"]');
  await clicar('[data-campo="itens.valor"]');
  await p.waitForSelector("#bi-barras", { timeout: 20000 }).catch(() => {});
  await esperar(500);
  const { dados: consulta } = await api("POST", "/bi/consultar",
    { fontes: ["itens", "vendas", "produtos"], dimensoes: ["produtos.categoria"], medidas: ["itens.valor"] });
  const barras = await p.evaluate(() => document.querySelectorAll("#bi-barras > div[title]").length);
  checar("a prévia em barras tem uma barra por categoria (até 30), como o servidor",
    barras === Math.min(consulta.linhas.length, 30) && barras > 0, { barras, servidor: consulta.linhas.length });
  await p.evaluate(() => [...document.querySelectorAll('[aria-label="Forma de ver"] button')].find((b) => b.textContent === "Tabela")?.click());
  await p.waitForSelector("#bi-tabela", { timeout: 15000 }).catch(() => {});
  checar("Tabela mostra todas as linhas",
    await p.evaluate(() => document.querySelectorAll("#bi-tabela tbody tr").length) === consulta.linhas.length);
  await p.evaluate(() => [...document.querySelectorAll('[aria-label="Forma de ver"] button')].find((b) => b.textContent === "Indicadores")?.click());
  await p.waitForSelector("#bi-indicadores", { timeout: 15000 }).catch(() => {});
  await esperar(800);
  checar("Indicadores mostra o total da medida",
    await p.evaluate(() => /R\$/.test(document.querySelector("#bi-indicadores")?.innerText ?? "")));
  await p.evaluate(() => [...document.querySelectorAll("main button")].find((b) => b.textContent === "Ver consulta")?.click());
  await esperar(300);
  checar("Ver consulta mostra o SELECT que o servidor montou",
    /SELECT[\s\S]*JOIN produtos AS produtos/.test(await p.$eval("#bi-consulta pre", (x) => x.textContent)));

  console.log("\n4. salvar e abrir em Relatórios");
  await p.evaluate(() => [...document.querySelectorAll('[aria-label="Forma de ver"] button')].find((b) => b.textContent === "Barras")?.click());
  await esperar(800);
  await clicar("#bi-salvar");
  await p.waitForSelector("#bi-nome-salvar", { timeout: 5000 });
  await p.$eval("#bi-nome-salvar", (i) => { i.select(); });
  await p.type("#bi-nome-salvar", "Smoke BI tela");
  await clicar("#bi-confirmar-salvar");
  await p.waitForFunction(() => /[?&]id=\d+/.test(location.search), { timeout: 10000 }).catch(() => {});
  const id = Number(new URL(p.url()).searchParams.get("id"));
  checar("salvar põe o relatório na URL e na fila de Meus relatórios",
    id > 0 && await p.evaluate(() => [...document.querySelectorAll("#bi-salvos button")].some((b) => b.textContent === "Smoke BI tela")), p.url());
  await p.goto(`${WEB}/relatorios?r=bi-${id}`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#relatorio-previa", { timeout: 60000 });
  checar("em Relatórios ele está em Personalizados",
    await p.evaluate((i) => !!document.querySelector(`[data-relatorio="bi-${i}"]`), id));
  await clicar("#relatorio-previa");
  await p.waitForSelector("#folha-relatorio tbody tr", { timeout: 30000 }).catch(() => {});
  checar("e a prévia em folha roda o relatório salvo",
    await p.evaluate(() => document.querySelectorAll("#folha-relatorio tbody tr").length) === consulta.linhas.length);

  console.log("\n5. fonte sem ligação");
  await p.goto(WEB + "/bi", { waitUntil: "networkidle2" });
  await p.waitForSelector("#bi-fontes button", { timeout: 60000 });
  await clicar('[data-fonte="vendas"]');
  await clicar('[data-fonte="clientes"]');
  await esperar(400);
  checar("Vendas com Clientes (sem ligação conhecida) avisa antes de consultar",
    /Clientes/.test(await p.$eval("#bi-soltas", (x) => x.textContent).catch(() => "")));

  console.log("\n6. no celular");
  await p.setViewport({ width: 390, height: 844 });
  await p.goto(WEB + "/relatorios", { waitUntil: "networkidle2" });
  await esperar(1000);
  checar("Relatórios não rola para o lado (390 px)", await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await p.goto(WEB + "/bi", { waitUntil: "networkidle2" });
  await esperar(1000);
  checar("o Estúdio não rola para o lado (390 px)", await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  checar("nenhum erro de JavaScript nas telas", !erros.length, erros);
} finally {
  await navegador.close();
  await limpar();
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
