/**
 * Sem conexão NÃO é sair da conta (v1.2.0).
 *
 * 🔴 Achado da análise de 30/10/2026: ao abrir o sistema, QUALQUER falha do `/auth/me` apagava
 * a sessão — celular sem sinal, a API trocando de contêiner no deploy, o banco com a conexão
 * caída. Agora só o 401/403 do servidor encerra; o resto mostra "sem conexão" e tenta de novo.
 *
 *    node scripts/verificar-sessao-sem-conexao.mjs     (API na 9200 e o Next na 3100 de pé)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const API = "http://127.0.0.1:9200";
const WEB = "http://127.0.0.1:3100";
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

const login = await (await fetch(API + "/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: "admin@botane.com.br", senha: "botane123" }) })).json();
const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"],
                                           defaultViewport: { width: 1280, height: 900 } });
try {
  const p = await navegador.newPage();
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  const temSessao = () => p.evaluate(() => !!localStorage.getItem("botane.access") && !!localStorage.getItem("botane.refresh"));

  console.log("1. a API não responde ao abrir");
  let fora = true;
  await p.setRequestInterception(true);
  p.on("request", (r) => {
    if (fora && r.url().startsWith(API + "/auth/me")) r.abort("internetdisconnected");
    else r.continue();
  });
  await p.goto(WEB + "/estoque", { waitUntil: "networkidle2" });
  await p.waitForSelector("#sem-conexao", { timeout: 15000 }).catch(() => {});
  checar("a tela diz que está sem conexão", !!(await p.$("#sem-conexao")));
  checar("e a sessão CONTINUA guardada", await temSessao());
  checar("sem ir para o login", !p.url().includes("/login"), p.url());

  console.log("\n2. a conexão volta");
  fora = false;
  await p.waitForFunction(() => !document.querySelector("#sem-conexao"), { timeout: 15000 }).catch(() => {});
  await esperar(1000);
  checar("a tela abre sozinha, sem digitar a senha",
    !(await p.$("#sem-conexao")) && (await p.evaluate(() => !!document.querySelector("h1"))) && !p.url().includes("/login"),
    p.url());

  console.log("\n3. sessão recusada pelo servidor ainda sai da conta");
  await p.evaluate(() => { localStorage.setItem("botane.access", "invalido"); localStorage.setItem("botane.refresh", "invalido"); });
  await p.goto(WEB + "/estoque", { waitUntil: "networkidle2" });
  await p.waitForFunction(() => location.pathname.startsWith("/login"), { timeout: 15000 }).catch(() => {});
  checar("401 de verdade leva ao login e limpa a sessão", p.url().includes("/login") && !(await temSessao()), p.url());
} finally {
  await navegador.close();
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((x) => console.log(`  - ${x}`));
process.exit(falhas.length ? 1 : 0);
