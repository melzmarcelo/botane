/**
 * Varredura de layout (análise v1.2.0): cada tela no celular e no computador.
 * Anota erros de console, chamadas que falharam, rolagem horizontal e texto quebrado
 * ("undefined", "NaN", "null", "[object"). Só LÊ — não clica em nada que grave.
 *    node scripts/varrer-telas.mjs ["/rota1,/rota2"]  (API 9200 e Next 3100 de pé; sem rotas, todas)
 */
import fs from "node:fs";
import puppeteer from "puppeteer-core";

const API = "http://127.0.0.1:9200", WEB = "http://127.0.0.1:3100";
const PASTA = "scripts/_capturas";
fs.mkdirSync(PASTA, { recursive: true });
const login = await (await fetch(API + "/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: "admin@botane.com.br", senha: "botane123" }) })).json();
const get = async (c) => (await fetch(API + c, { headers: { Authorization: `Bearer ${login.access_token}`, "X-Unidade": "1" } })).json();
const primeiro = async (c) => { try { const d = await get(c); const l = Array.isArray(d) ? d : (d.itens ?? d.lista ?? []); return l[0]?.id; } catch { return null; } };

const rotas = (process.argv[2] ? process.argv[2].split(",") : `/ /ajustes /alertas /auditoria /cadastros /cardapio-vivo /cardapio-vivo/anuncios /cardapio-vivo/atencao /catalogos /cmv /compras /consumo /empresa /estoque /estoque/painel /etiquetas /etiquetas/configuracao /etiquetas/painel /exportacao /fichas /fidelidade/codigos /fidelidade/configuracao /fidelidade/painel /fidelidade/premios /fornecedores /integracoes /inventario /lojas /lojas/1 /lojas/1?aba=whatsapp /meu-consumo /papeis /patrimonio /patrimonio/conferencias /patrimonio/valor /pedidos /pedidos/painel /perfil /precificacao /precificacao/configuracao /precos /producao /produtos /produtos/duplicados /produtos/ean-das-notas /receber /rede /reservas/agenda /reservas/clientes /reservas/configuracoes /reservas/painel /reservas/plano-de-acao /reservas/qrcodes /reservas/salao /transferencias /usuarios /vendas /vendas/lancar /vendas/painel /vendas/por-pessoa /vendas/sem-vinculo /ajuda`.split(" "));
if (!process.argv[2]) {
  for (const [rota, api] of [["/produtos/", "/produtos?limite=1&ativo=true"], ["/fichas/", "/fichas?limite=1"],
    ["/compras/", "/notas?limite=1"], ["/catalogos/", "/catalogos"], ["/patrimonio/", "/patrimonio?limite=1"],
    ["/fornecedores/", "/fornecedores?limite=1"], ["/inventario/", "/inventarios?limite=1"], ["/vendas/", "/vendas?limite=1"]]) {
    const id = await primeiro(api);
    if (id) rotas.push(rota + id);
  }
}

const navegador = await puppeteer.launch({ executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  headless: "new", args: ["--no-sandbox"] });
const p = await navegador.newPage();
let atual = [];
p.on("console", (m) => { if (m.type() === "error") atual.push("console: " + m.text().slice(0, 160)); });
p.on("pageerror", (e) => atual.push("pageerror: " + e.message.slice(0, 160)));
p.on("response", (r) => { const u = r.url(); if (r.status() >= 400 && !u.includes("/_next/") && !u.endsWith("favicon.ico")) atual.push(`http ${r.status()} ${u.replace(API, "API").replace(WEB, "")}`.slice(0, 160)); });
await p.goto(WEB + "/login");
await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); }, login.access_token, login.refresh_token);

const relatorio = [];
// ⚠️ Uma passada por tamanho: trocar o modo celular a cada tela faz o puppeteer recarregar a
// página no meio da navegação, e a captura saía com a tela de login.
for (const [nome, vp] of [["cel", { width: 390, height: 844, isMobile: true, hasTouch: true }], ["pc", { width: 1366, height: 900 }]]) {
  await p.setViewport(vp);
  await p.goto(WEB + "/", { waitUntil: "networkidle2" });
  for (const rota of rotas) {
    atual = [];
    try {
      await p.goto(WEB + rota, { waitUntil: "networkidle2", timeout: 45000 });
    } catch (e) { atual.push("goto: " + e.message.slice(0, 100)); }
    await new Promise((r) => setTimeout(r, 900));
    const info = await p.evaluate(() => {
      const w = document.documentElement.clientWidth;
      const largos = [...document.querySelectorAll("body *")].filter((el) => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.right <= w + 2) return false;
        // dentro de um contêiner que rola sozinho é aceitável
        for (let a = el.parentElement; a; a = a.parentElement) {
          const s = getComputedStyle(a);
          if (/(auto|scroll|hidden)/.test(s.overflowX) && a !== document.body && a !== document.documentElement) return false;
        }
        return true;
      }).slice(0, 3).map((el) => `${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}.${[...el.classList].slice(0, 2).join(".")} (${Math.round(el.getBoundingClientRect().right)}px)`);
      const texto = document.body.innerText;
      const quebrados = (texto.match(/.{0,25}(undefined|NaN|\[object|\bnull\b|Invalid Date).{0,25}/g) || []).slice(0, 3);
      return { rola: document.documentElement.scrollWidth > w + 2, largos, quebrados, titulo: document.querySelector("h1")?.innerText ?? "" };
    });
    const arq = `${PASTA}/${rota.replace(/[/?=]/g, "_") || "_inicio"}-${nome}.png`;
    await p.screenshot({ path: arq, fullPage: nome === "cel" ? false : false });
    const problemas = [...new Set(atual)];
    if (info.rola) problemas.push("ROLAGEM HORIZONTAL: " + info.largos.join(", "));
    info.quebrados.forEach((q) => problemas.push("TEXTO: " + q.replace(/\s+/g, " ")));
    relatorio.push({ rota, nome, titulo: info.titulo, problemas });
    console.log(`${problemas.length ? "!!" : "ok"} ${nome} ${rota} ${problemas.length ? "\n     " + problemas.join("\n     ") : ""}`);
  }
}
fs.writeFileSync(`${PASTA}/relatorio.json`, JSON.stringify(relatorio, null, 1));
await navegador.close();
