/**
 * O painel das reservas (Portal de Clientes → Reservas → Painel).
 *
 * 🔑 Pedido do dono (30/10/2026): os gráficos do BI de reservas do LeadsFood. Um ano de
 * reservas é montado e apagado por `api/tests/cenario_plano.py painel` (telefones 00900001…).
 *
 *    node scripts/verificar-painel-reservas.mjs     (API na 9200 e o Next na 3100 de pé)
 */
import { execFileSync } from "node:child_process";
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const API = "http://127.0.0.1:9200";
const WEB = "http://127.0.0.1:3100";
const PYTHON = process.env.PYTHON ?? "python";
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
const cenario = (acao) => execFileSync(PYTHON, ["tests/cenario_plano.py", acao, "1"], { cwd: "../api", encoding: "utf8" });

async function api(metodo, caminho, corpo, token) {
  const r = await fetch(API + caminho, {
    method: metodo,
    headers: { "Content-Type": "application/json", "X-Unidade": "1", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const texto = await r.text();
  return { status: r.status, dados: texto ? JSON.parse(texto) : null };
}

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;
const { dados: par } = await api("GET", "/unidades/1/parametros", undefined, token);
await api("PUT", "/unidades/1/parametros", { ...par, reservas_ligado: true }, token);
cenario("painel");
const { dados: esperado } = await api("GET", "/reservas/painel?meses=12", undefined, token);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"],
                                           defaultViewport: { width: 1280, height: 900 } });
const pronto = (p) => p.waitForFunction(() => document.body.textContent.includes("reservas válidas")
  && document.querySelectorAll("main svg[role=img]").length >= 4, { timeout: 30000 }).catch(() => {});
const numeros = (p) => p.evaluate(() => [...document.querySelectorAll("main .cartao b.mono")].slice(0, 5).map((b) => b.textContent.trim()));
const fmt = (n) => n.toLocaleString("pt-BR");

try {
  const p = await navegador.newPage();
  // A primeira visita a uma rota nova compila no `next dev`: passa dos 30 s padrão.
  p.setDefaultNavigationTimeout(180000);
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. a tela, o menu e os números");
  await p.goto(`${WEB}/reservas/painel`, { waitUntil: "networkidle2" });
  await pronto(p);
  checar("abre com o título", await p.evaluate(() => document.querySelector("h1")?.textContent === "Painel"));
  checar("o menu tem o item", await p.evaluate(() => !!document.querySelector('a[href="/reservas/painel"]')));
  const n = await numeros(p);
  checar("os números batem com o servidor (reservas, clientes, pessoas)",
    n[0] === fmt(esperado.resumo.reservas) && n[1] === fmt(esperado.resumo.clientes) && n[2] === fmt(esperado.resumo.pessoas),
    { tela: n, api: esperado.resumo });
  checar("o cenário aparece (mais de 100 reservas)", esperado.resumo.reservas > 100, esperado.resumo);

  console.log("\n2. os quadros");
  const quadros = await p.evaluate(() => [...document.querySelectorAll("main h2")].map((h) => h.textContent));
  for (const t of ["Evolução por mês", "Por dia da semana", "Por horário de chegada", "Objetivo da visita", "Grupos grandes"]) {
    checar(`tem "${t}"`, quadros.includes(t), quadros);
  }
  checar("quatro desenhos (mês, dia, hora, grupos) e as barras de objetivo",
    await p.evaluate(() => document.querySelectorAll("main svg[role=img]").length) === 4
    && await p.evaluate(() => document.body.textContent.includes("Aniversário")));
  checar("a semana tem os sete dias no eixo",
    await p.evaluate(() => ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"].every((d) =>
      [...document.querySelectorAll('main svg[aria-label*="dia da semana"] text')].some((t) => t.textContent === d))));

  console.log("\n3. a dica ao passar o cursor");
  const caixa = await p.evaluate(() => {
    const r = document.querySelector('main svg[aria-label*="por mês"]').getBoundingClientRect();
    return { x: r.x + r.width * 0.95, y: r.y + r.height * 0.5 };
  });
  await p.mouse.move(caixa.x, caixa.y);
  await esperar(300);
  const dica = await p.evaluate(() => document.querySelector("main .bg-tinta")?.textContent ?? "");
  checar("o último mês diz que está em andamento e traz as três contas",
    dica.includes("mês em andamento") && dica.includes("Reservas") && dica.includes("No-shows"), dica);

  console.log("\n4. a tabela dos números");
  await p.evaluate(() => [...document.querySelectorAll("main summary")].find((s) => s.textContent.includes("Ver os números"))?.click());
  await esperar(200);
  checar("uma linha por mês (12)", await p.evaluate(() =>
    document.querySelector("main details[open] tbody")?.querySelectorAll("tr").length) === 12);

  console.log("\n5. medida e período");
  await p.evaluate(() => [...document.querySelectorAll('main [role=tab]')].find((b) => b.textContent === "Pessoas")?.click());
  await esperar(500);
  checar("Pessoas vai para a URL", p.url().includes("medida=pessoas"), p.url());
  checar("o eixo do mês passa a contar pessoas", await p.evaluate(() =>
    !!document.querySelector('main svg[aria-label="Pessoas por mês"]')));
  await p.select("main select", "3");
  await esperar(1500);
  checar("3 meses: três barras de mês e a URL lembra", p.url().includes("meses=3") && await p.evaluate(() =>
    document.querySelector('main svg[aria-label="Pessoas por mês"]')?.querySelectorAll("rect").length) === 3, p.url());
  await p.reload({ waitUntil: "networkidle2" });
  await pronto(p);
  checar("recarregar mantém período e medida", await p.evaluate(() =>
    document.querySelector("main select")?.value === "3"
    && document.querySelector('main [role=tab][aria-selected="true"]')?.textContent === "Pessoas"));

  console.log("\n6. no celular");
  const cel = await navegador.newPage();
  cel.setDefaultNavigationTimeout(180000);
  await cel.setViewport({ width: 390, height: 800 });
  await cel.goto(`${WEB}/reservas/painel`, { waitUntil: "networkidle2" });
  await pronto(cel);
  const largura = await cel.evaluate(() => document.documentElement.scrollWidth);
  checar("não rola para o lado (390 px)", largura <= 390, largura);
} finally {
  await navegador.close();
  cenario("limpar");
  await api("PUT", "/unidades/1/parametros", par, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((x) => console.log(`  - ${x}`));
process.exit(falhas.length ? 1 : 0);
