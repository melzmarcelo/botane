/** Capturas do site do cliente (análise v1.2.0), no celular e no computador. Só lê.
 *    node scripts/varrer-site.mjs   (Next 3100 de pé; grava em scripts/_capturas/site) */
import fs from "node:fs";
import puppeteer from "puppeteer-core";
const WEB = "http://127.0.0.1:3100";
const PASTA = "scripts/_capturas/site";
fs.mkdirSync(PASTA, { recursive: true });
const b = await puppeteer.launch({ executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", headless: "new" });
for (const [nome, vp] of [["cel", { width: 390, height: 844, isMobile: true, hasTouch: true }], ["pc", { width: 1366, height: 900 }]]) {
  const p = await b.newPage();
  await p.setViewport(vp);
  const erros = [];
  p.on("console", (m) => { if (m.type() === "error") erros.push(m.text().slice(0, 150)); });
  p.on("pageerror", (e) => erros.push("pageerror " + e.message.slice(0, 150)));
  await p.goto(`${WEB}/portal/?loja=1`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1200));
  await p.screenshot({ path: `${PASTA}/inicio-${nome}.png`, fullPage: true });
  const telas = await p.evaluate(() => [...document.querySelectorAll("[data-tela]")].map((t) => t.dataset.tela));
  const botoes = await p.evaluate(() => [...document.querySelectorAll("button, a")].filter((x) => x.offsetParent).map((x) => (x.id ? "#" + x.id + " " : "") + x.innerText.trim().slice(0, 30)).filter(Boolean).slice(0, 30));
  console.log(nome, "telas:", telas.join(","), "\n botoes:", botoes.join(" | "));
  for (const id of ["#ir-reservar", "#ir-cardapios", "#ir-fidelidade"]) {
    if (!(await p.$(id))) { console.log(nome, "sem", id); continue; }
    await p.goto(`${WEB}/portal/?loja=1`, { waitUntil: "networkidle2" });
    await new Promise((r) => setTimeout(r, 800));
    await p.$eval(id, (x) => x.click()).catch(() => {});
    await new Promise((r) => setTimeout(r, 1500));
    await p.screenshot({ path: `${PASTA}/${id.slice(1)}-${nome}.png`, fullPage: true });
    const rola = await p.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2);
    console.log(nome, id, rola ? "ROLAGEM HORIZONTAL" : "ok");
  }
  console.log(nome, "erros:", erros.join(" || ") || "nenhum");
  await p.close();
}
await b.close();
