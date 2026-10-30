/**
 * A importação do LeadsFood (Portal de Clientes → Clientes → Importar do LeadsFood).
 *
 * 🔑 Pedido do dono (30/10/2026): "siga para a importação do LeadsFood". Os CSVs são
 * SINTÉTICOS (telefones 00900004…), escritos numa pasta ao lado e apagados no fim, com o que
 * foi importado (`api/tests/cenario_plano.py limpar-importacao`).
 *
 *    node scripts/verificar-importacao-leadsfood.mjs     (API na 9200 e o Next na 3100 de pé)
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const API = "http://127.0.0.1:9200";
const WEB = "http://127.0.0.1:3100";
const PYTHON = process.env.PYTHON ?? "python";
const PASTA = resolve("scripts/_leadsfood-roteiro");
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
const limpar = () => execFileSync(PYTHON, ["tests/cenario_plano.py", "limpar-importacao", "1"], { cwd: "../api", encoding: "utf8" });

async function api(metodo, caminho, corpo, token) {
  const r = await fetch(API + caminho, {
    method: metodo,
    headers: { "Content-Type": "application/json", "X-Unidade": "1", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const texto = await r.text();
  return { status: r.status, dados: texto ? JSON.parse(texto) : null, total: r.headers.get("X-Total") };
}

// Os quatro arquivos, no formato do LeadsFood.
const hoje = new Date();
const br = (dias) => { const d = new Date(hoje.getTime() - dias * 864e5); return d.toLocaleDateString("pt-BR"); };
const ARQ = {
  contatos: ["Nome completo,Nome,Sobrenome,Celular,E-mail,Gênero,Nascimento,Aniversário,Origem,Cidade,Estado,Tags,Total reservas,Total filas,Total checkins,Total vouchers,Total avaliações,Data de criação",
    "Roteiro Alfa,Roteiro,Alfa,5500900004001,,F,10/05/1990,10/05,Conversão,Blumenau,SC,Whatsapp,1,0,1,0,0,15/03/2026 10:20",
    "Roteiro Beta,Roteiro,Beta,5500900004002,,M,,,Reservas,Gaspar,SC,,0,0,0,1,0,01/12/2025 09:00",
    "Roteiro Fora,Roteiro,Fora,353123456789,,M,,,Conversão,,,,0,0,0,0,0,01/01/2026 08:00"],
  reservas: ["Nome completo,Celular,Origem,Pessoas,Data e hora,Mesa,Status,Ambiente,Objetivo,Observações,Notas,Valor,Valor total,Taxa,Pago em,Data de criação,Última atualização",
    `Roteiro Alfa,5500900004001,Reservas,4,${br(40)} 12:00,,Compareceu,Botané,Aniversário,,,,,,,${br(45)} 10:00,${br(40)} 14:00`],
  selos: ["nome,celular,pin,campanha,status,criado_em", `Roteiro Alfa,5500900004001,AAA111,10 pratos,Confirmado,${br(10)} 12:01:00`],
  premios: ["Nome completo,Celular,Remetente,Celular remetente,Campanha,Descrição,Expiração,Valor,Status,Data utilização",
    `Roteiro Beta,5500900004002,,,10 pratos,Almoço cortesia,${br(-20)},,Não utilizado,`],
};
mkdirSync(PASTA, { recursive: true });
for (const [k, linhas] of Object.entries(ARQ)) writeFileSync(join(PASTA, `${k}.csv`), "\ufeff" + linhas.join("\n"));

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;
const { dados: par } = await api("GET", "/unidades/1/parametros", undefined, token);
await api("PUT", "/unidades/1/parametros", { ...par, reservas_ligado: true }, token);
limpar();
const quantos = async () => Number((await api("GET", "/reservas/clientes?busca=009000040&limite=5&offset=0", undefined, token)).total ?? 0);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"],
                                           defaultViewport: { width: 1280, height: 900 } });
const texto = (p) => p.evaluate(() => document.querySelector("main")?.innerText ?? "");
try {
  const p = await navegador.newPage();
  // A primeira visita a uma rota nova compila no `next dev`: passa dos 30 s padrão.
  p.setDefaultNavigationTimeout(180000);
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. de Clientes para a importação");
  await p.goto(`${WEB}/reservas/clientes`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#ir-importar-leadsfood", { timeout: 30000 }).catch(() => {});
  checar("Clientes tem o botão 'Importar do LeadsFood'", !!(await p.$("#ir-importar-leadsfood")));
  await p.goto(`${WEB}/reservas/clientes/importar`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#leadsfood-contatos", { timeout: 30000 }).catch(() => {});
  checar("a tela abre com os quatro campos", (await p.$$('input[type=file][id^="leadsfood-"]')).length === 4);

  console.log("\n2. a prévia");
  for (const k of Object.keys(ARQ)) await (await p.$(`#leadsfood-${k}`)).uploadFile(join(PASTA, `${k}.csv`));
  await esperar(300);
  checar("os nomes dos arquivos aparecem", (await texto(p)).includes("contatos.csv") && (await texto(p)).includes("premios.csv"));
  await p.click("#leadsfood-previa");
  await p.waitForSelector("#leadsfood-resumo", { timeout: 30000 }).catch(() => {});
  let t = await texto(p);
  checar("o resumo diz 2 clientes novos, 1 reserva, 1 selo e 1 prêmio",
    t.includes("2 novos") && t.includes("1 nova") && t.includes("1 selo em 1 visita") && t.includes("1 novo"), t.slice(0, 600));
  checar("o celular estrangeiro aparece nas recusas, com o nome",
    (await p.evaluate(() => document.querySelector("#leadsfood-recusados")?.innerText ?? "")).includes("Roteiro Fora"));
  checar("e a prévia não gravou nada", (await quantos()) === 0);

  console.log("\n3. importar (SEM o arquivo de selos)");
  // ⚠️ Os selos em aberto são FOTO: gravar este arquivo de um cliente só retiraria os selos
  // importados de VERDADE na base (aconteceu na primeira rodada, 30/10/2026). Os selos ficam
  // na prévia, acima; quem prova a gravação deles é a suíte de API, que devolve a loja.
  await p.reload({ waitUntil: "networkidle2" });
  await p.waitForSelector("#leadsfood-contatos", { timeout: 30000 }).catch(() => {});
  for (const k of ["contatos", "reservas", "premios"]) await (await p.$(`#leadsfood-${k}`)).uploadFile(join(PASTA, `${k}.csv`));
  await esperar(300);
  await p.click("#leadsfood-previa");
  await p.waitForSelector("#leadsfood-aplicar", { timeout: 30000 }).catch(() => {});
  checar("sem o arquivo de selos, o resumo nem fala de selos", !(await p.evaluate(() =>
    document.querySelector("#leadsfood-resumo")?.innerText ?? "")).includes("Selos"));
  await p.click("#leadsfood-aplicar");
  await p.waitForFunction(() => document.querySelector("main")?.innerText.includes("Importado"), { timeout: 30000 }).catch(() => {});
  checar("a tela diz Importado", (await texto(p)).includes("Importado"));
  checar("os 2 clientes estão no Portal", (await quantos()) === 2);
  await p.click("#leadsfood-previa");
  await p.waitForSelector("#leadsfood-resumo", { timeout: 30000 }).catch(() => {});
  await esperar(500);
  t = await texto(p);
  checar("a prévia de novo: nada novo (não duplica)", t.includes("0 novos") && t.includes("já importada, igual"), t.slice(0, 600));

  console.log("\n3b. origem e etiquetas na tela de Clientes");
  await p.goto(`${WEB}/reservas/clientes?busca=Roteiro%20Alfa`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => document.querySelector("main tbody")?.innerText.includes("Roteiro Alfa"), { timeout: 30000 }).catch(() => {});
  const cab = await p.evaluate(() => [...document.querySelectorAll("main thead th")].map((th) => th.textContent.trim()));
  checar("o grid tem as colunas Origem e Etiquetas", cab.includes("Origem") && cab.includes("Etiquetas"), cab);
  const linha = await p.evaluate(() => [...document.querySelectorAll("main tbody tr")].find((tr) => tr.innerText.includes("Roteiro Alfa"))?.innerText ?? "");
  checar("a linha mostra a origem, 'do LeadsFood' e a etiqueta",
    linha.includes("Conversão") && linha.includes("do LeadsFood") && linha.includes("Whatsapp"), linha);
  await p.goto(`${WEB}/reservas/clientes/importar`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#leadsfood-contatos", { timeout: 30000 }).catch(() => {});

  console.log("\n4. o arquivo no campo errado");
  await (await p.$("#leadsfood-contatos")).uploadFile(join(PASTA, "reservas.csv"));
  await p.click("#leadsfood-previa");
  await esperar(1500);
  checar("diz que parece o arquivo de reservas", (await texto(p)).includes("parece o de reservas"));

  console.log("\n5. no celular");
  const cel = await navegador.newPage();
  cel.setDefaultNavigationTimeout(180000);
  await cel.setViewport({ width: 390, height: 800 });
  await cel.goto(`${WEB}/reservas/clientes/importar`, { waitUntil: "networkidle2" });
  await cel.waitForSelector("#leadsfood-contatos", { timeout: 30000 }).catch(() => {});
  const largura = await cel.evaluate(() => document.documentElement.scrollWidth);
  checar("não rola para o lado (390 px)", largura <= 390, largura);
} finally {
  await navegador.close();
  limpar();
  rmSync(PASTA, { recursive: true, force: true });
  await api("PUT", "/unidades/1/parametros", par, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((x) => console.log(`  - ${x}`));
process.exit(falhas.length ? 1 : 0);
