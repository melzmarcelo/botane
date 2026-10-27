/**
 * Quem PRODUZ x a quem o produto pertence (migração 137), no navegador.
 *
 * 🔑 Pedido do dono (27/10/2026): a Confeitaria produz a bolacha que vai para o
 * estoque da Cafeteria. As contas são de `api/tests/smoke_setor_que_produz.py`; aqui
 * se confere a tela: o campo "Produzido por" no cadastro, e a linha "Produz → Entra
 * em" na produção e na agenda.
 *
 *    node scripts/verificar-setor-produz.mjs   (API na 9200 e web na 3100 de pé)
 */
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
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(metodo, caminho, corpo, token) {
  const r = await fetch(API + caminho, {
    method: metodo,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), "X-Unidade": "1" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const t = await r.text();
  return { status: r.status, dados: t ? JSON.parse(t) : null };
}

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;

console.log("0. cenário: Confeitaria produz, Cafeteria guarda");
const { dados: conf } = await api("POST", "/setores", { nome: `CONF TELA ${MARCA}` }, token);
const { dados: cafe } = await api("POST", "/setores", { nome: `CAFE TELA ${MARCA}` }, token);
const { dados: lcafe } = await api("POST", "/locais", { nome: `CAFETERIA TELA ${MARCA}`, tipo: "SECO", id_setor: cafe.id }, token);
const { dados: ins } = await api("POST", "/produtos", { nome: `FARINHA TELA ${MARCA}`, tipo: "INSUMO", um_estoque: "KG", status: "ATIVO" }, token);
const { dados: bol } = await api("POST", "/produtos", {
  nome: `BOLACHA TELA ${MARCA}`, tipo: "PRODUZIDO", um_estoque: "UN", producao_propria: true, status: "ATIVO",
  id_setor: cafe.id, id_setor_producao: conf.id, id_local_padrao: lcafe.id,
}, token);
const { dados: fi } = await api("POST", "/fichas", { id_produto: bol.id, rendimento_qtd: 10, rendimento_um: "UN", porcoes: 10,
  itens: [{ id_insumo: ins.id, qtd_bruta: 1, um: "KG" }] }, token);
await api("POST", `/fichas/${fi.id}/homologar`, {}, token);
checar("o cenário nasce", !!(conf?.id && cafe?.id && lcafe?.id && bol?.id && fi?.id));

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1000 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. o cadastro: Produzido por");
  await p.goto(`${WEB}/produtos/${bol.id}`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#produto-setor-producao", { timeout: 30000 }).catch(() => {});
  await esperar(800);
  const cad = await p.evaluate(() => {
    const s = document.querySelector("#produto-setor-producao");
    return { valor: s?.value,
             texto: document.querySelector("#produto-setor-producao-explica")?.innerText ?? "" };
  });
  checar("o campo vem com a Confeitaria", cad.valor === String(conf.id), cad.valor);
  checar("e explica que a agenda é dela e o pronto entra na Cafeteria",
    cad.texto.includes(`CONF TELA ${MARCA}`) && cad.texto.includes(`CAFETERIA TELA ${MARCA}`), cad.texto.slice(0, 300));

  console.log("\n2. a produção: Produz → Entra em");
  await p.goto(`${WEB}/producao`, { waitUntil: "networkidle2" });
  await p.waitForSelector('input[aria-label="Buscar receita"]', { timeout: 30000 }).catch(() => {});
  await esperar(1000);
  // A aba que abre é a AGENDA. Escolhe o preparo como quem usa: o nome inteiro e sai.
  const escolher = async () => {
    await p.type('input[aria-label="Buscar receita"]', `BOLACHA TELA ${MARCA}`);
    await p.evaluate(() => document.querySelector('input[aria-label="Buscar receita"]')?.blur());
  };
  // ⚠️ A lista de receitas chega DEPOIS do campo: digitar antes deixa o nome sem
  // resolver. Tenta de novo enquanto o seletor de destino seguir travado.
  for (let i = 0; i < 4; i++) {
    await p.evaluate(() => {
      const c = document.querySelector('input[aria-label="Buscar receita"]');
      if (c) c.value = "";
    });
    await p.click('input[aria-label="Buscar receita"]', { clickCount: 3 });
    await p.keyboard.press("Backspace");
    await escolher();
    await esperar(1500);
    const travado = await p.evaluate(() =>
      document.querySelector('select[aria-label="Prateleira de destino"]')?.disabled);
    if (!travado) break;
  }
  await p.waitForSelector("#agenda-pontas", { timeout: 15000 }).catch(() => {});
  await esperar(800);
  const agenda = await p.evaluate(() => document.querySelector("#agenda-pontas")?.innerText
    ?? `[sem a linha; campo: ${document.querySelector('input[aria-label="Buscar receita"]')?.value}; `
       + `destino: ${document.querySelector('select[aria-label="Prateleira de destino"]')?.disabled}]`);
  checar("a agenda diz: Produz Confeitaria → Entra em Cafeteria",
    agenda.includes(`Produz: CONF TELA ${MARCA}`) && agenda.includes(`CAFETERIA TELA ${MARCA}`), agenda);

  await p.evaluate(() => [...document.querySelectorAll("button")]
    .find((x) => /Registrar o que foi feito/i.test(x.textContent ?? ""))?.click());
  await p.waitForSelector("#producao-destino", { timeout: 15000 }).catch(() => {});
  await esperar(800);
  await escolher();
  await p.waitForSelector("#producao-pontas", { timeout: 15000 }).catch(() => {});
  await esperar(800);
  const tela = await p.evaluate(() => ({
    pontas: document.querySelector("#producao-pontas")?.innerText ?? "",
    padrao: document.querySelector("#producao-destino option")?.textContent ?? "",
    valor: document.querySelector("#producao-destino")?.value,
  }));
  checar("a produção diz o mesmo", tela.pontas.includes(`Produz: CONF TELA ${MARCA}`)
    && tela.pontas.includes(`CAFETERIA TELA ${MARCA}`), tela);
  checar("e o 'Entra em' vem vazio: o local do produto",
    /local do produto/i.test(tela.padrao) && tela.valor === "", tela);
} finally {
  await navegador.close();
  await api("DELETE", `/produtos/${bol.id}`, undefined, token);
  await api("DELETE", `/produtos/${ins.id}`, undefined, token);
  await api("DELETE", `/locais/${lcafe.id}`, undefined, token);
  await api("DELETE", `/setores/${conf.id}`, undefined, token);
  await api("DELETE", `/setores/${cafe.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
