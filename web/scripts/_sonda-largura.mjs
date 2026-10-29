/**
 * Sonda: numa largura de celular, lista os elementos que passam da borda direita — os mais
 * internos primeiro, com a largura e o texto — para achar QUEM empurra a tela para o lado.
 * Uso: node scripts/_sonda-largura.mjs /rota [/outra ...]  (só lê)
 */
import puppeteer from "puppeteer-core";

const WEB = "http://127.0.0.1:3100";
const rotas = process.argv.slice(2);
const nav = await puppeteer.launch({
  executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  headless: "new", args: ["--no-sandbox"],
});
const p = await nav.newPage();
await p.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
await p.goto(`${WEB}/login`, { waitUntil: "networkidle2" });
await new Promise((r) => setTimeout(r, 2500));
await p.type('input[type="email"]', "admin@botane.com.br");
await p.type('input[type="password"]', "botane123");
await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {}), p.click('button[type="submit"]')]);
await new Promise((r) => setTimeout(r, 2000));
if (p.url().includes("/login")) { console.log("NAO ENTROU"); process.exit(1); }
await p.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
for (const rota of rotas) {
  await p.goto(WEB + rota, { waitUntil: "networkidle2" });
  for (let i = 0; i < 30; i++) {
    if (!(await p.evaluate(() => /Carregando/.test(document.querySelector("main")?.innerText ?? "")))) break;
    await new Promise((r) => setTimeout(r, 500));
  }
  await new Promise((r) => setTimeout(r, 800));
  const r = await p.evaluate(() => {
    const W = document.documentElement.clientWidth;
    const fora = [...document.querySelectorAll("main *")].filter((e) => {
      const b = e.getBoundingClientRect();
      if (!(b.width > 0 && b.right > W + 1)) return false;
      // dentro de um contêiner que rola sozinho não conta
      for (let a = e.parentElement; a && a !== document.querySelector("main"); a = a.parentElement) {
        const s = getComputedStyle(a);
        if (/(auto|scroll|hidden)/.test(s.overflowX) && a.getBoundingClientRect().right <= W + 1) return false;
      }
      return true;
    });
    const folhas = fora.filter((e) => !fora.some((f) => f !== e && e.contains(f)));
    return {
      W, scroll: document.documentElement.scrollWidth,
      folhas: folhas.slice(0, 12).map((e) => {
        const b = e.getBoundingClientRect();
        return `${e.tagName.toLowerCase()}.${String(e.className).slice(0, 60)} L=${Math.round(b.left)} R=${Math.round(b.right)} w=${Math.round(b.width)} «${(e.innerText ?? "").trim().slice(0, 40).replace(/\n/g, " ")}»`;
      }),
    };
  });
  console.log(`\n${rota}  viewport ${r.W}  scrollWidth ${r.scroll}`);
  for (const f of r.folhas) console.log("  " + f);
}
await nav.close();
