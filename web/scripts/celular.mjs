/**
 * A contagem no tamanho de um CELULAR — é para lá que ela foi feita.
 *
 *     node scripts/celular.mjs
 *
 * Confere o que só aparece no aparelho: corte lateral inalcançável (a tela
 * rolando de lado é o defeito clássico) e a foto para olhar o resultado.
 * Emular o tamanho da janela não basta: `isMobile` + `hasTouch` mudam o que o
 * navegador faz com o toque e com o zoom do foco.
 */
import puppeteer from "puppeteer-core";

const WEB = "http://127.0.0.1:3100";
const CHROME =
  process.env.CHROME ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";

const navegador = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox"],
  defaultViewport: { width: 390, height: 844, isMobile: true, hasTouch: true,
                     deviceScaleFactor: 2 },
});
const p = await navegador.newPage();
await p.goto(`${WEB}/login`, { waitUntil: "networkidle2" });
await p.type('input[type="email"]', "admin@botane.com.br");
await p.type('input[type="password"]', "botane123");
await Promise.all([
  p.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {}),
  p.click('button[type="submit"]'),
]);
await new Promise((r) => setTimeout(r, 1500));

const r = await p.evaluate(async () => {
  const t = localStorage.getItem("botane.access");
  const resp = await fetch("http://127.0.0.1:9200/inventarios", {
    headers: { Authorization: `Bearer ${t}` },
  });
  const l = await resp.json();
  return l.find((x) => x.status === "ABERTO") ?? l[0];
});
if (!r) {
  console.log("nenhum inventário para fotografar");
} else {
  await p.goto(`${WEB}/inventario/${r.id}`, { waitUntil: "networkidle2" });
  await new Promise((x) => setTimeout(x, 1600));
  await p.screenshot({ path: "scripts/_fotos/celular-contagem.png" });
  const corte = await p.evaluate(() => ({
    // Corte lateral inalcançável é o defeito clássico de tela de celular.
    rolaDeLado: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    largura: document.documentElement.scrollWidth,
    janela: document.documentElement.clientWidth,
  }));
  console.log("corte lateral:", JSON.stringify(corte));
}
await navegador.close();
