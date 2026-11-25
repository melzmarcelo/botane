/**
 * Venda: editar a quantidade e excluir item de documento à mão em aberto, e a forma de
 * pagamento (1.3.20, migração 160, pedidos do dono de 24/11/2026). Confere:
 *   1. o documento à mão mostra "Quantidade" e "Excluir" em cada linha;
 *   2. mudar a quantidade pela janela atualiza a linha e o total;
 *   3. excluir pede confirmação e tira a linha; a última linha não tem "Excluir" ativo;
 *   4. a venda com pagamentos mostra "pago em" com crédito, Pix e o troco;
 *   5. o painel de vendas do dia tem o quadro "Por forma de pagamento";
 *   6. a do PDV não oferece editar;
 *   7. Vendas ▸ Caixa: a diferença aparece ao digitar e grava com quem conferiu (161);
 *   8. a configuração da Precificação tem a taxa de cada forma; o caixa cabe no celular.
 * O que o roteiro cria é cancelado no fim.
 *
 *    node scripts/verificar-venda-itens-pagamentos.mjs   (API na 9200 e web na 3100 de pé)
 */
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
const criadas = [];

async function lancar(documento, origem, itens, pagamentos = []) {
  await api("POST", "/vendas/importar", { vendas: [{ data: HOJE, hora: "16:00:00", documento, origem,
    pagamentos, itens }] }, token);
  const { dados } = await api("GET", `/vendas?busca=${documento}&limite=5`, undefined, token);
  const lista = Array.isArray(dados) ? dados : dados?.itens ?? [];
  const id = lista.find((v) => v.documento === documento)?.id;
  if (id) criadas.push(id);
  return id;
}

const itens = [{ descricao: `Bolo editar ${MARCA}`, quantidade: 3, valor_unitario: 10 },
               { descricao: `Suco editar ${MARCA}`, quantidade: 2, valor_unitario: 8 }];
const idManual = await lancar(`VIW-${MARCA}`, "MANUAL", itens);
const idPdv = await lancar(`VIWP-${MARCA}`, "PDV_LEGAL", [{ descricao: `Café pdv ${MARCA}`, quantidade: 1, valor_unitario: 50 }],
  [{ grupo: "CREDITO", nome_pdv: "CREDITO", valor: 30 }, { grupo: "PIX", nome_pdv: "PIX WEB", valor: 15 },
   { grupo: "DINHEIRO", valor: 10 }, { grupo: "TROCO", nome_pdv: "TROCO", valor: 5 }]);
checar("as duas vendas de teste nascem", !!idManual && !!idPdv, { idManual, idPdv });

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1000 });
  await p.goto(WEB + "/login", { timeout: 180000 });
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. documento à mão");
  await p.goto(`${WEB}/vendas/${idManual}`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector('[data-acao-item="quantidade"]', { timeout: 60000 }).catch(() => {});
  checar("cada linha tem Quantidade e Excluir", await p.evaluate(() =>
    document.querySelectorAll('[data-acao-item="quantidade"]').length === 2
    && document.querySelectorAll('[data-acao-item="excluir"]').length === 2));
  checar("sem pagamento, a receita diz que a forma não foi informada",
    await p.evaluate(() => /não informada/.test(document.querySelector("#venda-pagamentos")?.innerText ?? "")));

  console.log("2. mudar a quantidade");
  const primeira = await p.$eval('[data-item-venda]', (e) => e.dataset.itemVenda);
  await p.click(`[data-item-venda="${primeira}"] [data-acao-item="quantidade"]`);
  await p.waitForSelector("#item-quantidade", { timeout: 10000 });
  await p.focus("#item-quantidade");
  await p.keyboard.type("1");
  await p.click("#item-salvar-quantidade");
  await p.waitForFunction(() => !document.querySelector("#item-quantidade"), { timeout: 15000 }).catch(() => {});
  const { dados: depois } = await api("GET", `/vendas/${idManual}`, undefined, token);
  checar("a linha passa a 1 e o total cai para 26 (10 + 16)",
    Number(depois.itens.find((i) => String(i.id) === primeira)?.quantidade) === 1 && Number(depois.valor_total) === 26,
    { itens: depois.itens.map((i) => i.quantidade), total: depois.valor_total });

  console.log("3. excluir");
  await p.click(`[data-item-venda="${primeira}"] [data-acao-item="excluir"]`);
  await p.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.innerText.trim() === "Excluir item"),
    { timeout: 10000 }).catch(() => {});
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.innerText.trim() === "Excluir item")?.click());
  await p.waitForFunction(() => document.querySelectorAll("[data-item-venda]").length === 1, { timeout: 15000 }).catch(() => {});
  checar("a linha sai da tela", await p.evaluate(() => document.querySelectorAll("[data-item-venda]").length === 1));
  checar("e a última linha fica sem Excluir ativo",
    await p.evaluate(() => document.querySelector('[data-acao-item="excluir"]')?.disabled === true));

  console.log("4. pagamentos");
  await p.goto(`${WEB}/vendas/${idPdv}`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#venda-pagamentos", { timeout: 60000 }).catch(() => {});
  const pago = await p.$eval("#venda-pagamentos", (e) => e.innerText).catch(() => "");
  checar("a venda do PDV mostra crédito, Pix (PIX WEB), dinheiro e o troco",
    /pago em/.test(pago) && /Crédito/.test(pago) && /PIX WEB/.test(pago) && /Dinheiro/.test(pago) && /troco/.test(pago), pago);
  checar("e não oferece editar os itens", !(await p.$('[data-acao-item="quantidade"]')));

  console.log("5. painel");
  await p.goto(`${WEB}/vendas/painel?inicio=${HOJE}&fim=${HOJE}`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#painel-vendas-pagamento", { timeout: 60000 }).catch(() => {});
  const quadro = await p.$eval("#painel-vendas-pagamento", (e) => e.innerText).catch(() => "");
  checar("o painel do dia tem Por forma de pagamento, com crédito e Pix", /Crédito/.test(quadro) && /Pix/.test(quadro), quadro.slice(0, 200));

  console.log("6. conferência do caixa (161)");
  const { dados: antesCaixa } = await api("GET", `/caixa/conferencia?inicio=${HOJE}&fim=${HOJE}`, undefined, token);
  const diaAntes = antesCaixa?.dias?.find((d) => d.data === HOJE);
  await p.goto(`${WEB}/vendas/caixa`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector(`[data-caixa-dia="${HOJE}"]`, { timeout: 60000 }).catch(() => {});
  checar("o menu tem Vendas ▸ Caixa", await p.evaluate(() => !!document.querySelector('a[href="/vendas/caixa"]')));
  checar("o dia de hoje aparece com o esperado", !!(await p.$(`[data-caixa-dia="${HOJE}"]`)));
  const esperado = diaAntes ? diaAntes.esperado : 0;
  const campoCx = `[data-caixa-dia="${HOJE}"] [data-caixa-contado]`;
  // ⚠️ Um valor INTEIRO, sem vírgula, como quem conta a gaveta digita: com a função de máscara
  // de moeda, "500" virava R$ 5,00 (24/11/2026).
  const inteiro = Math.ceil(esperado) + 2;
  const sobra = (inteiro - esperado).toFixed(2).replace(".", ",");
  await p.click(campoCx, { clickCount: 3 });
  await p.type(campoCx, String(inteiro));
  const difTela = await p.$eval(`[data-caixa-dia="${HOJE}"] [data-caixa-diferenca]`, (e) => e.innerText);
  checar("digitar sem vírgula dá a diferença certa (sobra)", /sobra/.test(difTela) && difTela.includes(sobra),
    { difTela, inteiro, esperado });
  await p.click(`[data-caixa-dia="${HOJE}"] [data-caixa-gravar]`);
  await p.waitForFunction((h) => /por /.test(document.querySelector(`[data-caixa-dia="${h}"]`)?.innerText ?? ""),
    { timeout: 15000 }, HOJE).catch(() => {});
  const { dados: depoisCaixa } = await api("GET", `/caixa/conferencia?inicio=${HOJE}&fim=${HOJE}`, undefined, token);
  const diaDepois = depoisCaixa.dias.find((d) => d.data === HOJE);
  checar("gravado no servidor, com quem conferiu",
    !!diaDepois && Math.abs(diaDepois.contado - inteiro) < 0.01 && !!diaDepois.conferido_por, diaDepois);
  if (diaAntes && diaAntes.contado !== null) {
    await api("PUT", `/caixa/conferencia/${HOJE}`, { contado: diaAntes.contado, observacao: diaAntes.observacao }, token);
  }

  console.log("7. taxas por forma (161)");
  await p.goto(`${WEB}/precificacao/configuracao`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#taxas-pagamento", { timeout: 60000 }).catch(() => {});
  checar("a configuração da Precificação tem a taxa de cada forma",
    await p.evaluate(() => document.querySelectorAll("#taxas-pagamento [data-taxa]").length >= 5));
  const larg = await (async () => {
    await p.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
    await p.goto(`${WEB}/vendas/caixa`, { waitUntil: "networkidle2", timeout: 180000 });
    await p.waitForSelector("#caixa-dias", { timeout: 60000 }).catch(() => {});
    return p.evaluate(() => ({ doc: document.documentElement.scrollWidth, tela: window.innerWidth }));
  })();
  checar("o caixa no celular não rola de lado", larg.doc <= larg.tela, larg);
} finally {
  await navegador.close();
  for (const id of criadas) await api("DELETE", `/vendas/${id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
