/**
 * Reservas e Fidelidade VISÍVEIS no site (migração 144): as duas marcas na configuração das
 * reservas e o site sem o botão quando desmarcadas.
 *
 * 🔑 Pedido do dono (30/10/2026): *"criar uma opção se as reservas vão estar visíveis no site.
 * Fazer isto também para a Fidelidade. Caso desmarcado, não aparecerá o botão desta ação."*
 * A configuração é fotografada e devolvida no fim.
 *
 *    node scripts/verificar-portal-no-site.mjs     (API na 9200 e o Next na 3100 de pé)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const API = "http://127.0.0.1:9200";
const WEB = "http://127.0.0.1:3100";
const SITE = `${WEB}/portal`;
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

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
const { dados: antes } = await api("GET", "/reservas/configuracao", undefined, token);
// O cenário: fidelidade ligada e as duas visíveis.
await api("PUT", "/reservas/configuracao", { ...antes, fidelidade_ligada: true, reservas_no_site: true, fidelidade_no_site: true }, token);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"],
                                           defaultViewport: { width: 1280, height: 900 } });
const visiveis = async (p) => {
  await p.goto(`${SITE}/?loja=1`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => document.querySelector("#linha-dias")?.textContent !== "…", { timeout: 20000 }).catch(() => {});
  await esperar(500);
  return p.evaluate(() => ({
    reservar: !!document.querySelector("#ir-reservar") && !document.querySelector("#ir-reservar").hidden
      && getComputedStyle(document.querySelector("#ir-reservar")).display !== "none",
    fidelidade: !!document.querySelector("#ir-fidelidade"),
  }));
};
try {
  const p = await navegador.newPage();
  console.log("1. com as duas marcadas, o site mostra os dois botões");
  let v = await visiveis(p);
  checar("'Reserve sua Mesa' e 'Fidelidade' aparecem", v.reservar && v.fidelidade, v);

  console.log("\n2. a configuração das reservas desmarca as duas");
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  await p.goto(`${WEB}/reservas/configuracoes`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#reservas-no-site", { timeout: 20000 }).catch(() => {});
  checar("as duas opções aparecem, marcadas",
    await p.evaluate(() => document.querySelector("#reservas-no-site")?.checked && document.querySelector("#fidelidade-no-site")?.checked));
  await p.click("#reservas-no-site");
  await p.click("#fidelidade-no-site");
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Salvar")?.click());
  await esperar(1500);
  const { dados: depois } = await api("GET", "/reservas/configuracao", undefined, token);
  checar("gravou as duas desmarcadas", depois.reservas_no_site === false && depois.fidelidade_no_site === false, depois);

  console.log("\n3. o site sem os botões");
  v = await visiveis(p);
  checar("sem 'Reserve sua Mesa' e sem 'Fidelidade'", !v.reservar && !v.fidelidade, v);

  console.log("\n4. só a fidelidade de volta");
  await api("PUT", "/reservas/configuracao", { ...depois, fidelidade_no_site: true }, token);
  v = await visiveis(p);
  checar("a Fidelidade volta e a reserva continua escondida", !v.reservar && v.fidelidade, v);
} finally {
  await navegador.close();
  await api("PUT", "/reservas/configuracao", antes, token);
  await api("PUT", "/unidades/1/parametros", par, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((x) => console.log(`  - ${x}`));
process.exit(falhas.length ? 1 : 0);
