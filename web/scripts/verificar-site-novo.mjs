/**
 * O site do cliente no layout novo (protótipo aprovado pelo dono, 05/11/2026).
 *
 * 🔑 *"pode implementar igual ao protótipo, lembrando que podemos ter N catálogos"*. Confere: a
 * capa só no início, os N catálogos na fileira E na grade de "Ver tudo" (um cartão por catálogo,
 * com o nome como texto), as abas de baixo que acendem conforme a tela, os dias em botões e as
 * pessoas com − e +, e que nada rola para o lado no celular.
 * O cenário usa os catálogos que a base local publica (lidos de `/publico/1/catalogos`).
 *
 *    node scripts/verificar-site-novo.mjs     (API na 9200 e o Next na 3100 de pé)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const API = "http://127.0.0.1:9200";
const SITE = "http://127.0.0.1:3100/portal/?loja=1";
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

const catalogos = await (await fetch(`${API}/publico/1/catalogos`)).json();
const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"],
                                           defaultViewport: { width: 390, height: 844 } });
try {
  const p = await navegador.newPage();
  const erros = [];
  p.on("pageerror", (e) => erros.push(e.message));
  await p.goto(SITE, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => document.querySelector("#linha-dias")?.textContent !== "…", { timeout: 20000 }).catch(() => {});
  await esperar(600);

  console.log("1. o início");
  checar("a capa aparece no início, com o nome da casa e a saudação",
    await p.evaluate(() => getComputedStyle(document.querySelector(".capa")).display !== "none"
      && !!document.querySelector("#nome-da-casa").textContent.trim()
      && /^(Bom dia|Boa tarde|Boa noite)!$/.test(document.querySelector("#saudacao").textContent)));
  const naFileira = await p.$$eval("#itens .cartao-catalogo", (cs) => cs.map((c) => c.textContent));
  checar(`os ${catalogos.length} catálogos entram na fileira, um cartão cada, com o nome como texto`,
    naFileira.length === catalogos.length && catalogos.every((c, i) => naFileira[i] === c.nome), { naFileira });
  checar("a fileira rola de lado (não quebra linha)",
    await p.$eval("#itens", (e) => getComputedStyle(e).flexDirection === "row" && getComputedStyle(e).overflowX === "auto"));
  if (catalogos.length >= 3) {
    checar("com 3 ou mais aparece 'Ver tudo'", await p.$eval("#ver-catalogos", (b) => !b.hidden));
  }
  const comCapa = catalogos.filter((c) => c.capa).length;
  checar("o catálogo com capa mostra a foto; o sem, o ícone",
    await p.$$eval("#itens .cartao-catalogo .capa-cat img", (i) => i.length) === comCapa);

  console.log("\n2. as abas");
  const abas = await p.$$eval("#abas button:not([hidden])", (bs) => bs.map((b) => b.dataset.aba));
  checar("as abas aparecem: Início sempre, Cardápio com catálogo", abas[0] === "inicio" && abas.includes("cardapio"), abas);
  checar("o Início começa aceso", await p.$eval('#abas [data-aba="inicio"]', (b) => b.getAttribute("aria-current")) === "page");
  if (catalogos.length > 1) {
    await p.$eval('#abas [data-aba="cardapio"]', (b) => b.click());
    await p.waitForSelector('[data-tela="catalogos"][data-ativa]', { timeout: 5000 }).catch(() => {});
    checar("a aba Cardápio abre a grade com TODOS os catálogos",
      await p.$$eval("#lista-catalogos .cartao-catalogo", (c) => c.length) === catalogos.length);
    checar("e acende a aba", await p.$eval('#abas [data-aba="cardapio"]', (b) => b.getAttribute("aria-current")) === "page");
    checar("fora do início a capa some",
      await p.evaluate(() => getComputedStyle(document.querySelector(".capa")).display === "none"));
  }

  console.log("\n3. a reserva");
  await p.evaluate(() => abrirReserva());
  await esperar(1500);
  const dias = await p.$$eval("#dias .dia-chip", (bs) => bs.length);
  checar("os dias aparecem em botões", dias > 0, dias);
  if (dias) {
    const alvo = await p.$eval("#dias .dia-chip:last-child", (b) => b.dataset.dia);
    await p.$eval("#dias .dia-chip:last-child", (b) => b.click());
    await esperar(400);
    checar("tocar no dia preenche o campo e acende o botão",
      await p.evaluate((d) => document.querySelector("#dia").value === d
        && document.querySelector(`#dias [data-dia="${d}"]`).getAttribute("aria-pressed") === "true", alvo));
  }
  const antes = Number(await p.$eval("#pessoas", (i) => i.value));
  await p.$eval("#mais-pessoas", (b) => b.click());
  await p.$eval("#mais-pessoas", (b) => b.click());
  await p.$eval("#menos-pessoas", (b) => b.click());
  checar("+ + − soma uma pessoa", Number(await p.$eval("#pessoas", (i) => i.value)) === antes + 1);
  for (let i = 0; i < 30; i++) await p.$eval("#menos-pessoas", (b) => b.click());
  checar("e não passa de 1 para baixo", await p.$eval("#pessoas", (i) => i.value) === "1");
  const alvos = await p.$$eval("#menos-pessoas, #mais-pessoas, #dias .dia-chip, #abas button:not([hidden])",
    (bs) => bs.map((b) => Math.min(b.getBoundingClientRect().width, b.getBoundingClientRect().height)));
  checar("todo botão de toque tem pelo menos 44px", alvos.every((n) => n >= 44), alvos);

  console.log("\n4. no celular e no computador");
  checar("nada rola para o lado (390 px)", await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await p.setViewport({ width: 1280, height: 900 });
  await p.goto(SITE, { waitUntil: "networkidle2" });
  await esperar(800);
  checar("no computador a coluna fica centrada e estreita",
    await p.$eval(".folha", (f) => f.getBoundingClientRect().width <= 520 && f.getBoundingClientRect().left > 300));
  checar("nenhum erro de JavaScript", !erros.length, erros);
} finally {
  await navegador.close();
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((x) => console.log(`  - ${x}`));
process.exit(falhas.length ? 1 : 0);
