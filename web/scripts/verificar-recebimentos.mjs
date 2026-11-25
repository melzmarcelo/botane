/**
 * Recebimento de notas no navegador (migração 162, pedido do dono de 24/11/2026). Confere:
 *   1. o menu leva à tela, e o formulário está lá;
 *   2. registrar com fornecedor fora do cadastro e FOTO pelo botão da casa;
 *   3. a linha aparece com "Não chegou ao sistema" e o botão Foto;
 *   4. a foto abre na janela (pela rota autenticada);
 *   5. o filtro "Não chegou ao sistema" mantém a linha;
 *   6. no celular a página não rola de lado;
 *   7. apagar pede confirmação e tira a linha.
 *
 *    node scripts/verificar-recebimentos.mjs   (API na 9200 e web na 3100 de pé)
 */
import { writeFileSync } from "node:fs";
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

async function api(metodo, caminho, corpo, token) {
  const r = await fetch(API + caminho, {
    method: metodo,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), "X-Unidade": "1" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const t = await r.text();
  return { status: r.status, dados: t ? JSON.parse(t) : null };
}

// Um PNG de verdade, 1×1, para o servidor aceitar como imagem.
const FOTO = "scripts/_fotos/nota-teste.png";
writeFileSync(FOTO, Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64"));

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;
const numero = `9${MARCA}`;

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1000 });
  await p.goto(WEB + "/login", { timeout: 180000 });
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. a tela");
  await p.goto(`${WEB}/compras/recebimentos`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#recebimento-form", { timeout: 60000 }).catch(() => {});
  checar("a tela abre com o formulário", !!(await p.$("#recebimento-form")));
  checar("o menu tem Compras ▸ Recebimento de notas",
    await p.evaluate(() => !!document.querySelector('a[href="/compras/recebimentos"]')));

  console.log("2. registrar com foto");
  await p.type("#recebimento-numero", numero);
  await p.click("#recebimento-alternar");
  await p.waitForSelector("#recebimento-fornecedor-texto", { timeout: 10000 });
  await p.type("#recebimento-fornecedor-texto", `Feira teste ${MARCA}`);
  const entrada = await p.$("#recebimento-foto");
  await entrada.uploadFile(FOTO);
  await p.waitForFunction(() => /nota-teste/.test(document.querySelector("#recebimento-form")?.innerText ?? ""),
    { timeout: 5000 }).catch(() => {});
  await p.click("#recebimento-registrar");
  await p.waitForFunction((n) => [...document.querySelectorAll("#recebimento-lista li")]
    .some((li) => li.innerText.includes(n)), { timeout: 30000 }, numero).catch(() => {});
  const linha = await p.evaluate((n) => {
    const li = [...document.querySelectorAll("#recebimento-lista li")].find((x) => x.innerText.includes(n));
    return li ? { id: li.dataset.recebimento, texto: li.innerText,
                  situacao: li.querySelector("[data-situacao-recebimento]")?.dataset.situacaoRecebimento,
                  foto: !!li.querySelector('[data-acao="foto"]') } : null;
  }, numero);
  checar("a linha aparece com Não chegou ao sistema", linha?.situacao === "FALTA", linha);
  checar("e com o botão Foto", !!linha?.foto, linha);
  checar("o formulário limpa para a próxima", await p.$eval("#recebimento-numero", (e) => e.value === ""));

  console.log("3. a foto");
  await p.click(`li[data-recebimento="${linha?.id}"] [data-acao="foto"]`);
  await p.waitForSelector("#recebimento-foto-grande", { timeout: 20000 }).catch(() => {});
  const img = await p.evaluate(() => {
    const i = document.querySelector("#recebimento-foto-grande");
    return i ? { carregou: i.complete && i.naturalWidth > 0, src: i.src.slice(0, 5) } : null;
  });
  checar("abre na janela, carregada por blob (rota autenticada)", !!img?.carregou && img.src === "blob:", img);
  await p.keyboard.press("Escape");

  console.log("4. filtro");
  await p.click('[data-situacao="FALTA"]');
  await p.waitForFunction(() => location.search.includes("situacao=FALTA"), { timeout: 10000 }).catch(() => {});
  await p.waitForFunction((n) => [...document.querySelectorAll("#recebimento-lista li")]
    .some((li) => li.innerText.includes(n)), { timeout: 20000 }, numero).catch(() => {});
  checar("no filtro Não chegou ao sistema, ela continua", await p.evaluate((n) =>
    [...document.querySelectorAll("#recebimento-lista li")].some((li) => li.innerText.includes(n)), numero));

  console.log("5. celular");
  await p.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
  await p.reload({ waitUntil: "networkidle2", timeout: 60000 });
  await p.waitForSelector("#recebimento-form", { timeout: 60000 }).catch(() => {});
  const larg = await p.evaluate(() => ({ doc: document.documentElement.scrollWidth, tela: window.innerWidth }));
  checar("a página não rola de lado", larg.doc <= larg.tela, larg);
  await p.setViewport({ width: 1366, height: 1000 });

  console.log("6. apagar");
  await p.goto(`${WEB}/compras/recebimentos?busca=${numero}`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector(`li[data-recebimento="${linha?.id}"] [data-acao="apagar"]`, { timeout: 20000 }).catch(() => {});
  await p.click(`li[data-recebimento="${linha?.id}"] [data-acao="apagar"]`);
  await p.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.innerText.trim() === "Apagar"),
    { timeout: 10000 }).catch(() => {});
  await p.evaluate(() => [...document.querySelectorAll('[role="dialog"] button')].find((b) => b.innerText.trim() === "Apagar")?.click());
  await p.waitForFunction((id) => !document.querySelector(`li[data-recebimento="${id}"]`), { timeout: 15000 }, linha?.id).catch(() => {});
  checar("some da lista", !(await p.$(`li[data-recebimento="${linha?.id}"]`)));
} finally {
  await navegador.close();
  const { dados } = await api("GET", `/recebimentos?busca=${numero}&limite=10`, undefined, token);
  for (const r of dados ?? []) await api("DELETE", `/recebimentos/${r.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
