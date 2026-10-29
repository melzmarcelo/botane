/**
 * Os itens de gravidade média da auditoria de 29/10/2026, no navegador. Só lê: nada é gravado.
 *
 * - o menu "Mais" abre, e a janela que nasce de um item dele fica POR CIMA da barra do topo
 *   (com o `z-index` no menu fechado ela ficava presa atrás dela);
 * - Notas de entrada em colunas no computador, com o cabeçalho;
 * - Patrimônio com abas (Bens · Conferência · Valor), a do lugar marcada;
 * - Alertas: vencidos e a vencer em quadros separados;
 * - Contas a receber: a busca por nome recorta a lista;
 * - Perfil: a tabela de chaves usa mais largura que o formulário.
 *
 *    node scripts/verificar-auditoria-medias.mjs   (API na 9200 e web na 3100 de pé)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const WEB = process.env.BOTANE_WEB ?? "http://127.0.0.1:3100";
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
const p = await navegador.newPage();
await p.setViewport({ width: 1280, height: 900 });

async function ir(rota) {
  await p.goto(WEB + rota, { waitUntil: "networkidle2" });
  for (let i = 0; i < 30; i++) {
    if (!(await p.evaluate(() => /Carregando/.test(document.querySelector("main")?.innerText ?? "")))) break;
    await esperar(500);
  }
  await esperar(800);
}

try {
  await p.goto(`${WEB}/login`, { waitUntil: "networkidle2" });
  // ⚠️ Digitar antes da hidratação perde o texto e a sonda mede a tela de login.
  await esperar(2500);
  await p.type('input[type="email"]', "admin@botane.com.br");
  await p.type('input[type="password"]', "botane123");
  await Promise.all([p.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {}),
                     p.click('button[type="submit"]')]);
  await esperar(2000);

  console.log("1. Notas de entrada: o menu Mais e as colunas");
  await ir("/compras");
  const antes = await p.evaluate(() => ({
    menu: !!document.querySelector("main .menu-mais"),
    fechado: getComputedStyle(document.querySelector("main .menu-mais") ?? document.body).visibility,
    cabecalho: [...document.querySelectorAll("main li")].some((l) =>
      getComputedStyle(l).display === "grid" && /emissão/i.test(l.innerText) && /situação/i.test(l.innerText)),
  }));
  checar("há o menu Mais, fechado", antes.menu && antes.fechado === "hidden", antes);
  checar("a lista tem colunas com cabeçalho no computador", antes.cabecalho, antes);
  // ⚠️ `main`: o menu do usuário, no topo, também é `aria-haspopup`.
  await p.click('main button[aria-haspopup="menu"]');
  await esperar(300);
  const aberto = await p.evaluate(() => getComputedStyle(document.querySelector("main .menu-mais")).visibility);
  checar("clicado, ele abre", aberto === "visible", aberto);
  await p.evaluate(() => [...document.querySelectorAll("main .menu-mais > button")]
    .find((b) => b.textContent?.trim() === "Relatório de compras")?.click());
  await p.waitForSelector('[role="dialog"]', { timeout: 15000 }).catch(() => {});
  await esperar(500);
  const janela = await p.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    const h = d?.querySelector("h2");
    const r = h?.getBoundingClientRect();
    const noPonto = r ? document.elementFromPoint(r.left + 5, r.top + r.height / 2) : null;
    return {
      titulo: h?.textContent ?? "",
      visivel: d ? getComputedStyle(d).visibility : "",
      menu: getComputedStyle(document.querySelector("main .menu-mais")).visibility,
      porCima: !!(noPonto && d?.contains(noPonto)),
    };
  });
  checar("o item abre a janela de Imprimir e o menu fecha",
    /Compras/.test(janela.titulo) && janela.visivel === "visible" && janela.menu === "hidden", janela);
  checar("e a janela fica por cima de tudo (o título é o que está no ponto)", janela.porCima, janela);

  console.log("\n2. Patrimônio em abas");
  await ir("/patrimonio");
  const abas = await p.evaluate(() => ({
    abas: [...document.querySelectorAll('nav[aria-label="Partes do patrimônio"] a')].map((a) => a.textContent),
    atual: document.querySelector('nav[aria-label="Partes do patrimônio"] a[aria-current="page"]')?.textContent,
  }));
  checar("Bens, Conferência e Valor, com Bens marcada",
    abas.abas.join("|") === "Bens|Conferência|Valor" && abas.atual === "Bens", abas);
  await p.click("#patrimonio-valor");
  await p.waitForFunction(() => location.pathname === "/patrimonio/valor", { timeout: 15000 }).catch(() => {});
  await esperar(800);
  const noValor = await p.evaluate(() =>
    document.querySelector('nav[aria-label="Partes do patrimônio"] a[aria-current="page"]')?.textContent);
  checar("a aba Valor leva à tela e fica marcada lá", noValor === "Valor", noValor);

  console.log("\n3. Alertas: vencidos à parte");
  await ir("/alertas");
  const quadros = await p.evaluate(() => [...document.querySelectorAll("main h2, main h3")].map((h) => h.textContent?.trim()));
  checar("há o quadro do que vence, e nenhum chamado só Vencendo",
    quadros.includes("Vencem nos próximos dias") && !quadros.includes("Vencendo"), quadros);
  const vencidos = await p.evaluate(() => {
    const h = [...document.querySelectorAll("main h2, main h3")].find((x) => x.textContent?.trim() === "Vencem nos próximos dias");
    const cartao = h?.closest(".cartao");
    return [...(cartao?.querySelectorAll("td") ?? [])].filter((td) => /venceu há/.test(td.textContent ?? "")).length;
  });
  checar("e nele não entra lote já vencido", vencidos === 0, vencidos);

  console.log("\n4. Contas a receber: a busca por nome");
  await ir("/receber");
  const total = await p.evaluate(() => document.querySelectorAll("#receber-em-aberto tbody tr").length);
  if (total > 1) {
    const nome = await p.evaluate(() => document.querySelector("#receber-em-aberto tbody tr a")?.textContent?.trim() ?? "");
    await p.type("#receber-busca", nome);
    await esperar(500);
    const depois = await p.evaluate(() => ({
      linhas: document.querySelectorAll("#receber-em-aberto tbody tr").length,
      botao: document.querySelector("#receber-gerar")?.textContent?.trim() ?? "",
    }));
    checar("o nome recorta a lista", depois.linhas >= 1 && depois.linhas < total, { total, ...depois });
    checar("e o botão do lote diz que é só a busca (não todos)",
      !depois.botao || /da busca/.test(depois.botao), depois.botao);
  } else {
    checar("a busca por nome está na tela", await p.evaluate(() => !!document.querySelector("#receber-busca")));
  }

  console.log("\n5. Perfil: a tabela de chaves com largura");
  await ir("/perfil");
  const larguras = await p.evaluate(() => {
    const form = document.querySelector("main form")?.closest(".cartao")?.getBoundingClientRect().width ?? 0;
    const tabela = [...document.querySelectorAll("main table")].at(-1)?.closest(".cartao")?.getBoundingClientRect().width ?? 0;
    return { form, tabela };
  });
  checar("o cartão das chaves é mais largo que o do formulário",
    !larguras.tabela || larguras.tabela > larguras.form + 100, larguras);
} finally {
  await navegador.close();
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
