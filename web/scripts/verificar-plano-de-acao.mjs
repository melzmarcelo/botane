/**
 * O Plano de ação das reservas (Portal de Clientes → Reservas → Plano de ação).
 *
 * 🔑 Pedido do dono (30/10/2026): *"comece pelo plano de ação de reservas"* — a tela do
 * LeadsFood: VIPs em risco, organizadores de grupo sumidos e adormecidos, com WhatsApp.
 * O cenário (reservas no passado) é montado e apagado por `api/tests/cenario_plano.py`.
 *
 *    node scripts/verificar-plano-de-acao.mjs     (API na 9200 e o Next na 3100 de pé)
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
const cenario = (acao) => JSON.parse(execFileSync(PYTHON, ["tests/cenario_plano.py", acao, "1"],
  { cwd: "../api", encoding: "utf8" }).trim().split(/\r?\n/).pop());

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
const F = cenario("montar");

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"],
                                           defaultViewport: { width: 1280, height: 900 } });
/** As linhas da lista aberta: nome e o link do WhatsApp (ou null). */
const linhas = (p) => p.evaluate(() => [...document.querySelectorAll("main li")].map((li) => ({
  texto: li.textContent,
  link: li.querySelector('a[href^="https://wa.me/"]')?.getAttribute("href") ?? null,
})));
const linhaDe = (ls, nome) => ls.find((l) => l.texto.includes(nome));

try {
  const p = await navegador.newPage();
  // A primeira visita a uma rota nova compila no `next dev`: passa dos 30 s padrão.
  p.setDefaultNavigationTimeout(180000);
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. a tela e o menu");
  await p.goto(`${WEB}/reservas/plano-de-acao`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => document.body.textContent.includes("Clientes para recuperar agora"), { timeout: 20000 }).catch(() => {});
  checar("abre com o título", await p.evaluate(() => document.querySelector("h1")?.textContent === "Plano de ação"));
  checar("o menu tem o item", await p.evaluate(() => !!document.querySelector('a[href="/reservas/plano-de-acao"]')));

  console.log("\n2. VIPs em risco (a lista que abre)");
  let ls = await linhas(p);
  const vip = linhaDe(ls, "VALENTINA Roteiro");
  checar("o VIP do cenário aparece", !!vip, ls.map((l) => l.texto).slice(0, 5));
  checar("o botão abre o WhatsApp do número", vip?.link?.startsWith(`https://wa.me/55${F.vip}?text=`), vip?.link);
  const texto = vip?.link ? decodeURIComponent(vip.link.split("text=")[1]) : "";
  checar("o convite chama pelo primeiro nome, sem caixa alta", texto.includes("Olá, Valentina!"), texto);
  checar("e sem marcador sobrando", !texto.includes("{"), texto);
  checar("o organizador NÃO está em VIPs", !linhaDe(ls, "Otávio Roteiro"));

  console.log("\n3. mensagem editada vai no link");
  await p.evaluate(() => {
    const t = document.querySelector("main textarea");
    const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
    set.call(t, "Oi {nome}, saudades!");
    t.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await esperar(300);
  ls = await linhas(p);
  const editado = decodeURIComponent((linhaDe(ls, "VALENTINA Roteiro")?.link ?? "").split("text=")[1] ?? "");
  checar("o link leva o texto novo", editado === "Oi Valentina, saudades!", editado);

  console.log("\n4. as outras listas");
  await p.evaluate(() => [...document.querySelectorAll("main button")].find((b) => b.textContent.includes("organizadores de grupo"))?.click());
  await esperar(500);
  ls = await linhas(p);
  const org = linhaDe(ls, "Otávio Roteiro");
  checar("o organizador aparece com os grupos e as pessoas", !!org && /2\s*grupos/.test(org.texto) && /21\s*pessoas/.test(org.texto), org?.texto);
  checar("a lista escolhida vai para a URL", p.url().includes("lista=organizadores"), p.url());
  await p.evaluate(() => [...document.querySelectorAll("main button")].find((b) => b.textContent.includes("adormecidos para convidar"))?.click());
  await esperar(500);
  // ⚠️ "Sumiu há mais tempo": o cenário sumiu há 400 dias e, com a base que já tem clientes
  // de verdade (a importação do LeadsFood, 30/10/2026), na ordem padrão ele cai na ÚLTIMA página.
  await p.select("main select", "mais");
  await esperar(500);
  ls = await linhas(p);
  checar("o adormecido aparece", !!linhaDe(ls, "Dora Roteiro"));
  const parou = linhaDe(ls, "Paula Roteiro");
  checar("quem pediu para não receber aparece SEM o botão", !!parou && !parou.link && parou.texto.includes("não quer receber"), parou);

  console.log("\n5. os critérios");
  await p.evaluate(() => document.querySelector("main details summary")?.click());
  await esperar(200);
  // Adormecido: sem vir há 500 dias — o cenário tem 400, então a lista esvazia dele.
  await p.evaluate(() => {
    const campo = [...document.querySelectorAll("main details label")].find((l) => l.textContent.includes("Adormecido: sem vir há"))?.querySelector("input");
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    set.call(campo, "500");
    campo.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await p.evaluate(() => [...document.querySelectorAll("main details button")].find((b) => b.textContent.trim() === "Aplicar")?.click());
  await esperar(1200);
  ls = await linhas(p);
  checar("com 500 dias, o adormecido de 400 sai", !linhaDe(ls, "Dora Roteiro"));
  await p.evaluate(() => [...document.querySelectorAll("main details button")].find((b) => b.textContent.trim() === "Voltar ao padrão")?.click());
  await esperar(1200);
  ls = await linhas(p);
  checar("voltar ao padrão traz de volta", !!linhaDe(ls, "Dora Roteiro"));

  console.log("\n6. no celular");
  const cel = await navegador.newPage();
  cel.setDefaultNavigationTimeout(180000);
  await cel.setViewport({ width: 390, height: 800 });
  await cel.goto(`${WEB}/reservas/plano-de-acao`, { waitUntil: "networkidle2" });
  await cel.waitForFunction(() => document.body.textContent.includes("Clientes para recuperar agora"), { timeout: 20000 }).catch(() => {});
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
