/**
 * Auditoria visual: passa por todas as telas (computador e celular), fotografa a página
 * inteira e mede o que se mede sem olho: erros de JS, rolagem horizontal no celular,
 * tempo até carregar, quantos "carregando" sobraram, texto pequeno demais e alvos de toque
 * pequenos. Só navega e lê — não grava nada.
 *
 * Uso: node scripts/_auditoria.mjs  →  scripts/_fotos/auditoria/*.png + _auditoria.json
 */
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const CHROME =
  process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const WEB = "http://127.0.0.1:3100";
const API = "http://127.0.0.1:9200";
const SAIDA = new URL("./_fotos/auditoria/", import.meta.url);
fs.mkdirSync(SAIDA, { recursive: true });

const ESTATICAS = [
  "/", "/alertas", "/produtos", "/produtos/duplicados", "/produtos/ean-das-notas",
  "/produtos/reclassificar", "/fornecedores", "/cadastros", "/fichas", "/estoque",
  "/estoque/painel", "/ajustes", "/producao", "/inventario", "/inventario/novo",
  "/transferencias", "/compras", "/compras/nova", "/vendas", "/vendas/lancar",
  "/vendas/painel", "/vendas/motivos", "/vendas/por-pessoa", "/vendas/sem-vinculo",
  "/receber", "/consumo", "/meu-consumo", "/cmv", "/precificacao",
  "/precificacao/configuracao", "/precos", "/etiquetas", "/etiquetas/painel",
  "/etiquetas/configuracao", "/patrimonio", "/patrimonio/conferencias",
  "/patrimonio/importar", "/patrimonio/valor", "/catalogos", "/cardapio-vivo",
  "/cardapio-vivo/anuncios", "/cardapio-vivo/atencao", "/cardapio-vivo/testes",
  "/pedidos", "/pedidos/painel", "/reservas/agenda", "/reservas/clientes",
  "/reservas/configuracoes", "/reservas/qrcodes", "/reservas/salao",
  "/fidelidade/painel", "/fidelidade/codigos", "/fidelidade/premios",
  "/fidelidade/configuracao", "/rede", "/integracoes", "/exportacao", "/lojas",
  "/usuarios", "/papeis", "/auditoria", "/empresa", "/perfil",
];
// As do celular: o que se usa em pé, no balcão, na cozinha e no estoque.
const CELULAR = new Set([
  "/", "/alertas", "/produtos", "/fichas", "/estoque", "/estoque/painel", "/producao",
  "/inventario", "/vendas/lancar", "/vendas/painel", "/cmv", "/etiquetas", "/patrimonio",
  "/patrimonio/conferencias", "/pedidos/painel", "/reservas/agenda", "/meu-consumo",
]);

const login = await (await fetch(`${API}/auth/login`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: "admin@botane.com.br", senha: "botane123" }),
})).json();
const tk = login.access_token ?? login.token;
const get = async (c) => {
  const r = await fetch(API + c, { headers: { Authorization: `Bearer ${tk}` } });
  return r.ok ? r.json() : null;
};
const primeiro = (x) => (Array.isArray(x) ? x : x?.lotes ?? x?.itens ?? x?.items ?? x?.dados ?? [])[0];
const detalhes = [];
for (const [rota, caminho, campo = "id"] of [
  ["/produtos/", "/produtos?por_pagina=5&status=ATIVO&tipo=PRODUZIDO"],
  ["/produtos/", "/produtos?por_pagina=5&tipo=INSUMO"],
  ["/fichas/", "/fichas?por_pagina=5"],
  ["/compras/", "/notas?por_pagina=5"],
  ["/vendas/", "/vendas?por_pagina=5"],
  ["/inventario/", "/inventarios"],
  ["/catalogos/", "/catalogos"],
  ["/patrimonio/conferencias/", "/patrimonio/conferencias"],
  ["/patrimonio/", "/patrimonio?por_pagina=5"],
  ["/receber/lotes/", "/receber/lotes?por_pagina=5"],
]) {
  const x = primeiro(await get(caminho).catch(() => null));
  if (x?.[campo]) detalhes.push(rota + x[campo]);
}

const navegador = await puppeteer.launch({
  executablePath: CHROME, headless: "new",
  args: ["--no-sandbox", "--window-size=1440,1000"], protocolTimeout: 120_000,
});
const p = await navegador.newPage();
const erros = [];
p.on("pageerror", (e) => erros.push(`JS: ${String(e).slice(0, 160)}`));
p.on("console", (m) => {
  if (m.type() === "error" && !/favicon|manifest|Download the React/i.test(m.text())) {
    erros.push(`console: ${m.text().slice(0, 160)}`);
  }
});
await p.setViewport({ width: 1440, height: 1000 });
await p.goto(`${WEB}/login`, { waitUntil: "networkidle2" });
await p.type('input[type="email"]', "admin@botane.com.br");
await p.type('input[type="password"]', "botane123");
await Promise.all([
  p.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {}),
  p.click('button[type="submit"]'),
]);
await new Promise((r) => setTimeout(r, 1500));

const nome = (rota, sufixo) =>
  (rota === "/" ? "inicio" : rota.slice(1).replace(/\//g, "_")) + sufixo + ".png";

async function medir() {
  return p.evaluate(() => {
    const doc = document.documentElement;
    const visiveis = [...document.querySelectorAll("body *")].filter((e) => {
      const r = e.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden";
    });
    const comTexto = visiveis.filter((e) =>
      [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 2));
    const pequenos = comTexto.filter((e) => parseFloat(getComputedStyle(e).fontSize) < 12);
    const alvos = visiveis.filter((e) => e.matches("button, a, input, select, [role=button]"));
    const alvosPequenos = alvos.filter((e) => {
      const r = e.getBoundingClientRect();
      return r.height < 32 || r.width < 32;
    });
    const largos = visiveis.filter((e) => e.getBoundingClientRect().right > doc.clientWidth + 2)
      .filter((e) => !e.closest(".grid-rolante, [class*=overflow-x], [class*=overflow-auto]"))
      .slice(0, 5).map((e) => `${e.tagName.toLowerCase()}.${String(e.className).slice(0, 40)}`);
    return {
      h1: document.querySelector("h1")?.innerText ?? null,
      altura: doc.scrollHeight,
      rolagemHorizontal: doc.scrollWidth > doc.clientWidth + 2,
      largos,
      carregando: [...document.querySelectorAll("*")].filter((e) =>
        /^carregando/i.test(e.textContent?.trim() ?? "") && e.children.length === 0).length,
      textoPequeno: pequenos.length,
      exemplosPequenos: [...new Set(pequenos.slice(0, 6).map((e) => e.innerText.trim().slice(0, 40)))],
      alvos: alvos.length,
      alvosPequenos: alvosPequenos.length,
      botoes: [...document.querySelectorAll("main button, main a.botao, main [class*=botao]")]
        .map((b) => b.innerText.trim()).filter(Boolean).slice(0, 25),
      vazio: /nenhum|nada (aqui|ainda)|sem registros/i.test(document.querySelector("main")?.innerText ?? ""),
    };
  });
}

const resultado = [];
async function visitar(rota, largura, sufixo) {
  erros.length = 0;
  await p.setViewport({ width: largura, height: largura < 600 ? 844 : 1000, isMobile: largura < 600, hasTouch: largura < 600 });
  const t0 = Date.now();
  try {
    await p.goto(WEB + rota, { waitUntil: "networkidle2", timeout: 60000 });
  } catch (e) {
    resultado.push({ rota, largura, falha: String(e).slice(0, 120) });
    return;
  }
  // espera o "Carregando" sumir (até 15 s)
  for (let i = 0; i < 30; i++) {
    const ainda = await p.evaluate(() => /Carregando/.test(document.querySelector("main")?.innerText ?? ""));
    if (!ainda) break;
    await new Promise((r) => setTimeout(r, 500));
  }
  await new Promise((r) => setTimeout(r, 800));
  const ms = Date.now() - t0;
  const m = await medir();
  await p.screenshot({ path: fileURLToPath(new URL(nome(rota, sufixo), SAIDA)), fullPage: true,
                       captureBeyondViewport: true }).catch((e) => console.log("foto falhou", String(e).slice(0, 100)));
  resultado.push({ rota, largura, ms, ...m, erros: [...erros] });
  console.log(`${largura < 600 ? "cel" : "pc "} ${rota.padEnd(32)} ${String(ms).padStart(6)} ms ${m.rolagemHorizontal ? "ROLA-H " : ""}${erros.length ? "ERROS " + erros.length : ""}`);
}

for (const rota of [...ESTATICAS, ...detalhes]) await visitar(rota, 1440, "");
for (const rota of [...CELULAR, ...detalhes.slice(0, 2)]) await visitar(rota, 390, "--cel");

fs.writeFileSync(new URL("_auditoria.json", SAIDA), JSON.stringify(resultado, null, 1));
await navegador.close();
console.log(`\n${resultado.length} telas; JSON em _fotos/auditoria/_auditoria.json`);
