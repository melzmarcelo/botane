/**
 * Patrimônio no navegador: a lista com o resumo por setor, a ficha, a manutenção, o
 * cadastro novo, o QR e a importação por planilha.
 *
 * 🔑 Pedido do dono (27/10/2026): *"um processo para inventariar o patrimônio"* — etapas 1
 * e 2 (cadastro com plaqueta e importação; manutenção com plano e alertas). Confere:
 *   1. a lista mostra o quadro por setor e filtra pela URL (o link do alerta);
 *   2. a ficha diz "Vencida", e registrar a preventiva de hoje a põe "Em dia";
 *  2b. a entrega 2 (157): garantia em meses calcula a data, responsável, checklist marcado na
 *      preventiva, NF, foto anexada (capa da ficha) e o botão "Consultar no Omie";
 *   3. "Novo bem" cadastra e abre a ficha do bem criado;
 *   4. o endereço do QR (/patrimonio/b/PAT-…) abre a ficha;
 *   5. a importação mostra a prévia e só grava no segundo clique;
 *   6. o produto Patrimônio que entra aparece em "falta cadastrar"; o "Cadastrar bem" chega
 *      com o produto e a última entrada; o cadastro do produto lista o bem.
 *   7. a conferência pelas plaquetas (etapa 3, 140);
 *   8. o valor do patrimônio (etapa 4, 141): os totais batem com a API, a ficha mostra o
 *      valor atual e a vida útil trocada refaz a conta.
 * O que o roteiro cria é apagado no fim.
 *
 *    node scripts/verificar-patrimonio.mjs   (API na 9200 e web na 3100 de pé)
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const API = process.env.BOTANE_API ?? "http://127.0.0.1:9200";
const WEB = process.env.BOTANE_WEB ?? "http://127.0.0.1:3100";
const MARCA = String(Date.now()).slice(-6);
const AQUI = path.dirname(fileURLToPath(import.meta.url));
let ok = 0;
const falhas = [];
const checar = (nome, cond, detalhe = "") => {
  if (cond) { ok++; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHA ${nome} ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`); }
};
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
// ⚠️ Com a ficha mais alta (157), o botão fica abaixo da dobra e o clique do puppeteer saía
// durante a rolagem, num ponto que já não era o botão: rola ANTES, sem animação, e clica.
const clicar = async (alvo) => {
  await alvo.evaluate((e) => e.scrollIntoView({ block: "center", behavior: "instant" }));
  await esperar(150);
  await alvo.click();
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
const hoje = new Date().toLocaleDateString("sv-SE");
const seteMeses = new Date(Date.now() - 215 * 86400000).toLocaleDateString("sv-SE");

console.log("0. cenário: um bem crítico com a preventiva vencida");
const { dados: setor } = await api("POST", "/setores", { nome: `SETOR PATWEB ${MARCA}` }, token);
const { status: st0, dados: bem } = await api("POST", "/patrimonio", {
  descricao: `Forno web ${MARCA}`, marca: `Marca${MARCA}`, id_setor: setor.id, criticidade: "ALTA",
  preventiva_meses: 6, ultima_preventiva: seteMeses,
}, token);
checar("o bem de teste nasce", st0 === 201, bem);
const csv = path.join(AQUI, `_patrimonio_${MARCA}.csv`);
const criados = [bem.id];
const produtos = [];
const bensConf = [];
const setoresConf = [];

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1100 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. a lista");
  await p.goto(`${WEB}/patrimonio?preventiva=VENCIDA&busca=Marca${MARCA}`, { waitUntil: "networkidle2" });
  await p.waitForFunction((c) => document.querySelector("#patrimonio-lista")?.innerText.includes(c),
                          { timeout: 20000 }, bem.codigo).catch(() => {});
  const lista = await p.evaluate(() => ({
    linhas: [...document.querySelectorAll("#patrimonio-lista tbody tr")].map((tr) => tr.innerText),
    resumo: document.querySelector("#patrimonio-resumo")?.innerText ?? "",
    prev: document.querySelector("#patrimonio-preventiva")?.value,
  }));
  checar("o filtro da URL (o link do alerta) traz só o bem vencido",
    lista.linhas.length === 1 && lista.linhas[0].includes(bem.codigo) && lista.prev === "VENCIDA", lista);
  checar("e a linha diz Vencida", /Vencida/.test(lista.linhas[0] ?? ""), lista.linhas);
  checar("o quadro por setor mostra o setor do bem", lista.resumo.includes(`SETOR PATWEB ${MARCA}`), lista.resumo.slice(0, 300));

  console.log("\n2. a ficha e a manutenção");
  await p.goto(`${WEB}/patrimonio/${bem.id}`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#bem-faixa", { timeout: 20000 }).catch(() => {});
  const cab = await p.evaluate(() => document.querySelector("main header")?.innerText ?? "");
  checar("o cabeçalho traz o código e 'Vencida'", cab.includes(bem.codigo) && /Vencida/.test(cab), cab);
  // 🔑 156 (09/11/2026): a ficha em abas, com os quatro números numa faixa acima.
  const abasDaFicha = await p.evaluate(() => ({
    faixa: document.querySelector("#bem-faixa")?.innerText ?? "",
    abas: [...document.querySelectorAll('[role="tablist"] [role="tab"]')].map((b) => b.textContent?.trim()),
    plaqueta: !!document.querySelector("#bem-plaqueta-previa svg rect"),
  }));
  checar("a faixa mostra garantia, próxima preventiva, última manutenção e custo acumulado",
    ["Garantia", "Próxima preventiva", "Última manutenção", "Custo acumulado"].every((t) => abasDaFicha.faixa.includes(t)), abasDaFicha.faixa);
  checar("as cinco abas", ["Dados do bem", "Garantia", "Preventiva", "Manutenções", "Custos"]
    .every((t) => abasDaFicha.abas.some((a) => a?.startsWith(t))), abasDaFicha.abas);
  checar("a aba Dados do bem mostra a prévia da plaqueta com o QR", abasDaFicha.plaqueta);
  // O botão do cabeçalho leva à aba Manutenções, no formulário.
  await p.click("#bem-registrar-manutencao");
  await p.waitForSelector("#manutencao-registrar", { timeout: 15000 }).catch(() => {});
  checar("'Registrar manutenção' abre a aba Manutenções e põe ?aba= no endereço",
    !!(await p.$("#manutencao-registrar")) && p.url().includes("aba=manutencoes"), p.url());
  await p.select("#manutencao-tipo", "PREVENTIVA");
  await p.$eval("#manutencao-descricao", (e) => { e.value = ""; });
  await p.type("#manutencao-descricao", "limpeza e calibração");
  await clicar(await p.$("#manutencao-registrar"));
  await p.waitForFunction(() => /Em dia/.test(document.querySelector("main header")?.innerText ?? ""),
                          { timeout: 15000 }).catch(() => {});
  const depois = await p.evaluate(() => ({
    cab: document.querySelector("main header")?.innerText ?? "",
    hist: document.querySelector("#manutencao-lista")?.innerText ?? "",
  }));
  checar("registrar a preventiva de hoje põe 'Em dia'", /Em dia/.test(depois.cab), depois.cab);
  checar("e o histórico mostra o registro", depois.hist.includes("limpeza e calibração"), depois.hist);
  checar("e marca a de hoje como recente", /recente/.test(depois.hist), depois.hist);
  await clicar(await p.$("#aba-custos"));
  await p.waitForSelector("#custos-extrato", { timeout: 15000 }).catch(() => {});
  const custos = await p.evaluate(() => document.querySelector("#custos-extrato")?.innerText ?? "");
  checar("a aba Custos traz o extrato com a preventiva e o saldo acumulado",
    /Preventiva/.test(custos) && /Saldo acumulado/i.test(custos), custos);

  console.log("\n2b. entrega 2 da ficha (157): garantia em meses, responsável, checklist, NF, foto e Omie");
  // React só vê o valor posto pelo setter NATIVO seguido de um evento de input.
  const definir = (sel, valor) => p.$eval(sel, (e, v) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(e, v);
    e.dispatchEvent(new Event("input", { bubbles: true }));
  }, valor);
  await clicar(await p.$("#aba-dados"));
  await p.waitForSelector("#bem-data-compra", { timeout: 15000 });
  await definir("#bem-data-compra", "2026-01-31");
  await p.type("#bem-responsavel", `Chef Web ${MARCA}`);
  await clicar(await p.$("#aba-garantia"));
  await p.waitForSelector("#bem-garantia-meses", { timeout: 15000 });
  await p.type("#bem-garantia-meses", "1");
  await p.select("#bem-garantia-tipo", "FABRICA");
  const ateCalculada = await p.$eval("#bem-garantia-ate", (e) => e.value);
  checar("os meses calculam a data final pela compra (31/01 + 1 mês = 28/02)", ateCalculada === "2026-02-28", ateCalculada);
  await clicar(await p.$("#aba-preventiva"));
  await p.waitForSelector("#preventiva-checklist-novo", { timeout: 15000 });
  for (const item of ["Limpar condensador", "Trocar filtro"]) {
    await p.type("#preventiva-checklist-novo", item);
    await p.keyboard.press("Enter");
  }
  const itensTela = await p.$$eval("#preventiva-checklist li", (l) => l.length);
  checar("o checklist ganha os dois itens na tela", itensTela === 2, itensTela);
  await clicar(await p.$("#bem-salvar"));
  let salvo = {};
  for (let i = 0; i < 20 && !salvo.preventiva_checklist?.length; i++) {
    await esperar(500);
    salvo = (await api("GET", `/patrimonio/${bem.id}`, undefined, token)).dados;
  }
  checar("Salvar grava garantia, tipo, responsável e checklist das três abas",
    salvo.garantia_ate === "2026-02-28" && salvo.garantia_tipo === "FABRICA"
    && salvo.responsavel === `Chef Web ${MARCA}` && salvo.preventiva_checklist?.length === 2, salvo);
  await clicar(await p.$("#aba-manutencoes"));
  await p.waitForSelector("#manutencao-checklist", { timeout: 15000 }).catch(() => {});
  const caixas = await p.$$("#manutencao-checklist input[type=checkbox]");
  checar("a preventiva mostra o checklist do bem para marcar", caixas.length === 2, caixas.length);
  if (caixas[0]) await clicar(caixas[0]);
  await p.type("#manutencao-nota", `NF${MARCA}`);
  await clicar(await p.$("#manutencao-registrar"));
  await p.waitForFunction(() => /1 de 2 itens/.test(document.querySelector("#manutencao-lista")?.innerText ?? ""),
                          { timeout: 15000 }).catch(() => {});
  const hist2 = await p.evaluate(() => document.querySelector("#manutencao-lista")?.innerText ?? "");
  checar("o histórico mostra a NF e '1 de 2 itens'", hist2.includes(`NF${MARCA}`) && /1 de 2 itens/.test(hist2), hist2);
  const foto = path.join(AQUI, `_foto_${MARCA}.png`);
  fs.writeFileSync(foto, Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64"));
  try {
    await clicar(await p.$("#aba-anexos"));
    const seletor = await p.waitForSelector("#anexo-arquivo", { timeout: 15000 });
    await seletor.uploadFile(foto);
    await p.click("#anexo-enviar");
    await p.waitForSelector("#anexos-fotos img", { timeout: 15000 }).catch(() => {});
    checar("a aba Fotos e documentos anexa a foto", !!(await p.$("#anexos-fotos img")));
    const contador = await p.$eval("#aba-anexos", (e) => e.textContent ?? "");
    checar("e a aba conta o anexo", /1$/.test(contador.trim()), contador);
    await clicar(await p.$("#aba-dados"));
    await p.waitForSelector("#bem-foto-capa", { timeout: 15000 }).catch(() => {});
    checar("a primeira foto vira a capa da ficha (aba Dados)", !!(await p.$("#bem-foto-capa")));
  } finally {
    fs.rmSync(foto, { force: true });
  }
  await clicar(await p.$("#aba-custos"));
  await p.waitForSelector("#custos-omie-consultar", { timeout: 15000 });
  await p.click("#custos-omie-consultar");
  // Com ou sem Omie configurado na base local, a tela responde: a tabela, ou a frase do porquê.
  await p.waitForFunction(() => !!document.querySelector("#custos-omie-lista")
    || /Omie/.test(document.querySelector('[role="alert"], .text-erro')?.textContent ?? "")
    || /não está configurado|Omie não/.test(document.body.innerText), { timeout: 30000 }).catch(() => {});
  const omie = await p.evaluate(() => ({
    tabela: document.querySelector("#custos-omie-lista")?.innerText ?? "",
    texto: document.body.innerText,
  }));
  checar("'Consultar no Omie' responde: a situação de cada lançamento, ou por que não dá",
    /Preventiva/.test(omie.tabela) || /não está configurado/.test(omie.texto), omie.tabela || omie.texto.slice(0, 300));

  console.log("\n3. novo bem");
  await p.goto(`${WEB}/patrimonio/novo`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#bem-descricao", { timeout: 20000 });
  await p.type("#bem-descricao", `Batedeira web ${MARCA}`);
  await p.type("#bem-apelido", `W${MARCA}`);
  await p.click("#bem-salvar");
  await p.waitForFunction(() => /\/patrimonio\/\d+$/.test(location.pathname), { timeout: 15000 }).catch(() => {});
  const idNovo = Number((p.url().match(/\/patrimonio\/(\d+)$/) ?? [])[1]);
  if (idNovo) criados.push(idNovo);
  checar("cadastra e abre a ficha do bem criado", !!idNovo, p.url());
  await p.waitForFunction(() => /PAT-\d+/.test(document.querySelector("h1")?.innerText ?? ""), { timeout: 15000 }).catch(() => {});
  const titulo = await p.evaluate(() => document.querySelector("h1")?.innerText ?? "");
  checar("com o código da plaqueta no título", /PAT-\d+/.test(titulo) && titulo.includes(`Batedeira web ${MARCA}`), titulo);

  console.log("\n4. o QR");
  await p.goto(`${WEB}/patrimonio/b/${bem.codigo}`, { waitUntil: "networkidle2" });
  await p.waitForFunction((id) => location.pathname === `/patrimonio/${id}`, { timeout: 15000 }, bem.id).catch(() => {});
  checar("o endereço da plaqueta abre a ficha", p.url().endsWith(`/patrimonio/${bem.id}`), p.url());

  console.log("\n5. importar planilha");
  fs.writeFileSync(csv, `Código;Equipamento;Setor;Marca\nIMP-${MARCA};Liquidificador web ${MARCA};SETOR PATWEB ${MARCA};Walita\n`, "utf8");
  await p.goto(`${WEB}/patrimonio/importar`, { waitUntil: "networkidle2" });
  const entrada = await p.waitForSelector("#patrimonio-arquivo", { timeout: 20000 });
  // 🔑 Pedido do dono (28/10): escolher arquivo é um BOTÃO da casa, não o controle nativo.
  const antesDeEscolher = await p.evaluate(() => ({
    nativoVisivel: document.querySelector("#patrimonio-arquivo")?.offsetParent !== null,
    botao: document.querySelector("#patrimonio-arquivo-botao")?.textContent?.trim() ?? "",
  }));
  checar("escolher a planilha é um botão, e o seletor nativo fica escondido",
    !antesDeEscolher.nativoVisivel && antesDeEscolher.botao === "Escolher a planilha", antesDeEscolher);
  await entrada.uploadFile(csv);
  await p.waitForFunction((n) => document.body.innerText.includes(n), { timeout: 5000 },
    path.basename(csv)).catch(() => {});
  const depoisDeEscolher = await p.evaluate(() =>
    document.querySelector("#patrimonio-arquivo-botao")?.parentElement?.innerText ?? "");
  checar("depois de escolher, o botão vira Trocar e o nome do arquivo aparece ao lado",
    depoisDeEscolher.includes("Trocar arquivo") && depoisDeEscolher.includes(path.basename(csv)),
    depoisDeEscolher);
  await p.click("#patrimonio-previa");
  await p.waitForSelector("#patrimonio-novos", { timeout: 15000 }).catch(() => {});
  const previa = await p.evaluate(() => ({
    novos: document.querySelector("#patrimonio-novos")?.innerText ?? "",
    botao: !!document.querySelector("#patrimonio-aplicar"),
  }));
  const { dados: antes } = await api("GET", `/patrimonio?busca=Liquidificador web ${MARCA}`, undefined, token);
  checar("a prévia mostra o novo e não grava", previa.novos.includes(`Liquidificador web ${MARCA}`)
    && previa.botao && antes.length === 0, { previa, antes });
  await p.click("#patrimonio-aplicar");
  await p.waitForFunction(() => /Importado/.test(document.body.innerText), { timeout: 15000 }).catch(() => {});
  const { dados: depoisImp } = await api("GET", `/patrimonio?busca=Liquidificador web ${MARCA}`, undefined, token);
  checar("o segundo clique grava, com o código da casa como apelido",
    depoisImp.length === 1 && depoisImp[0].apelido === `IMP-${MARCA}` && depoisImp[0].marca === "Walita", depoisImp);
  for (const b of depoisImp) criados.push(b.id);

  console.log("\n6. o produto Patrimônio que entra vira bem");
  const { dados: prod } = await api("POST", "/produtos", {
    nome: `CAFETEIRA PATWEB ${MARCA}`, tipo: "PATRIMONIO", um_estoque: "UN", status: "ATIVO",
  }, token);
  produtos.push(prod.id);
  await api("POST", "/estoque/entradas", {
    id_produto: prod.id, quantidade: 2, custo_unitario: 900, documento: `NF-WEB-${MARCA}`,
  }, token);
  await p.goto(`${WEB}/patrimonio`, { waitUntil: "networkidle2" });
  await p.waitForFunction((n) => document.querySelector("#patrimonio-a-cadastrar")?.innerText.includes(n),
                          { timeout: 20000 }, `CAFETEIRA PATWEB ${MARCA}`).catch(() => {});
  const pendente = await p.evaluate((n) => [...document.querySelectorAll("#patrimonio-a-cadastrar tbody tr")]
    .map((tr) => tr.innerText).find((t) => t.includes(n)) ?? "", `CAFETEIRA PATWEB ${MARCA}`);
  checar("a lista mostra o que entrou e falta cadastrar (faltam 2)", /\b2\b/.test(pendente), pendente);
  await p.goto(`${WEB}/patrimonio/novo?produto=${prod.id}`, { waitUntil: "networkidle2" });
  await p.waitForFunction((n) => document.querySelector("#bem-descricao")?.value === n,
                          { timeout: 20000 }, `CAFETEIRA PATWEB ${MARCA}`).catch(() => {});
  const pre = await p.evaluate(() => ({
    descricao: document.querySelector("#bem-descricao")?.value,
    produto: document.querySelector("#bem-produto")?.value ?? document.querySelector("#bem-produto")?.textContent,
  }));
  checar("o Cadastrar bem chega com o produto e o nome dele", pre.descricao === `CAFETEIRA PATWEB ${MARCA}`, pre);
  await p.click("#bem-salvar");
  await p.waitForFunction(() => /\/patrimonio\/\d+$/.test(location.pathname), { timeout: 15000 }).catch(() => {});
  const idDoProduto = Number((p.url().match(/\/patrimonio\/(\d+)$/) ?? [])[1]);
  if (idDoProduto) criados.push(idDoProduto);
  const { dados: criado } = await api("GET", `/patrimonio/${idDoProduto}`, undefined, token);
  checar("o bem nasce ligado ao produto, com a nota da última entrada",
    criado?.id_produto === prod.id && criado?.nota_fiscal === `NF-WEB-${MARCA}`, criado);
  await p.goto(`${WEB}/produtos/${prod.id}`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#produto-bens", { timeout: 20000 }).catch(() => {});
  const noProduto = await p.evaluate(() => document.body.innerText);
  checar("o cadastro do produto lista o bem e diz que falta 1",
    noProduto.includes(criado?.codigo ?? "??") && /Faltam\s+1/.test(noProduto), noProduto.slice(0, 200));

  console.log("\n7. a conferência pelas plaquetas (etapa 3, 140)");
  // Setor e bens PRÓPRIOS: o que passa por conferência fechada não se apaga (é história).
  const { dados: setorConf } = await api("POST", "/setores", { nome: `CONF PATWEB ${MARCA}` }, token);
  setoresConf.push(setorConf.id);
  for (const d of ["Chapa", "Coifa", "Fritadeira"]) {
    const { dados: b } = await api("POST", "/patrimonio",
      { descricao: `${d} conf web ${MARCA}`, id_setor: setorConf.id }, token);
    bensConf.push(b);
  }
  const [chapa, coifa, fritadeira] = bensConf;
  await p.goto(`${WEB}/patrimonio/conferencias`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#conferencia-setor", { timeout: 20000 });
  await p.waitForFunction((id) => !!document.querySelector(`#conferencia-setor option[value="${id}"]`),
                          { timeout: 10000 }, String(setorConf.id)).catch(() => {});
  await p.select("#conferencia-setor", String(setorConf.id));
  await p.click("#conferencia-abrir");
  await p.waitForFunction(() => /\/patrimonio\/conferencias\/\d+$/.test(location.pathname), { timeout: 15000 }).catch(() => {});
  const idConf = Number((p.url().match(/\/conferencias\/(\d+)$/) ?? [])[1]);
  checar("abrir leva à tela de leitura", !!idConf, p.url());
  await p.waitForSelector("#conferencia-leitura", { timeout: 15000 }).catch(() => {});
  const prog0 = await p.evaluate(() => document.querySelector("#conferencia-progresso")?.innerText ?? "");
  checar("com os 3 bens do setor a ler", /0 de 3 lidos/.test(prog0), prog0);
  // O leitor de código USB "digita" o LINK inteiro e dá Enter.
  await p.type("#conferencia-leitura", `${WEB}/patrimonio/b/${chapa.codigo}\n`);
  await p.waitForFunction(() => /conferido/.test(document.querySelector("#conferencia-ultima")?.innerText ?? ""),
                          { timeout: 15000 }).catch(() => {});
  const ultima = await p.evaluate(() => ({
    msg: document.querySelector("#conferencia-ultima")?.innerText ?? "",
    prog: document.querySelector("#conferencia-progresso")?.innerText ?? "",
    campo: document.querySelector("#conferencia-leitura")?.value,
  }));
  checar("a leitura diz numa linha que conferiu, e o campo limpa para a próxima",
    ultima.msg.includes(chapa.codigo) && /1 de 3 lidos/.test(ultima.prog) && ultima.campo === "", ultima);
  checar("este aparelho fica marcado como o que confere",
    await p.evaluate(() => localStorage.getItem("botane.patrimonio.conferindo")) === String(idConf));
  // A câmera COMUM do celular: a plaqueta abre o sistema e a leitura conta lá.
  await p.goto(`${WEB}/patrimonio/b/${coifa.codigo}`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#plaqueta-conferida", { timeout: 15000 }).catch(() => {});
  const pelaCamera = await p.evaluate(() => document.querySelector("#plaqueta-conferida")?.innerText ?? "");
  checar("a plaqueta aberta pela câmera comum conta na conferência (2 de 3)",
    pelaCamera.includes(coifa.codigo) && /2 de 3 lidos/.test(pelaCamera), pelaCamera);
  await p.goto(`${WEB}/patrimonio/conferencias/${idConf}`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#conferencia-fechar", { timeout: 15000 });
  await p.click("#conferencia-fechar");
  await p.waitForSelector("#conferencia-baixar", { timeout: 10000 });
  await p.click(`#conferencia-baixar input[data-codigo="${fritadeira.codigo}"]`);
  await p.waitForSelector("#conferencia-motivo", { timeout: 5000 });
  await p.type("#conferencia-motivo", "descartada");
  await p.click("#conferencia-confirmar-fechar");
  await p.waitForFunction(() => /Fechada/.test(document.querySelector("main header")?.innerText ?? ""),
                          { timeout: 15000 }).catch(() => {});
  const fechada = await p.evaluate(() => ({
    cab: document.querySelector("main header")?.innerText ?? "",
    nao: document.querySelector("#conferencia-faltam")?.innerText ?? "",
  }));
  checar("fechar com a baixa escolhida: a conferência fica Fechada e a fritadeira Baixada",
    /Fechada/.test(fechada.cab) && fechada.nao.includes(fritadeira.codigo) && /Baixado/.test(fechada.nao), fechada);
  const { dados: chapaDepois } = await api("GET", `/patrimonio/${chapa.id}`, undefined, token);
  checar("a chapa lida fica com a data de hoje", chapaDepois?.conferido_em === hoje, chapaDepois?.conferido_em);
  checar("e o aparelho deixa de estar conferindo",
    await p.evaluate(() => localStorage.getItem("botane.patrimonio.conferindo")) === null);

  console.log("\n8. o valor do patrimônio (etapa 4, 141)");
  const { status: stV, dados: comValor } = await api("POST", "/patrimonio", {
    descricao: `Vitrine web ${MARCA}`, id_setor: setor.id, valor_compra: 12000, data_compra: "2024-01-15",
  }, token);
  checar("o bem com valor nasce", stV === 201, comValor);
  criados.push(comValor.id);
  const { dados: esperado } = await api("GET", `/patrimonio/valor?setores=${setor.id}`, undefined, token);
  const brl = (n) => n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  await p.goto(`${WEB}/patrimonio`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#patrimonio-valor", { timeout: 20000 });
  await p.click("#patrimonio-valor");
  await p.waitForSelector("#valor-setor", { timeout: 20000 });
  await p.waitForFunction((n) => [...document.querySelectorAll("#valor-setor option")].some((o) => o.textContent === n),
                          { timeout: 15000 }, `SETOR PATWEB ${MARCA}`).catch(() => {});
  await p.select("#valor-setor", String(setor.id));
  // ⚠️ Espera os TOTAIS do setor, não o código do bem: com todos os setores na tela o código
  // já está lá antes de o filtro valer, e os totais eram lidos ainda os da loja inteira.
  await p.waitForFunction((n) => (" " + (document.querySelector("#valor-totais")?.innerText ?? "").replace(/\s+/g, " "))
                            .includes(` ${n} bem`),
                          { timeout: 20000 }, esperado.total.bens).catch(() => {});
  const tela = await p.evaluate((c) => ({
    totais: document.querySelector("#valor-totais")?.innerText ?? "",
    linha: document.querySelector(`#valor-bens tr[data-codigo="${c}"]`)?.innerText ?? "",
    setores: document.querySelector("#valor-setores")?.innerText ?? "",
  }), comValor.codigo);
  checar("a tela do valor abre pelo botão da lista e filtra pelo setor",
    tela.linha.includes(`Vitrine web ${MARCA}`) && tela.setores.includes(`SETOR PATWEB ${MARCA}`), tela);
  checar("os totais batem com a API (valor atual e depreciação)",
    tela.totais.includes(brl(esperado.total.valor_atual)) && tela.totais.includes(brl(esperado.total.depreciacao)),
    { tela: tela.totais, api: esperado.total });
  checar("a linha diz a vida útil padrão", /10 anos\s*\(padrão\)/.test(tela.linha), tela.linha);
  checar("o bem sem valor de compra é contado à parte",
    esperado.total.sem_valor > 0 && tela.totais.includes(`${esperado.total.sem_valor} sem valor de compra`), tela.totais);

  await p.goto(`${WEB}/patrimonio/${comValor.id}`, { waitUntil: "networkidle2" });
  await p.waitForSelector("#bem-valor-atual", { timeout: 20000 }).catch(() => {});
  const ficha = await p.evaluate(() => document.querySelector("#bem-valor-atual")?.innerText ?? "");
  checar("a ficha mostra o valor atual, a mesma conta",
    ficha.includes(brl(esperado.bens.find((b) => b.id === comValor.id).valor_atual)) && /\(padrão\)/.test(ficha), ficha);
  await p.type("#bem-vida-util", "5");
  await p.click("#bem-salvar");
  await p.waitForFunction(() => /vida útil 5 anos/.test(document.querySelector("#bem-valor-atual")?.innerText ?? ""),
                          { timeout: 15000 }).catch(() => {});
  const ficha5 = await p.evaluate(() => document.querySelector("#bem-valor-atual")?.innerText ?? "");
  checar("trocar a vida útil para 5 anos refaz a conta na hora", /vida útil 5 anos/.test(ficha5) && !/padrão/.test(ficha5), ficha5);
  await p.select("#bem-situacao", "BAIXADO");
  await p.waitForSelector("#bem-data-baixa", { timeout: 5000 }).catch(() => {});
  checar("dar baixa mostra a data da baixa", !!(await p.$("#bem-data-baixa")));
} finally {
  await navegador.close();
  try { fs.unlinkSync(csv); } catch { /* já não existe */ }
  for (const id of criados) {
    const { dados: d } = await api("GET", `/patrimonio/${id}`, undefined, token);
    for (const m of d?.manutencoes ?? []) await api("DELETE", `/patrimonio/manutencoes/${m.id}`, undefined, token);
    await api("DELETE", `/patrimonio/${id}`, undefined, token);
  }
  // ⚠️ NÃO zera o saldo antes de apagar: o acerto para zero entra na quebra do CMV por
  // grupo/setor/local (ver smoke_patrimonio). Com saldo, o produto fica só desativado.
  for (const id of produtos) {
    await api("DELETE", `/produtos/${id}`, undefined, token);
  }
  await api("DELETE", `/setores/${setor.id}`, undefined, token);
  // ⚠️ O bem que passou por conferência FECHADA não se apaga (é a folha assinada): fica
  // BAIXADO, fora das listas. O setor com conferência é desativado em vez de apagado.
  for (const b of bensConf) {
    const { status } = await api("DELETE", `/patrimonio/${b.id}`, undefined, token);
    if (status === 409) {
      await api("PUT", `/patrimonio/${b.id}`, { situacao: "BAIXADO", motivo_baixa: "limpeza do roteiro" }, token);
    }
  }
  for (const id of setoresConf) await api("DELETE", `/setores/${id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
