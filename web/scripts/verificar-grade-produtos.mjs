/**
 * O grid configurável de Produtos (layout novo, fase 2 — 05/11/2026).
 *
 * 🔑 Pedido do dono: *"grids configuráveis e que proporcionem uma ótima visualização"*. Confere:
 * escolher e ordenar colunas, densidade, ordenar pelo cabeçalho (no servidor), guardar no servidor
 * (sobrevive ao recarregar) e as visões salvas com os filtros.
 * ⚠️ Mexe só na preferência `grade:produtos` do administrador — guardada no começo e devolvida no fim.
 *
 *    node scripts/verificar-grade-produtos.mjs   (API na 9200 e web na 3100 de pé)
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
const CHAVE = "/preferencias/grade:produtos";
const original = (await api("GET", CHAVE)).dados?.valor ?? null;
await api("DELETE", CHAVE);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  p.setDefaultNavigationTimeout(180000);
  await p.setViewport({ width: 1440, height: 1000 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  const cabecalho = () => p.evaluate(() => [...document.querySelectorAll("table.tabela thead th")]
    .map((t) => t.innerText.replace(/[↑↓]/g, "").trim()).filter(Boolean));
  const abrir = async (url) => {
    await p.goto(WEB + url, { waitUntil: "networkidle2" });
    await p.waitForSelector("table.tabela tbody tr", { timeout: 60000 });
    await esperar(800);
  };
  const painel = async (abrirPainel) => {
    const aberto = await p.$("#painel-colunas");
    if (!!aberto !== abrirPainel) await p.$eval("#grade-colunas", (b) => b.click());
    await esperar(300);
  };
  const guardado = async () => { await esperar(900); return (await api("GET", CHAVE)).dados?.valor ?? null; };

  console.log("1. colunas");
  await abrir("/produtos");
  const antes = await cabecalho();
  checar("o grid abre com Código, Produto e Tipo", ["Código", "Produto", "Tipo"].every((x) => antes.includes(x)), antes);
  await painel(true);
  const op = await p.evaluate(() => [...document.querySelectorAll("#painel-colunas li")].map((li) => ({
    chave: li.dataset.coluna, marcada: li.querySelector("input").checked, travada: li.querySelector("input").disabled })));
  checar("o painel lista as colunas, com Produto travada e Situação desmarcada",
    op.find((x) => x.chave === "nome")?.travada && op.find((x) => x.chave === "situacao")?.marcada === false, op);
  await p.$eval("#col-tipo", (c) => c.click());
  await esperar(300);
  checar("desmarcar Tipo tira a coluna", !(await cabecalho()).includes("Tipo"), await cabecalho());
  await p.$eval("#col-situacao", (c) => c.click());
  await esperar(300);
  checar("marcar Situação põe a coluna", (await cabecalho()).includes("Situação"), await cabecalho());
  await p.$eval('#painel-colunas li[data-coluna="preco"] button[aria-label^="Subir"]', (b) => b.click());
  await esperar(300);
  const h = await cabecalho();
  checar("subir Preço passa ele para antes de Un.", h.indexOf("Preço") >= 0 && h.indexOf("Preço") < h.indexOf("Un."), h);
  const v1 = await guardado();
  checar("a escolha vai para o servidor", v1 && v1.ocultas.includes("tipo") && !v1.ocultas.includes("situacao")
    && v1.ordem.indexOf("preco") < v1.ordem.indexOf("unidade"), v1);

  console.log("\n2. densidade e recarregar");
  await painel(false);
  await p.evaluate(() => [...document.querySelectorAll('[aria-label="Densidade das linhas"] button')].find((b) => b.textContent === "Compacta")?.click());
  await esperar(300);
  checar("Compacta aperta as linhas", await p.$eval("table.tabela", (t) => t.classList.contains("tabela-compacta")));
  await guardado();
  await abrir("/produtos");
  const depois = await cabecalho();
  checar("recarregar mantém colunas, ordem e densidade",
    !depois.includes("Tipo") && depois.includes("Situação") && depois.indexOf("Preço") < depois.indexOf("Un.")
    && await p.$eval("table.tabela", (t) => t.classList.contains("tabela-compacta")), depois);

  console.log("\n3. ordenar pelo cabeçalho");
  await p.evaluate(() => [...document.querySelectorAll("table.tabela thead th button")].find((b) => b.innerText.startsWith("Código"))?.click());
  await p.waitForFunction(() => location.search.includes("ordem=codigo"), { timeout: 5000 }).catch(() => {});
  await esperar(1200);
  checar("clicar em Código ordena e vai para a URL", p.url().includes("ordem=codigo") && !p.url().includes("direcao=desc"), p.url());
  // (crescente é o padrão da direção, e o valor padrão não vai para a URL)
  await p.evaluate(() => [...document.querySelectorAll("table.tabela thead th button")].find((b) => b.innerText.startsWith("Código"))?.click());
  await p.waitForFunction(() => location.search.includes("direcao=desc"), { timeout: 5000 }).catch(() => {});
  await esperar(1500);
  const doServidor = (await api("GET", "/produtos?ordem=codigo&direcao=desc&limite=5")).dados.map((x) => x.codigo);
  const naTela = await p.evaluate(() => [...document.querySelectorAll("table.tabela tbody tr")].slice(0, 5)
    .map((tr) => tr.querySelector("td.mono")?.innerText.trim()));
  checar("o segundo clique inverte, e a tela mostra o que o servidor ordenou",
    p.url().includes("direcao=desc") && JSON.stringify(naTela) === JSON.stringify(doServidor), { naTela, doServidor });
  checar("o cabeçalho anuncia a ordem para o leitor de tela",
    await p.evaluate(() => [...document.querySelectorAll("table.tabela thead th")].some((t) => t.getAttribute("aria-sort") === "descending")));

  console.log("\n4. visões salvas");
  await abrir("/produtos?tipo=PRODUZIDO");
  await p.$eval("#salvar-visao", (b) => b.click());
  await p.waitForSelector("#nome-visao", { timeout: 5000 });
  await p.type("#nome-visao", "Só produzidos");
  await p.evaluate(() => [...document.querySelectorAll("#visoes-grade button")].find((b) => b.textContent === "Salvar")?.click());
  await esperar(400);
  const marcada = () => p.evaluate(() => [...document.querySelectorAll("#visoes-grade .visao-grade")]
    .filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.textContent));
  checar("a visão nova aparece já escolhida", JSON.stringify(await marcada()) === JSON.stringify(["Só produzidos"]), await marcada());
  const v2 = await guardado();
  checar("e vai para o servidor com o filtro", v2?.visoes?.some((v) => v.nome === "Só produzidos" && v.busca.includes("tipo=PRODUZIDO")), v2?.visoes);
  await p.evaluate(() => [...document.querySelectorAll("#visoes-grade button")].find((b) => b.textContent === "Padrão")?.click());
  await p.waitForFunction(() => !location.search.includes("tipo="), { timeout: 5000 }).catch(() => {});
  await esperar(1200);
  const padrao = await cabecalho();
  checar("Padrão limpa o filtro e devolve as colunas de fábrica",
    !p.url().includes("tipo=") && padrao.includes("Tipo") && !padrao.includes("Situação"), { url: p.url(), padrao });
  await p.evaluate(() => [...document.querySelectorAll("#visoes-grade button")].find((b) => b.textContent === "Só produzidos")?.click());
  await p.waitForFunction(() => location.search.includes("tipo=PRODUZIDO"), { timeout: 5000 }).catch(() => {});
  await esperar(1500);
  const tipos = await p.evaluate(() => document.querySelector("label select")?.value);
  checar("abrir a visão devolve o filtro e as colunas dela",
    p.url().includes("tipo=PRODUZIDO") && !(await cabecalho()).includes("Tipo") && (await cabecalho()).includes("Situação"), { url: p.url(), tipos });
  await p.$eval('[data-visao="Só produzidos"] .visao-grade-x', (b) => b.click());
  await esperar(300);
  checar("o × apaga a visão", !(await p.$('[data-visao="Só produzidos"]')));

  console.log("\n5. restaurar");
  await painel(true);
  await p.evaluate(() => [...document.querySelectorAll("#painel-colunas button")].find((b) => b.textContent === "Restaurar")?.click());
  await esperar(400);
  const r = await cabecalho();
  checar("Restaurar volta às colunas de fábrica", r.includes("Tipo") && !r.includes("Situação"), r);
  await painel(false);

  console.log("\n5b. o filtro do PDV (10/11/2026)");
  await abrir("/produtos");
  await p.select("#produtos-pdv", "sim");
  await p.waitForFunction(() => location.search.includes("pdv=sim"), { timeout: 5000 }).catch(() => {});
  await esperar(1500);
  const totalSim = (await api("GET", "/produtos?no_pdv=true&limite=1")).dados;
  const codigosSim = new Set((await api("GET", "/produtos?no_pdv=true&limite=1000")).dados.map((x) => x.codigo));
  const naTelaPdv = await p.evaluate(() => [...document.querySelectorAll("table.tabela tbody tr")]
    .map((tr) => tr.querySelector("td.mono")?.innerText.trim()).filter(Boolean));
  checar("'Vende no PDV' vai para a URL e a tela só mostra o que o servidor diz que vende no PDV",
    p.url().includes("pdv=sim") && naTelaPdv.length > 0 && naTelaPdv.every((c) => codigosSim.has(c)),
    { url: p.url(), naTelaPdv: naTelaPdv.slice(0, 5), totalSim: totalSim?.length });
  await p.select("#produtos-pdv", "");
  await esperar(800);

  console.log("\n6. no celular");
  await p.setViewport({ width: 390, height: 844 });
  await p.reload({ waitUntil: "networkidle2" });
  await esperar(1000);
  checar("no celular (390 px) a página não rola para o lado",
    await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
} finally {
  await navegador.close();
  if (original) await api("PUT", CHAVE, { valor: original });
  else await api("DELETE", CHAVE);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
