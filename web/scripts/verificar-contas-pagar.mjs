/**
 * Contas a pagar no navegador (migração 163, módulo Financeiro, 24/11/2026). Confere:
 *   1. o menu tem o grupo Financeiro, com Contas a receber e Contas a pagar;
 *   2. a Nova conta: pessoa pela busca, descrição, valor → entra em A pagar;
 *   3. a equipe do dia: acrescentar pessoa, valor, lançar;
 *   4. agrupar por pessoa e "Pagar todas" com comprovante → vai para Pagos com Comprovante;
 *   5. o comprovante abre (rota autenticada);
 *   6. agendar para hoje com baixa automática → aparece em Pagos, automática;
 *   7. o cadastro de Pessoas tem a chave Pix; no celular a página não rola de lado;
 *   8. etapa 3 (167): parcelar mostra a prévia e lança "parcela 1/3"; a conta fixa que vence hoje
 *      nasce na hora em A pagar, marcada; encerrar cancelando as em aberto tira a conta da lista.
 *   9. etapa 4: o fluxo de caixa está no menu, mostra a conta em aberto no dia do vencimento, a
 *      previsão liga e desliga, e o saldo inicial sobe o acumulado; no celular não rola de lado.
 * O que o roteiro cria é estornado e cancelado no fim.
 *
 *    node scripts/verificar-contas-pagar.mjs   (API na 9200 e web na 3100 de pé)
 */
import { writeFileSync } from "node:fs";
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const API = process.env.BOTANE_API ?? "http://127.0.0.1:9200";
const WEB = process.env.BOTANE_WEB ?? "http://127.0.0.1:3100";
const MARCA = String(Date.now()).slice(-6);
const HOJE = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
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

const FOTO = "scripts/_fotos/comprovante-teste.png";
writeFileSync(FOTO, Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64"));

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;
const nomes = [`FREELA TELA A ${MARCA}`, `FREELA TELA B ${MARCA}`];
const ids = [];
for (const nome of nomes) {
  const { dados } = await api("POST", "/fornecedores", { nome, fornecedor: false, chave_pix: `${MARCA}@pix.teste` }, token);
  ids.push(dados?.id);
}
checar("os dois freelancers de teste nascem", ids.every(Boolean), ids);

async function linhaDe(p, texto) {
  return p.evaluate((t) => [...document.querySelectorAll("[data-conta]")]
    .filter((li) => li.innerText.toUpperCase().includes(t.toUpperCase()))
    .map((li) => ({ id: li.dataset.conta, texto: li.innerText })), texto);
}

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1000 });
  await p.goto(WEB + "/login", { timeout: 180000 });
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. o menu");
  await p.goto(`${WEB}/financeiro/pagar`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#pagar-resumo", { timeout: 60000 }).catch(() => {});
  const menu = await p.evaluate(() => ({
    grupo: [...document.querySelectorAll("aside .menu-grupo")].some((g) => /^financeiro/i.test(g.innerText.trim())),
    pagar: !!document.querySelector('aside a[href="/financeiro/pagar"]'),
    receber: !!document.querySelector('aside a[href="/receber"]'),
  }));
  checar("o grupo Financeiro tem Contas a receber e Contas a pagar", menu.grupo && menu.pagar && menu.receber, menu);
  checar("a tela abre com o resumo", !!(await p.$("#pagar-resumo")));

  console.log("2. nova conta");
  await p.click("#pagar-nova");
  await p.waitForSelector("#conta-pessoa", { timeout: 10000 });
  await p.click("#conta-pessoa");
  await p.type("#conta-pessoa", nomes[0]);
  await p.keyboard.press("Tab");
  await esperar(800);
  await p.type("#conta-descricao", `Diária tela ${MARCA}`);
  await p.click("#conta-valor", { clickCount: 3 });
  await p.type("#conta-valor", "150,00");
  await p.click("#conta-salvar");
  await p.waitForFunction((m) => [...document.querySelectorAll("[data-conta]")].some((li) => li.innerText.includes(m)),
    { timeout: 20000 }, `Diária tela ${MARCA}`).catch(() => {});
  const nova = await linhaDe(p, `Diária tela ${MARCA}`);
  checar("a conta entra em A pagar, com o valor", nova.length === 1 && /150,00/.test(nova[0].texto), nova);

  console.log("3. a equipe do dia");
  await p.click("#pagar-equipe");
  await p.waitForSelector("#equipe-pessoa", { timeout: 10000 });
  await p.click("#equipe-pessoa");
  await p.type("#equipe-pessoa", nomes[1]);
  await p.keyboard.press("Tab");
  await p.waitForSelector("[data-equipe-pessoa] [data-equipe-valor]", { timeout: 10000 }).catch(() => {});
  await p.type("[data-equipe-pessoa] [data-equipe-valor]", "120");
  await p.click("#equipe-lancar");
  await p.waitForFunction((m) => [...document.querySelectorAll("[data-conta]")].some((li) => li.innerText.includes(m)),
    { timeout: 20000 }, nomes[1]).catch(() => {});
  const daEquipe = await linhaDe(p, nomes[1]);
  checar("a equipe lança a conta da pessoa", daEquipe.length === 1 && /120,00/.test(daEquipe[0].texto), daEquipe);

  console.log("4. agrupar e pagar todas com comprovante");
  await p.click("#pagar-por-pessoa");
  await p.waitForSelector(`[data-grupo-pessoa="${nomes[0]}"]`, { timeout: 15000 }).catch(() => {});
  checar("agrupa por pessoa", !!(await p.$(`[data-grupo-pessoa="${nomes[0]}"]`)));
  await p.click(`[data-grupo-pessoa="${nomes[0]}"] [data-acao="pagar-todas"]`);
  await p.waitForSelector("#pagar-confirmar", { timeout: 10000 });
  const pixNaJanela = await p.evaluate((m) => document.body.innerText.includes(`${m}@pix.teste`), MARCA);
  checar("a janela de pagar mostra a chave Pix", pixNaJanela);
  await (await p.$("#pagar-comprovante")).uploadFile(FOTO);
  await p.click("#pagar-confirmar");
  await p.waitForFunction(() => !document.querySelector("#pagar-confirmar"), { timeout: 20000 }).catch(() => {});
  await p.click('[data-aba-pagar="PAGO"]');
  await p.waitForFunction((m) => [...document.querySelectorAll("[data-conta]")].some((li) => li.innerText.includes(m)),
    { timeout: 20000 }, `Diária tela ${MARCA}`).catch(() => {});
  const paga = await linhaDe(p, `Diária tela ${MARCA}`);
  checar("vai para Pagos com o botão Comprovante", paga.length === 1 && /Comprovante/.test(paga[0].texto), paga);

  console.log("5. o comprovante");
  await p.evaluate((id) => document.querySelector(`[data-conta="${id}"] [data-acao="comprovante"]`)?.click(), paga[0]?.id);
  await p.waitForSelector("#comprovante-quadro", { timeout: 15000 }).catch(() => {});
  const quadro = await p.$eval("#comprovante-quadro", (i) => i.src.slice(0, 5)).catch(() => "");
  checar("abre por blob (rota autenticada)", quadro === "blob:", quadro);
  // ⚠️ Pelo botão, não pelo Escape: com o foco dentro do iframe do comprovante, a tecla vai para
  // o documento do iframe e a janela não ouve.
  await p.evaluate(() => [...document.querySelectorAll('[role="dialog"] [aria-label="fechar"]')].pop()?.click());
  await p.waitForFunction(() => !document.querySelector("#comprovante-quadro"), { timeout: 10000 }).catch(() => {});
  // Sem o agrupamento: agrupado, o nome da pessoa fica no cabeçalho do grupo, não na linha.
  await p.click("#pagar-por-pessoa");

  console.log("6. agendar com baixa automática para hoje");
  await p.click('[data-aba-pagar="A_PAGAR"]');
  await p.waitForFunction((n) => [...document.querySelectorAll("[data-conta]")].some((li) => li.innerText.includes(n)),
    { timeout: 20000 }, nomes[1]).catch(() => {});
  const doB = (await linhaDe(p, nomes[1]))[0];
  await p.evaluate((id) => document.querySelector(`[data-conta="${id}"] [data-acao="agendar"]`)?.click(), doB?.id);
  await p.waitForSelector("#agendar-data", { timeout: 10000 });
  await p.$eval("#agendar-data", (e, h) => {
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    set.call(e, h); e.dispatchEvent(new Event("input", { bubbles: true })); e.dispatchEvent(new Event("change", { bubbles: true }));
  }, HOJE);
  checar("a baixa automática vem ligada", await p.$eval("#agendar-automatica", (e) => e.checked));
  await p.click("#agendar-confirmar");
  await p.waitForFunction(() => !document.querySelector("#agendar-confirmar"), { timeout: 15000 }).catch(() => {});
  await p.click('[data-aba-pagar="PAGO"]');
  await p.waitForFunction((n) => [...document.querySelectorAll("[data-conta]")].some((li) => li.innerText.includes(n)),
    { timeout: 20000 }, nomes[1]).catch(() => {});
  const auto = await linhaDe(p, nomes[1]);
  checar("agendada para hoje, já aparece paga com baixa automática",
    auto.length === 1 && /baixa automática/.test(auto[0].texto), auto);

  console.log("6b. o painel (etapa 2)");
  await p.goto(`${WEB}/financeiro/painel`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#painel-frente", { timeout: 60000 }).catch(() => {});
  checar("o painel está no menu do Financeiro e abre", !!(await p.$('aside a[href="/financeiro/painel"]')) && !!(await p.$("#painel-frente")));
  await p.waitForSelector(`[data-linha-painel="${nomes[0]}"]`, { timeout: 15000 }).catch(() => {});
  const naPessoa = await p.$eval(`[data-linha-painel="${nomes[0]}"]`, (e) => e.innerText).catch(() => "");
  checar("por pessoa, o que foi pago hoje no mês", /150,00/.test(naPessoa), naPessoa);
  const sozinhas = await p.$eval("#painel-sozinhas", (e) => e.innerText).catch(() => "");
  checar("a baixa automática de hoje aparece para conferir no banco", sozinhas.includes(nomes[1]), sozinhas.slice(0, 200));
  await p.click("#painel-mes-passado");
  await p.waitForFunction(() => /de=/.test(location.search), { timeout: 10000 }).catch(() => {});
  await esperar(800);
  const semPessoa = !(await p.$(`[data-linha-painel="${nomes[0]}"]`));
  checar("no mês passado o pagamento de hoje não aparece", semPessoa);

  console.log("8. parcelas e contas fixas (etapa 3)");
  await p.goto(`${WEB}/financeiro/pagar`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#pagar-nova", { timeout: 60000 });
  await p.click("#pagar-nova");
  await p.waitForSelector("#conta-pessoa", { timeout: 10000 });
  await p.click("#conta-pessoa");
  await p.type("#conta-pessoa", nomes[0]);
  await p.keyboard.press("Tab");
  await esperar(800);
  await p.type("#conta-descricao", `Forno tela ${MARCA}`);
  await p.click("#conta-parcelas", { clickCount: 3 });
  await p.type("#conta-parcelas", "3");
  await p.click("#conta-valor", { clickCount: 3 });
  await p.type("#conta-valor", "100");
  await p.waitForSelector("#conta-previa-parcelas", { timeout: 5000 }).catch(() => {});
  const previa = await p.$eval("#conta-previa-parcelas", (e) => e.innerText).catch(() => "");
  checar("a prévia mostra as 3 parcelas, a sobra na primeira", /3 parcelas/.test(previa) && /33,34/.test(previa) && /33,33/.test(previa), previa);
  checar("o botão diz quantas parcelas", /Lançar 3 parcelas/.test(await p.$eval("#conta-salvar", (e) => e.innerText)));
  await p.click("#conta-salvar");
  await p.waitForFunction((m) => [...document.querySelectorAll("[data-conta]")].filter((li) => li.innerText.includes(m)).length === 3,
    { timeout: 20000 }, `Forno tela ${MARCA}`).catch(() => {});
  const parcs = await linhaDe(p, `Forno tela ${MARCA}`);
  checar("entram 3 contas, marcadas parcela 1/3 a 3/3",
    parcs.length === 3 && [1, 2, 3].every((n) => parcs.some((x) => x.texto.includes(`parcela ${n}/3`))), parcs.map((x) => x.texto.slice(0, 80)));

  await p.click("#pagar-fixas");
  await p.waitForSelector("#fixas-janela", { timeout: 10000 });
  await p.click("#fixa-nova");
  await p.waitForSelector("#fixa-pessoa", { timeout: 10000 });
  await p.click("#fixa-pessoa");
  await p.type("#fixa-pessoa", nomes[1]);
  await p.keyboard.press("Tab");
  await esperar(800);
  await p.type("#fixa-descricao", `Internet tela ${MARCA}`);
  await p.type("#fixa-valor", "99,90");
  await p.click("#fixa-dia", { clickCount: 3 });
  await p.type("#fixa-dia", String(Number(HOJE.slice(8, 10))));
  await p.click("#fixa-antecedencia", { clickCount: 3 });
  await p.type("#fixa-antecedencia", "0");
  await p.click("#fixa-salvar");
  await p.waitForFunction((m) => [...document.querySelectorAll("[data-fixa]")].some((li) => li.innerText.includes(m)),
    { timeout: 20000 }, `Internet tela ${MARCA}`).catch(() => {});
  const fixaTxt = await p.evaluate((m) => [...document.querySelectorAll("[data-fixa]")]
    .find((li) => li.innerText.includes(m))?.innerText ?? "", `Internet tela ${MARCA}`);
  checar("a conta fixa aparece na lista, com o dia e a próxima", /todo dia/.test(fixaTxt) && /próxima: vence/.test(fixaTxt), fixaTxt);
  await p.evaluate(() => [...document.querySelectorAll('[role="dialog"] [aria-label="fechar"]')].pop()?.click());
  await p.waitForFunction(() => !document.querySelector("#fixas-janela"), { timeout: 10000 }).catch(() => {});
  await p.waitForFunction((m) => [...document.querySelectorAll("[data-conta]")].some((li) => li.innerText.includes(m)),
    { timeout: 20000 }, `Internet tela ${MARCA}`).catch(() => {});
  const gerada = await linhaDe(p, `Internet tela ${MARCA}`);
  checar("vencendo hoje, a conta deste mês já está em A pagar, marcada como conta fixa",
    gerada.length === 1 && /conta fixa/.test(gerada[0].texto) && /99,90/.test(gerada[0].texto), gerada);

  await p.click("#pagar-fixas");
  await p.waitForSelector("#fixas-janela", { timeout: 10000 });
  await p.waitForFunction((m) => [...document.querySelectorAll("[data-fixa]")].some((li) => li.innerText.includes(m)),
    { timeout: 20000 }, `Internet tela ${MARCA}`).catch(() => {});
  await p.evaluate((m) => [...document.querySelectorAll("[data-fixa]")]
    .find((li) => li.innerText.includes(m))?.querySelector('[data-acao="encerrar-fixa"]')?.click(), `Internet tela ${MARCA}`);
  await p.waitForSelector("#fixa-cancelar-abertas", { timeout: 10000 }).catch(() => {});
  await p.click("#fixa-cancelar-abertas");
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.innerText.trim() === "Encerrar" && !b.dataset.acao)?.click());
  await p.waitForFunction((m) => ![...document.querySelectorAll("[data-fixa]")].some((li) => li.innerText.includes(m)),
    { timeout: 15000 }, `Internet tela ${MARCA}`).catch(() => {});
  checar("encerrada, sai da lista das ativas", !(await p.evaluate((m) => [...document.querySelectorAll("[data-fixa]")]
    .some((li) => li.innerText.includes(m)), `Internet tela ${MARCA}`)));
  await p.evaluate(() => [...document.querySelectorAll('[role="dialog"] [aria-label="fechar"]')].pop()?.click());
  await p.waitForFunction((m) => ![...document.querySelectorAll("[data-conta]")].some((li) => li.innerText.includes(m)),
    { timeout: 15000 }, `Internet tela ${MARCA}`).catch(() => {});
  checar("e a conta em aberto dela foi cancelada", (await linhaDe(p, `Internet tela ${MARCA}`)).length === 0);

  console.log("9. fluxo de caixa (etapa 4)");
  const diaMais = (n) => { const d = new Date(`${HOJE}T12:00:00`); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
  const venc = diaMais(5);
  const { status: stF } = await api("POST", "/contas-pagar", { id_pessoa: ids[0], descricao: `Fluxo tela ${MARCA}`,
    competencia: HOJE, vencimento: venc, valor: 77.77 }, token);
  checar("a conta para o fluxo nasce", stF === 201, stF);
  await p.goto(`${WEB}/financeiro/fluxo?de=${HOJE}&ate=${diaMais(10)}&previsao=false`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#fluxo-totais", { timeout: 60000 }).catch(() => {});
  checar("o Fluxo de caixa está no menu do Financeiro", !!(await p.$('aside a[href="/financeiro/fluxo"]')));
  checar("a tela abre com os totais e o dia a dia", !!(await p.$("#fluxo-totais")) && !!(await p.$("#fluxo-dias")));
  const linhaVenc = await p.$eval(`[data-dia-fluxo="${venc}"]`, (e) => e.innerText).catch(() => "");
  checar("a conta em aberto aparece no dia do vencimento, como saída", /77,77/.test(linhaVenc) && /a pagar/.test(linhaVenc), linhaVenc);
  checar("a previsão começa desligada pela URL", !(await p.$eval("#fluxo-previsao", (e) => e.checked)));
  const rodape = async () => p.$eval("#fluxo-rodape", (e) => e.innerText).catch(() => "");
  const numeros = (t) => (t.match(/-?R\$\s?-?[\d.]+,\d{2}/g) ?? []).map((x) => Number(x.replace(/[^\d,-]/g, "").replace(",", ".")));
  const antesR = numeros(await rodape());
  await p.type("#fluxo-saldo-inicial", "1000");
  await p.waitForFunction((v) => {
    const t = document.querySelector("#fluxo-rodape")?.innerText ?? "";
    return !t.includes(v);
  }, { timeout: 15000 }, (await rodape()).split("	").pop()).catch(() => {});
  const depoisR = numeros(await rodape());
  checar("o saldo inicial de 1.000 sobe o acumulado final em 1.000 (o saldo do período não muda)",
    antesR.length === 4 && depoisR.length === 4 && Math.abs(depoisR[3] - antesR[3] - 1000) < 0.01 && Math.abs(depoisR[2] - antesR[2]) < 0.01,
    { antesR, depoisR });
  await p.click("#fluxo-previsao");
  await p.waitForFunction(() => location.search.includes("previsao=true") || !location.search.includes("previsao=false"),
    { timeout: 10000 }).catch(() => {});
  checar("ligar a previsão vai para a URL", await p.$eval("#fluxo-previsao", (e) => e.checked)
    && !(await p.evaluate(() => location.search.includes("previsao=false"))));
  checar("o botão do relatório está na tela", (await p.evaluate(() => document.body.innerText)).includes("Imprimir")
    || !!(await p.$('[data-relatorio="fluxo-caixa"]')));

  console.log("7. cadastro e celular");
  await p.goto(`${WEB}/fornecedores/${ids[0]}`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#pessoa-chave-pix", { timeout: 30000 }).catch(() => {});
  const pix = await p.$eval("#pessoa-chave-pix", (e) => e.value).catch(() => null);
  checar("o cadastro de Pessoas mostra a chave Pix", pix === `${MARCA}@pix.teste`, pix);
  await p.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
  await p.goto(`${WEB}/financeiro/pagar?aba=PAGO`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#pagar-resumo", { timeout: 60000 }).catch(() => {});
  await esperar(500);
  const larg = await p.evaluate(() => ({ doc: document.documentElement.scrollWidth, tela: window.innerWidth }));
  checar("no celular a página não rola de lado", larg.doc <= larg.tela, larg);
  await p.goto(`${WEB}/financeiro/painel`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#painel-frente", { timeout: 60000 }).catch(() => {});
  await esperar(500);
  const largP = await p.evaluate(() => ({ doc: document.documentElement.scrollWidth, tela: window.innerWidth }));
  checar("no celular o painel não rola de lado", largP.doc <= largP.tela, largP);
  await p.goto(`${WEB}/financeiro/fluxo`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#fluxo-totais", { timeout: 60000 }).catch(() => {});
  await esperar(500);
  const largF = await p.evaluate(() => ({ doc: document.documentElement.scrollWidth, tela: window.innerWidth }));
  checar("no celular o fluxo de caixa não rola de lado", largF.doc <= largF.tela, largF);
} finally {
  await navegador.close();
  // ⚠️ A conta fixa de teste ativa geraria uma conta por mês para sempre na base local.
  const { dados: fx } = await api("GET", "/contas-pagar/fixas", undefined, token);
  for (const f of (fx ?? []).filter((x) => x.descricao.includes(MARCA))) {
    await api("POST", `/contas-pagar/fixas/${f.id}/encerrar`, { cancelar_abertas: true }, token);
  }
  const { dados } = await api("GET", `/contas-pagar?status=PAGO&status=A_PAGAR&status=AGENDADO&busca=${MARCA}&limite=100`, undefined, token);
  const pagas = (dados?.itens ?? []).filter((c) => c.status === "PAGO").map((c) => c.id);
  if (pagas.length) await api("POST", "/contas-pagar/estornar", { ids: pagas }, token);
  const { dados: d2 } = await api("GET", `/contas-pagar?status=A_PAGAR&status=AGENDADO&busca=${MARCA}&limite=100`, undefined, token);
  const abertas = (d2?.itens ?? []).map((c) => c.id);
  if (abertas.length) await api("POST", "/contas-pagar/cancelar", { ids: abertas }, token);
  for (const id of ids) if (id) await api("DELETE", `/fornecedores/${id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
