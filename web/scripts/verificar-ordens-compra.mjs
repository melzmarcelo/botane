/**
 * Ordem de compra no navegador (migração 158, pedido do dono de 23/11/2026). Confere:
 *   1. o menu leva à tela;
 *   2. pedir pelo teclado: produto, Tab, quantidade, observação, Enter;
 *   3. pedir de novo o mesmo item pergunta, e "Somar" soma;
 *   4. item fora do cadastro;
 *   5. comprar parte: o resto fica, a parte vai para Comprados;
 *   6. "Voltar à lista" junta de novo;
 *   7. no celular, a página não rola de lado;
 *   8. etapa 2: o link das sugestões abre a janela com o produto sem saldo, e "Pôr na lista" grava;
 *   9. aprovação (migração 165): o pedido da cozinha vai para "Aguardando aprovação", o
 *      administrador aprova (vai para A comprar) e recusa com motivo (vai para Recusados);
 *      e (166) a cozinha vê só os próprios pedidos e não mexe no aprovado.
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
  checar("sem escolher, o pedido sai para esta semana", !!l && /Esta semana/.test(l.texto), l);
  checar("os quatro passos estão na tela", await p.evaluate(() =>
    document.querySelectorAll("#ordem-passos li").length === 4));
  // ⚠️ Cabeçalho e linhas eram grades separadas e a coluna de ações (auto) desalinhava tudo.
  const colunas = await p.evaluate(() => {
    const cab = document.querySelector("#ordem-lista")?.previousElementSibling;
    const li = document.querySelector("#ordem-lista li");
    const x = (e) => [...(e?.children ?? [])].map((c) => Math.round(c.getBoundingClientRect().left));
    return { cab: x(cab), linha: x(li) };
  });
  checar("as colunas do cabeçalho caem em cima das da linha",
    colunas.cab.length === 7 && colunas.cab.every((v, n) => Math.abs(v - colunas.linha[n]) <= 1), colunas);

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
  await clicar(p, '[data-urgencia="HOJE"]');
  const resumo = await p.$eval("#ordem-resumo", (e) => e.innerText);
  checar("o resumo lê o pedido de volta, com a urgência",
    /3 UN de Guardanapo/i.test(resumo) && /Urgente — hoje/.test(resumo), resumo);
  await clicar(p, "#ordem-adicionar");
  await esperarLinha(p, `Guardanapo ${MARCA}`);
  const livre = await linhaCom(p, `Guardanapo ${MARCA}`);
  checar("entra com a etiqueta", !!livre && /fora do cadastro/i.test(livre.texto), livre);
  checar("e com o selo de urgente", !!livre && /Urgente — hoje/.test(livre.texto), livre);
  const posicoes = await p.evaluate((m) => {
    const lis = [...document.querySelectorAll("#ordem-lista li")].map((x) => x.innerText.toUpperCase());
    return { guardanapo: lis.findIndex((t) => t.includes(`GUARDANAPO ${m}`)),
             farinha: lis.findIndex((t) => t.includes(`FARINHA ORDEM ${m}`)) };
  }, MARCA);
  checar("o urgente sobe acima do de esta semana", posicoes.guardanapo >= 0
    && posicoes.guardanapo < posicoes.farinha, posicoes);

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
  // ⚠️ A URL muda por navegação suave, depois da janela fechar: na bateria inteira (next dev
  // lento) a checagem imediata pegava ainda "?sugestoes=1".
  await p.waitForFunction(() => !location.search.includes("sugestoes"), { timeout: 15000 }).catch(() => {});
  checar("e a janela fecha (sai da URL)", !(await p.$("#ordem-sugestoes")) && !p.url().includes("sugestoes"), p.url());

  console.log("9. aprovação (migração 165)");
  const { dados: papeis } = await api("GET", "/papeis", undefined, token);
  const cozinha = papeis.find((x) => x.nome === "Cozinha");
  const emailCozinha = `ordemw${MARCA}@teste.botane`;
  const { status: stU } = await api("POST", "/usuarios", {
    nome: `Cozinha ordem ${MARCA}`, email: emailCozinha, senha: "Teste#12345",
    papeis: [{ id_papel: cozinha.id, id_unidade: 1 }],
  }, token);
  checar("a pessoa da cozinha nasce", stU === 200 || stU === 201, stU);
  const { dados: loginCozinha } = await api("POST", "/auth/login", { email: emailCozinha, senha: "Teste#12345" });
  // ⚠️ Contexto separado: o localStorage é da origem, e a sessão do administrador seria trocada.
  const contexto = await navegador.createBrowserContext();
  const c = await contexto.newPage();
  await c.setViewport({ width: 1366, height: 1000 });
  await c.goto(WEB + "/login", { timeout: 180000 });
  await c.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   loginCozinha.access_token, loginCozinha.refresh_token);
  await c.goto(`${WEB}/compras/ordens`, { waitUntil: "networkidle2", timeout: 180000 });
  await c.waitForSelector("#ordem-form", { timeout: 60000 }).catch(() => {});
  checar("para a cozinha, o botão diz que vai para aprovação",
    /Enviar para aprovação/.test(await c.$eval("#ordem-adicionar", (e) => e.innerText).catch(() => "")));
  async function pedirLivre(pg, texto) {
    // ⚠️ Depois de um pedido, o formulário continua em "fora do cadastro": alternar de novo voltava à busca.
    if (!(await pg.$("#ordem-descricao"))) await clicar(pg, "#ordem-alternar");
    await pg.waitForSelector("#ordem-descricao");
    await pg.waitForFunction(() => document.querySelectorAll("#ordem-um option").length > 1, { timeout: 15000 });
    await pg.type("#ordem-descricao", texto);
    await pg.type("#ordem-quantidade", "2");
    await pg.select("#ordem-um", "UN");
    await clicar(pg, "#ordem-adicionar");
  }
  await pedirLivre(c, `Pano aprovar ${MARCA}`);
  await esperarLinha(c, `Pano aprovar ${MARCA}`);
  await c.waitForFunction(() => location.search.includes("aba=AGUARDANDO"), { timeout: 15000 }).catch(() => {});
  checar("o pedido aparece em Aguardando aprovação", c.url().includes("aba=AGUARDANDO"), c.url());
  const aguarda = await linhaCom(c, `Pano aprovar ${MARCA}`);
  checar("com o selo de aguardando aprovação", !!aguarda && /Aguardando aprovação/.test(aguarda.texto), aguarda);
  checar("e a cozinha não vê o botão Aprovar",
    !(await c.$(`li[data-ordem-item="${aguarda?.id}"] [data-acao="aprovar"]`)));
  await pedirLivre(c, `Vela recusar ${MARCA}`);
  await esperarLinha(c, `Vela recusar ${MARCA}`);
  const recusar = await linhaCom(c, `Vela recusar ${MARCA}`);

  await p.goto(`${WEB}/compras/ordens?aba=AGUARDANDO`, { waitUntil: "networkidle2", timeout: 180000 });
  await esperarLinha(p, `Pano aprovar ${MARCA}`);
  checar("a aba mostra quantos aguardam",
    /Aguardando aprovação \(\d+\)/.test(await p.$eval("#ordem-aba-aguardando", (e) => e.innerText).catch(() => "")));
  await clicar(p, `li[data-ordem-item="${aguarda.id}"] [data-acao="aprovar"]`);
  await p.waitForFunction((id) => !document.querySelector(`li[data-ordem-item="${id}"]`), { timeout: 15000 }, aguarda.id).catch(() => {});
  checar("aprovado, sai de Aguardando", !(await p.$(`li[data-ordem-item="${aguarda.id}"]`)));

  await clicar(p, `li[data-ordem-item="${recusar.id}"] [data-acao="recusar"]`);
  await p.waitForSelector("#ordem-motivo-recusa", { timeout: 10000 }).catch(() => {});
  await p.type("#ordem-motivo-recusa", "tem no freezer 2");
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")]
      .find((x) => x.innerText.trim() === "Recusar" && !x.dataset.acao);
    b?.click();
  });
  await p.waitForFunction((id) => !document.querySelector(`li[data-ordem-item="${id}"]`), { timeout: 15000 }, recusar.id).catch(() => {});
  checar("recusado, sai de Aguardando", !(await p.$(`li[data-ordem-item="${recusar.id}"]`)));

  await clicar(p, "#ordem-aba-comprar");
  await esperarLinha(p, `Pano aprovar ${MARCA}`);
  const aprovado = await linhaCom(p, `Pano aprovar ${MARCA}`);
  checar("o aprovado está em A comprar, com quem aprovou",
    !!aprovado && /aprovado por/i.test(aprovado.texto), aprovado);

  // 🔑 Migração 166: sem ver todos, a cozinha vê só os próprios pedidos e não mexe no aprovado.
  await c.goto(`${WEB}/compras/ordens?aba=A_COMPRAR`, { waitUntil: "networkidle2", timeout: 180000 });
  await esperarLinha(c, `Pano aprovar ${MARCA}`);
  checar("a cozinha é avisada de que vê só os seus pedidos", !!(await c.$("#ordem-so-meus")));
  checar("e não vê o pedido do administrador", !(await linhaCom(c, `Sabão ordem ${MARCA}`)));
  const meuAprovado = await linhaCom(c, `Pano aprovar ${MARCA}`);
  checar("no próprio pedido aprovado, nem Corrigir nem Cancelar",
    !!meuAprovado && !(await c.$(`li[data-ordem-item="${meuAprovado.id}"] [data-acao]`)), meuAprovado);

  await c.goto(`${WEB}/compras/ordens?aba=RECUSADO`, { waitUntil: "networkidle2", timeout: 180000 });
  await esperarLinha(c, `Vela recusar ${MARCA}`);
  const recusado = await linhaCom(c, `Vela recusar ${MARCA}`);
  checar("quem pediu vê a recusa com o motivo",
    !!recusado && /Recusado/.test(recusado.texto) && /tem no freezer 2/.test(recusado.texto), recusado);
  await c.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
  await c.reload({ waitUntil: "networkidle2", timeout: 60000 });
  await esperarLinha(c, `Vela recusar ${MARCA}`);
  const largurasC = await c.evaluate(() => ({ doc: document.documentElement.scrollWidth, tela: window.innerWidth }));
  checar("com as quatro abas, o celular não rola de lado", largurasC.doc <= largurasC.tela, largurasC);
  await contexto.close();
} finally {
  await navegador.close();
  // ⚠️ O comprado também: rodada que falha no meio deixaria a linha em Comprados.
  const { dados: comprados } = await api("GET", `/ordens-compra?status=COMPRADO&busca=${MARCA}&limite=50`, undefined, token);
  if (comprados?.length) await api("POST", "/ordens-compra/voltar", { ids: comprados.map((i) => i.id) }, token);
  for (const situacao of ["A_COMPRAR", "AGUARDANDO"]) {
    const { dados: abertos } = await api("GET", `/ordens-compra?status=${situacao}&busca=${MARCA}&limite=50`, undefined, token);
    for (const i of abertos ?? []) await api("POST", `/ordens-compra/${i.id}/cancelar`, {}, token);
  }
  if (produto?.id) await api("DELETE", `/produtos/${produto.id}`, undefined, token);
  if (minimo?.id) await api("DELETE", `/produtos/${minimo.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
