/**
 * Ordem de compra no navegador (migração 158, pedido do dono de 23/11/2026). Confere:
 *   1. o menu leva à tela;
 *   2. pedir pelo teclado: produto, Tab, quantidade, observação, Enter;
 *   3. pedir de novo o mesmo item pergunta, e "Somar" soma;
 *   4. item fora do cadastro;
 *   5. comprar parte: o resto fica, a parte vai para Comprados;
 *   6. "Voltar à lista" junta de novo;
 *   7. no celular, a página não rola de lado;
 *   8. etapa 2: o link das sugestões abre a janela com o produto sem saldo, e "Pôr na lista" grava.
 * O que o roteiro cria é cancelado no fim.
 *
 *    node scripts/verificar-ordens-compra.mjs   (API na 9200 e web na 3100 de pé)
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
const codigo = `OCW${MARCA}`;
const { status: st0, dados: produto } = await api("POST", "/produtos", {
  codigo, nome: `Farinha ordem ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", um_compra: "UN",
  fator_compra: 1, status: "ATIVO",
}, token);
checar("o produto de teste nasce", st0 === 201, produto);
const { status: st1, dados: minimo } = await api("POST", "/produtos", {
  codigo: `OCM${MARCA}`, nome: `Sabão ordem ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", um_compra: "UN",
  fator_compra: 1, status: "ATIVO", estoque_minimo: 6,
}, token);
checar("o produto com mínimo nasce", st1 === 201, minimo);

const linhaCom = (p, texto) => p.evaluate((t) => {
  const li = [...document.querySelectorAll("#ordem-lista li")]
    .find((x) => x.innerText.toUpperCase().includes(t.toUpperCase()));
  return li ? { id: Number(li.dataset.ordemItem), texto: li.innerText } : null;
}, texto);
const esperarLinha = (p, texto) => p.waitForFunction((t) =>
  [...document.querySelectorAll("#ordem-lista li")]
    .some((x) => x.innerText.toUpperCase().includes(t.toUpperCase())), { timeout: 30000 }, texto).catch(() => {});
const clicar = async (p, seletor) => {
  await p.waitForSelector(seletor, { timeout: 20000 });
  await p.$eval(seletor, (e) => { e.scrollIntoView({ block: "center", behavior: "instant" }); e.click(); });
};

async function pedirPeloTeclado(p, quantidade, observacao) {
  await p.waitForSelector("#ordem-produto", { timeout: 60000 });
  await p.click("#ordem-produto");
  await p.type("#ordem-produto", codigo);
  await p.keyboard.press("Tab");
  await p.waitForFunction(() => document.querySelector("#ordem-um")?.value === "UN", { timeout: 20000 });
  await p.click("#ordem-quantidade");
  await p.type("#ordem-quantidade", quantidade);
  if (observacao) {
    await p.click("#ordem-observacao");
    await p.type("#ordem-observacao", observacao);
  }
  await p.keyboard.press("Enter");
}

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1000 });
  await p.goto(WEB + "/login", { timeout: 180000 });
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. a tela");
  await p.goto(`${WEB}/compras/ordens`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#ordem-form", { timeout: 60000 }).catch(() => {});
  checar("a tela abre com o formulário", !!(await p.$("#ordem-form")));
  checar("o menu tem a entrada", await p.evaluate(() => !!document.querySelector('a[href="/compras/ordens"]')));

  console.log("2. pedir pelo teclado");
  await pedirPeloTeclado(p, "10", "a de sempre");
  await esperarLinha(p, `Farinha ordem ${MARCA}`);
  let l = await linhaCom(p, `Farinha ordem ${MARCA}`);
  checar("a linha aparece com quantidade e observação",
    !!l && /10/.test(l.texto) && l.texto.includes("a de sempre"), l);

  console.log("3. repetido");
  await pedirPeloTeclado(p, "2");
  await p.waitForSelector("#ordem-somar", { timeout: 15000 }).catch(() => {});
  checar("pedir de novo pergunta", !!(await p.$("#ordem-somar")));
  await clicar(p, "#ordem-somar");
  await p.waitForFunction((m) => [...document.querySelectorAll("#ordem-lista li")]
    .some((x) => x.innerText.toUpperCase().includes(`FARINHA ORDEM ${m}`) && /\b12\b/.test(x.innerText)),
    { timeout: 15000 }, MARCA).catch(() => {});
  l = await linhaCom(p, `Farinha ordem ${MARCA}`);
  checar("Somar vira 12 na mesma linha", !!l && /\b12\b/.test(l.texto), l);

  console.log("4. fora do cadastro");
  await clicar(p, "#ordem-alternar");
  await p.waitForSelector("#ordem-descricao");
  await p.waitForFunction(() => document.querySelectorAll("#ordem-um option").length > 1, { timeout: 15000 });
  await p.type("#ordem-descricao", `Guardanapo ${MARCA}`);
  await p.type("#ordem-quantidade", "3");
  await p.select("#ordem-um", "UN");
  await clicar(p, "#ordem-adicionar");
  await esperarLinha(p, `Guardanapo ${MARCA}`);
  const livre = await linhaCom(p, `Guardanapo ${MARCA}`);
  checar("entra com a etiqueta", !!livre && /fora do cadastro/i.test(livre.texto), livre);

  console.log("5. comprar parte");
  await clicar(p, `li[data-ordem-item="${l.id}"] [data-acao="comprei"]`);
  const campo = `[data-ordem-qtd="${l.id}"]`;
  await p.waitForSelector(campo);
  await p.focus(campo);
  await p.keyboard.type("7");
  await p.waitForFunction(() => /continuam na lista/.test(document.body.innerText), { timeout: 5000 }).catch(() => {});
  checar("a janela diz quanto continua na lista",
    await p.evaluate(() => /5\s+UN continuam na lista/.test(document.body.innerText)));
  await clicar(p, "#ordem-confirmar-compra");
  await p.waitForFunction((id) => {
    const li = document.querySelector(`li[data-ordem-item="${id}"]`);
    return li && /\b5\b/.test(li.innerText);
  }, { timeout: 15000 }, l.id).catch(() => {});
  const resto = await linhaCom(p, `Farinha ordem ${MARCA}`);
  checar("os 5 continuam em A comprar", !!resto && /\b5\b/.test(resto.texto), resto);
  checar("o aviso oferece desfazer", await p.evaluate(() => /desfazer/i.test(document.body.innerText)));

  await clicar(p, "#ordem-aba-comprados");
  await p.waitForFunction(() => !document.querySelector("#ordem-form"), { timeout: 10000 }).catch(() => {});
  // ⚠️ Espera a linha DOS 7: a lista da aba anterior não pode aparecer aqui nem por um instante.
  await p.waitForFunction((m) => [...document.querySelectorAll("#ordem-lista li")]
    .some((x) => x.innerText.toUpperCase().includes(`FARINHA ORDEM ${m}`) && /comprado por/i.test(x.innerText)),
    { timeout: 15000 }, MARCA).catch(() => {});
  const comprado = await linhaCom(p, `Farinha ordem ${MARCA}`);
  checar("os 7 estão em Comprados", !!comprado && /\b7\b/.test(comprado.texto) && /comprado por/i.test(comprado.texto), comprado);

  console.log("6. voltar à lista");
  await clicar(p, `li[data-ordem-item="${comprado.id}"] [data-acao="voltar"]`);
  await p.waitForFunction((id) => !document.querySelector(`li[data-ordem-item="${id}"]`), { timeout: 15000 }, comprado.id).catch(() => {});
  await clicar(p, "#ordem-aba-comprar");
  await p.waitForFunction((id) => {
    const li = document.querySelector(`li[data-ordem-item="${id}"]`);
    return li && /\b12\b/.test(li.innerText);
  }, { timeout: 15000 }, l.id).catch(() => {});
  const junto = await linhaCom(p, `Farinha ordem ${MARCA}`);
  checar("volta a ser uma linha de 12", !!junto && /\b12\b/.test(junto.texto), junto);
  // ⚠️ A URL muda por navegação suave, depois da lista: recarregar antes disso volta à aba velha.
  await p.waitForFunction(() => !location.search.includes("aba=COMPRADO"), { timeout: 15000 }).catch(() => {});
  checar("a aba A comprar fica no endereço", !p.url().includes("aba=COMPRADO"), p.url());

  console.log("7. celular");
  await p.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
  await p.reload({ waitUntil: "networkidle2", timeout: 60000 });
  await esperarLinha(p, `Farinha ordem ${MARCA}`);
  await esperar(300);
  const larguras = await p.evaluate(() => ({ doc: document.documentElement.scrollWidth, tela: window.innerWidth }));
  checar("a página não rola de lado", larguras.doc <= larguras.tela, larguras);
  const alturaBotao = await p.evaluate(() =>
    document.querySelector('#ordem-lista [data-acao="comprei"]')?.getBoundingClientRect().height ?? 0);
  checar("o botão Comprei tem alvo de toque", alturaBotao >= 36, {
    alturaBotao, url: p.url(),
    lista: await p.evaluate(() => document.querySelector("#ordem-lista")?.innerText.slice(0, 160) ?? "(sem lista)"),
    abas: await p.evaluate(() => document.querySelector("#ordem-aba-comprar")?.className),
  });

  console.log("8. abaixo do mínimo (etapa 2)");
  await p.setViewport({ width: 1366, height: 1000 });
  // ⚠️ Sem saldo nenhum de propósito: era o caso que o painel não mostrava.
  await p.goto(`${WEB}/compras/ordens?sugestoes=1`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector(`li[data-sugestao="${minimo.id}"]`, { timeout: 30000 }).catch(() => {});
  const sug = await p.evaluate((id) => {
    const li = document.querySelector(`li[data-sugestao="${id}"]`);
    return li ? { texto: li.innerText, qtd: li.querySelector("[data-sugestao-qtd]")?.value,
                  marcado: li.querySelector("[data-marcar]")?.checked } : null;
  }, minimo.id);
  checar("o link abre direto nas sugestões, com o produto sem saldo", !!sug, sug);
  checar("vem marcado, com a falta inteira: 6", !!sug && sug.marcado && sug.qtd === "6", sug);
  // Só o de teste vai para a lista: a base local tem outros abaixo do mínimo.
  await p.evaluate((id) => {
    for (const li of document.querySelectorAll("#ordem-sugestoes li[data-sugestao]")) {
      const cx = li.querySelector("[data-marcar]");
      if (cx && cx.checked !== (li.dataset.sugestao === String(id))) cx.click();
    }
  }, minimo.id);
  await p.waitForFunction(() => /Pôr 1 na lista/.test(document.querySelector("#ordem-por-na-lista")?.innerText ?? ""),
    { timeout: 5000 }).catch(() => {});
  await clicar(p, "#ordem-por-na-lista");
  await esperarLinha(p, `Sabão ordem ${MARCA}`);
  const posto = await linhaCom(p, `Sabão ordem ${MARCA}`);
  checar("entra em A comprar com 6", !!posto && /\b6\b/.test(posto.texto), posto);
  checar("e a janela fecha (sai da URL)", !(await p.$("#ordem-sugestoes")) && !p.url().includes("sugestoes"), p.url());
} finally {
  await navegador.close();
  // ⚠️ O comprado também: rodada que falha no meio deixaria a linha em Comprados.
  const { dados: comprados } = await api("GET", `/ordens-compra?status=COMPRADO&busca=${MARCA}&limite=50`, undefined, token);
  if (comprados?.length) await api("POST", "/ordens-compra/voltar", { ids: comprados.map((i) => i.id) }, token);
  const { dados: abertos } = await api("GET", `/ordens-compra?status=A_COMPRAR&busca=${MARCA}&limite=50`, undefined, token);
  for (const i of abertos ?? []) await api("POST", `/ordens-compra/${i.id}/cancelar`, {}, token);
  if (produto?.id) await api("DELETE", `/produtos/${produto.id}`, undefined, token);
  if (minimo?.id) await api("DELETE", `/produtos/${minimo.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
