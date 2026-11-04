/**
 * Os três painéis que vieram do LeadsFood, no navegador (04/11/2026).
 *
 * 🔑 Pedido do dono: *"uma tela com todos os indicadores que são apresentados lá"*. Confere que
 * cada quadro aparece e que os números da tela são os da API:
 *   1. Portal de Clientes ▸ Painel de clientes (base, novos por mês/dia, pirâmide, gênero,
 *      cidades, origem) — e o botão que leva a ele na lista de Clientes;
 *   2. Reservas ▸ Painel: ano contra ano e sazonalidade;
 *   3. Fidelidade ▸ Painel: check-ins por mês e por dia, e os dois rankings (o nome abre a ficha).
 * ⚠️ Só lê: nada é criado. Os números dependem da base, então a régua é a própria API.
 *
 *    node scripts/verificar-paineis-leadsfood.mjs   (API na 9200 e web na 3100 de pé)
 *    FOTOS=pasta node scripts/...                   (guarda uma foto de cada tela)
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
const inteiro = (n) => n.toLocaleString("pt-BR");

async function api(caminho, token) {
  const r = await fetch(API + caminho, { headers: { Authorization: `Bearer ${token}`, "X-Unidade": "1" } });
  return { status: r.status, dados: await r.json() };
}

const login = await (await fetch(API + "/auth/login", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: "admin@botane.com.br", senha: "botane123" }),
})).json();
const token = login.access_token;

const { status: s1, dados: cli } = await api("/reservas/clientes/painel", token);
const { status: s2, dados: res } = await api("/reservas/painel?meses=12", token);
const { status: s3, dados: fid } = await api("/fidelidade/painel/graficos", token);
console.log("0. a API");
checar("as três rotas respondem", s1 === 200 && s2 === 200 && s3 === 200, { s1, s2, s3 });
checar("a base soma o que a pirâmide e o gênero contam",
  cli.genero.feminino + cli.genero.masculino + cli.genero.nao_informado === cli.resumo.base &&
  cli.idade.reduce((s, x) => s + x.feminino + x.masculino + x.outros, 0) + cli.sem_idade === cli.resumo.base,
  { genero: cli.genero, base: cli.resumo.base, sem_idade: cli.sem_idade });
checar("a origem soma a base", cli.origens.reduce((s, x) => s + x.n, 0) === cli.resumo.base);
checar("o ano contra ano vai de janeiro ao último mês fechado, e a sazonalidade tem os 12 meses",
  res.ano_contra_ano.meses.length === res.ano_contra_ano.ate_mes && res.sazonalidade.length === 12,
  { ate: res.ano_contra_ano.ate_mes, n: res.ano_contra_ano.meses.length });
checar("check-ins: 6 meses e 14 dias, com clientes únicos nunca acima dos check-ins",
  fid.por_mes.length === 6 && fid.por_dia.length === 14 && fid.por_mes.every((x) => x.clientes <= x.checkins));

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1000 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  const foto = async (nome) => process.env.FOTOS && p.screenshot({ path: `${process.env.FOTOS}/${nome}.png`, fullPage: true });

  console.log("\n1. Portal de Clientes ▸ Painel de clientes");
  await p.goto(WEB + "/reservas/clientes", { waitUntil: "networkidle2" });
  await p.waitForSelector("#ir-painel-clientes", { timeout: 30000 }).catch(() => {});
  checar("a lista de Clientes tem o botão do painel",
    (await p.$eval("#ir-painel-clientes", (a) => a.getAttribute("href")).catch(() => "")) === "/reservas/clientes/painel");
  await p.goto(WEB + "/reservas/clientes/painel", { waitUntil: "networkidle2" });
  await p.waitForSelector("#clientes-piramide", { timeout: 30000 }).catch(() => {});
  const t = await p.evaluate(() => ({
    numeros: [...document.querySelectorAll("#clientes-numeros b")].map((b) => b.innerText),
    mes: document.querySelectorAll("#clientes-por-mes svg rect").length,
    dia: document.querySelectorAll("#clientes-por-dia svg rect").length,
    faixas: document.querySelectorAll("#clientes-piramide li").length,
    genero: document.querySelector("#clientes-genero")?.innerText ?? "",
    cidades: document.querySelectorAll("#clientes-cidades li").length,
    origem: document.querySelector("#clientes-origem")?.innerText ?? "",
    menu: [...document.querySelectorAll("nav a")].some((a) => a.getAttribute("href") === "/reservas/clientes/painel"),
  }));
  checar("os quatro números são os da API (base, no ano, no mês, hoje)",
    JSON.stringify(t.numeros) === JSON.stringify([cli.resumo.base, cli.resumo.no_ano, cli.resumo.no_mes, cli.resumo.hoje].map(inteiro)),
    t.numeros);
  checar("novos por mês e por dia desenham uma barra por ponto", t.mes === 6 && t.dia === 14, t);
  checar("a pirâmide tem uma linha por faixa", t.faixas === cli.idade.length, t.faixas);
  checar("gênero mostra mulheres, homens e não informado",
    /Mulheres/.test(t.genero) && /Homens/.test(t.genero) && /Não informado/.test(t.genero) &&
    t.genero.includes(inteiro(cli.genero.feminino)), t.genero);
  checar("as cidades são as da API, até dez", t.cidades === cli.cidades.top.length, t.cidades);
  checar("a origem lista cada origem da API",
    cli.origens.every((x) => t.origem.includes(x.origem)), t.origem);
  checar("o menu tem o Painel de clientes", t.menu);
  await foto("painel-clientes");

  // 🔑 04/11/2026: os aniversariantes, no fim do painel.
  const an = cli.aniversariantes;
  const ab = await p.evaluate(() => ({
    abas: [...document.querySelectorAll("#clientes-aniversariantes [role=tab]")]
      .map((b) => ({ aba: b.dataset.aba, n: b.querySelector(".mono")?.textContent, sel: b.getAttribute("aria-selected") })),
    linhas: document.querySelectorAll("#clientes-aniversariantes li").length,
    zap: [...document.querySelectorAll("#clientes-aniversariantes a[href^='https://wa.me/']")].map((a) => a.href),
    barras: document.querySelectorAll("#aniversarios-por-mes svg rect").length,
  }));
  checar("aniversariantes: as quatro abas com os números da API",
    JSON.stringify(ab.abas.map((x) => x.n)) === JSON.stringify([an.hoje, an.semana, an.no_mes, an.proximo_mes].map(inteiro)), ab.abas);
  const contas = { hoje: an.hoje, semana: an.semana, mes: an.no_mes, proximo: an.proximo_mes };
  const aberta = ab.abas.find((x) => x.sel === "true");
  checar("abre na primeira aba que tem gente, uma linha por pessoa (até 20 por página)",
    aberta && aberta.aba === (ab.abas.find((x) => contas[x.aba] > 0)?.aba ?? "hoje")
    && ab.linhas === Math.min(contas[aberta.aba], 20), { aberta, linhas: ab.linhas });
  checar("o botão abre o WhatsApp com o parabéns e o nome da casa",
    !ab.linhas || (ab.zap.length > 0 && ab.zap.every((h) => decodeURIComponent(h).includes("Feliz aniversário")
      && decodeURIComponent(h).includes(cli.loja ?? "nossa casa"))), ab.zap.slice(0, 1));
  checar("aniversários por mês: doze barras", ab.barras === 12, ab.barras);
  await p.$eval("#clientes-aniversariantes [data-aba=proximo]", (b) => b.click());
  // A URL vem com atraso de propósito (useEstadoNaUrl, 300 ms).
  await p.waitForFunction(() => location.search.includes("aniversario="), { timeout: 5000 }).catch(() => {});
  checar("trocar de aba muda a lista e vai para a URL",
    p.url().includes("aniversario=proximo") &&
    await p.evaluate(() => document.querySelectorAll("#clientes-aniversariantes li").length) === Math.min(an.proximo_mes, 20),
    p.url());

  await p.setViewport({ width: 390, height: 844 });
  await p.reload({ waitUntil: "networkidle2" });
  await p.waitForSelector("#clientes-piramide", { timeout: 30000 }).catch(() => {});
  checar("no celular (390 px), o painel de clientes não rola para o lado",
    await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await p.setViewport({ width: 1366, height: 1000 });

  console.log("\n2. Reservas ▸ Painel: ano contra ano e sazonalidade");
  await p.goto(WEB + "/reservas/painel?meses=12", { waitUntil: "networkidle2" });
  await p.waitForSelector("#reservas-sazonalidade", { timeout: 30000 }).catch(() => {});
  const r = await p.evaluate(() => ({
    aa: document.querySelectorAll("#reservas-ano-contra-ano svg rect").length,
    aaTexto: document.querySelector("#reservas-ano-contra-ano")?.closest("section,div.cartao")?.innerText ?? "",
    saz: document.querySelectorAll("#reservas-sazonalidade svg rect").length,
    sazTexto: document.querySelector("#reservas-sazonalidade")?.closest("section,div.cartao")?.innerText ?? "",
  }));
  const a = res.ano_contra_ano;
  checar("ano contra ano: duas barras por mês fechado e a legenda com os dois anos",
    r.aa === a.meses.length * 2 && r.aaTexto.includes(String(a.ano)) && r.aaTexto.includes(String(a.anterior)), r);
  checar(a.variacao.reservas === null ? "sem ano anterior, diz que não há com que comparar (nada de +0%)"
                                      : "com ano anterior, mostra a variação",
    a.variacao.reservas === null ? /para comparar/.test(r.aaTexto) && !/\+0%/.test(r.aaTexto) : /%/.test(r.aaTexto),
    r.aaTexto.slice(0, 200));
  checar("sazonalidade: doze meses, com pico e vale", r.saz === 12 && /pico: /.test(r.sazTexto) && /vale: /.test(r.sazTexto), r);
  await foto("painel-reservas");

  console.log("\n3. Fidelidade ▸ Painel: check-ins e quem mais vem");
  await p.goto(WEB + "/fidelidade/painel", { waitUntil: "networkidle2" });
  await p.waitForSelector("#fidelidade-graficos", { timeout: 30000 }).catch(() => {});
  const f = await p.evaluate(() => ({
    rects: document.querySelectorAll("#fidelidade-graficos svg rect").length,
    top: [...document.querySelectorAll("#top-sempre li")].map((li) => li.innerText.replace(/\s+/g, " ")),
    top30: document.querySelectorAll("#top-30-dias li").length,
  }));
  checar("check-ins por mês (duas barras) e por dia (uma) desenhados", f.rects === 6 * 2 + 14, f.rects);
  checar("os rankings são os da API, com o número de visitas",
    f.top.length === fid.top_sempre.length && f.top30 === fid.top_30_dias.length &&
    (!fid.top_sempre.length || (f.top[0].includes(fid.top_sempre[0].nome) && f.top[0].includes(`${fid.top_sempre[0].visitas}×`))),
    { tela: f.top.slice(0, 2), api: fid.top_sempre.slice(0, 2) });
  await foto("painel-fidelidade");
  if (fid.top_sempre.length) {
    await p.$eval("#top-sempre li button", (b) => b.click());
    await p.waitForFunction(() => location.search.includes("cliente="), { timeout: 10000 }).catch(() => {});
    checar("o nome no ranking abre a ficha do participante",
      (await p.evaluate(() => location.search)).includes(`cliente=${fid.top_sempre[0].id}`));
  }
} finally {
  await navegador.close();
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
