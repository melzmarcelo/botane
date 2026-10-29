// Foto de celular (390) de verdade: página aberta JÁ no tamanho de celular. Só lê.
// LARGURA=1280 tira a do computador.
import puppeteer from "puppeteer-core";
const WEB = "http://127.0.0.1:3100";
const [saida, ...rotas] = process.argv.slice(2);
const nav = await puppeteer.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: "new", args: ["--no-sandbox"] });
const p = await nav.newPage();
const L = Number(process.env.LARGURA || 390);
await p.setViewport({ width: L, height: L > 600 ? 900 : 844, isMobile: L <= 600, hasTouch: L <= 600, deviceScaleFactor: 1 });
await p.goto(`${WEB}/login`, { waitUntil: "networkidle2" });
await new Promise((r) => setTimeout(r, 2500));
await p.type('input[type="email"]', "admin@botane.com.br");
await p.type('input[type="password"]', "botane123");
await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {}), p.click('button[type="submit"]')]);
await new Promise((r) => setTimeout(r, 2000));
if (p.url().includes("/login")) { console.log("NAO ENTROU"); process.exit(1); }
for (const rota of rotas) {
  await p.goto(WEB + rota, { waitUntil: "networkidle2" });
  for (let i = 0; i < 30; i++) { if (!(await p.evaluate(() => /Carregando/.test(document.querySelector("main")?.innerText ?? "")))) break; await new Promise((r) => setTimeout(r, 500)); }
  await new Promise((r) => setTimeout(r, 800));
  const w = await p.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  const nome = `${saida}/${rota === "/" ? "inicio" : rota.slice(1).replace(/\//g, "_")}.png`;
  await p.screenshot({ path: nome, fullPage: true });
  console.log(rota, w, nome);
}
await nav.close();
