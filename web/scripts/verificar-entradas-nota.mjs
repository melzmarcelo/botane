// Roteiro de navegador: a nota RECEBIDA (migração 168) e a aba "Entradas por nota" do painel
// do estoque (pedidos do dono de 26/11/2026).
//
//   node scripts/verificar-entradas-nota.mjs     (API na 9200, web na 3100)
//
// 1. a nota conciliada do Omie oferece "Marcar como recebida"; a janela exige o nome
// 2. marcada, a nota mostra quem recebeu e oferece desfazer; a lista filtra "recebida"
// 3. o painel do estoque tem a aba "Entradas por nota", com as situações, a nota e quem recebeu
// 4. "por nota" agrupa pela nota; o filtro de situação filtra; Imprimir existe
// 5. no celular, sem rolagem lateral da página

import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const API = process.env.BOTANE_API ?? "http://127.0.0.1:9200";
const WEB = process.env.BOTANE_WEB ?? "http://127.0.0.1:3100";
const MARCA = String(Date.now()).slice(-6);
const DIA = "2033-06-10";
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

// A nota digitada (MANUAL) serve para o painel; o botão de recebida só existe na conciliada do
// OMIE, e essa não se cria pela API — o roteiro usa uma que a base local já tenha, e desfaz no fim.
const { dados: produtos } = await api("GET", "/produtos?controla_estoque=true&limite=1", undefined, token);
const prod = (produtos ?? [])[0];
const { status: stNota, dados: nova } = await api("POST", "/notas", {
  numero: `VE${MARCA}`, data_emissao: DIA, data_entrada: DIA,
  itens: [{ descricao: `ITEM TELA ${MARCA}`, quantidade: 2, um: prod?.um_estoque ?? "UN",
            valor_unitario: 7.5, id_produto: prod?.id }],
}, token);
checar("a nota digitada de teste nasce", stNota === 200 || stNota === 201, { stNota, nova });
const idNovaNota = nova?.id;

// Uma conciliada do Omie da base local, para o botão de recebida (sem mudar nada nela no fim).
const { dados: concs } = await api("GET", "/notas?status=CONCILIADA&origem=OMIE&limite=20", undefined, token);
let alvo = null;
for (const n of concs ?? []) {
  const { dados: d } = await api("GET", `/notas/${n.id}`, undefined, token);
  if (d?.pode_receber) { alvo = d; break; }
}

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1000 });
  await p.goto(WEB + "/login", { timeout: 180000 });
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. marcar como recebida");
  if (!alvo) {
    console.log("  (a base local não tem nota conciliada do Omie que possa ser recebida — pulando 1 e 2)");
  } else {
    await p.goto(`${WEB}/compras/${alvo.id}`, { waitUntil: "networkidle2", timeout: 180000 });
    await p.waitForSelector("#nota-marcar-recebida", { timeout: 60000 }).catch(() => {});
    checar("a conciliada do Omie oferece 'Marcar como recebida'", !!(await p.$("#nota-marcar-recebida")));
    await p.click("#nota-marcar-recebida").catch(() => {});
    await p.waitForSelector("#nota-recebido-por", { timeout: 10000 }).catch(() => {});
    checar("a janela pede quem recebeu", !!(await p.$("#nota-recebido-por")));
    // Sem nome: não marca. (O `required` do campo seguraria o envio; tirar mostra a frase da casa.)
    await p.evaluate(() => document.querySelector("#nota-recebido-por")?.removeAttribute("required"));
    await p.click('#form-recebida button[type="submit"]').catch(() => {});
    await esperar(800);
    const { dados: semNome } = await api("GET", `/notas/${alvo.id}`, undefined, token);
    checar("sem o nome, não marca", semNome?.status === "CONCILIADA", semNome?.status);
    checar("e a janela diz o que fazer", await p.evaluate(() => /nome de quem recebeu/i.test(document.body.innerText)));
    await p.type("#nota-recebido-por", `Pessoa Tela ${MARCA}`);
    await p.click('#form-recebida button[type="submit"]').catch(() => {});
    await p.waitForSelector("#nota-recebida-por", { timeout: 15000 }).catch(() => {});
    const linha = await p.$eval("#nota-recebida-por", (e) => e.innerText).catch(() => "");
    checar("marcada, a nota mostra quem recebeu", linha.includes(`Pessoa Tela ${MARCA}`), linha);
    checar("e oferece desfazer", !!(await p.$("#nota-desfazer-recebida")));

    console.log("2. a lista de notas");
    await p.goto(`${WEB}/compras?situacao=RECEBIDA&busca=${encodeURIComponent(alvo.numero ?? "")}`,
                 { waitUntil: "networkidle2", timeout: 180000 });
    await p.waitForSelector("[data-recebido-por]", { timeout: 20000 }).catch(() => {});
    const naLista = await p.evaluate(() => [...document.querySelectorAll("[data-recebido-por]")].map((e) => e.textContent));
    checar("o filtro 'recebida' mostra a nota com quem recebeu", naLista.some((t) => t?.includes(`Pessoa Tela ${MARCA}`)), naLista);
  }

  console.log("3. a aba Entradas por nota");
  await p.goto(`${WEB}/estoque/painel?aba=entradas&de=${DIA}&ate=${DIA}`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#entradas-situacoes", { timeout: 60000 }).catch(() => {});
  checar("o painel tem a aba", !!(await p.$('[data-aba="entradas"]')));
  const sits = await p.$$eval("#entradas-situacoes [data-situacao]", (b) => b.map((x) => x.textContent?.trim() ?? ""))
    .catch(() => []);
  checar("com as situações: a conciliar, conciliada, recebida, lançada",
    ["a conciliar", "conciliada", "recebida", "lançada"].every((s) => sits.some((t) => t.startsWith(s))), sits);
  await p.waitForFunction((n) => document.querySelector("#entradas-itens")?.innerText.includes(n),
    { timeout: 20000 }, `VE${MARCA}`).catch(() => {});
  const tabela = await p.$eval("#entradas-itens", (t) => t.innerText).catch(() => "");
  checar("o item aparece com o número da nota", tabela.includes(`NF VE${MARCA}`), tabela.slice(0, 200));
  checar("e o link abre a nota", !!(await p.$(`#entradas-itens a[href="/compras/${idNovaNota}"]`)));

  console.log("4. por nota, filtro e Imprimir");
  await p.click('[data-leitura="nota"]').catch(() => {});
  await p.waitForFunction(() => location.search.includes("leitura=nota"), { timeout: 6000 }).catch(() => {});
  checar("'por nota' agrupa pela nota", !!(await p.$(`[data-grupo-entrada="n${idNovaNota}"]`)));
  await p.click('#entradas-situacoes [data-situacao="LANCADA"]').catch(() => {});
  await p.waitForFunction(() => location.search.includes("situacao=LANCADA"), { timeout: 6000 }).catch(() => {});
  await p.waitForFunction((n) => !document.querySelector("#entradas-itens")?.innerText.includes(n),
    { timeout: 15000 }, `VE${MARCA}`).catch(() => {});
  const soLancadas = await p.evaluate((n) => !(document.body.innerText.includes(`NF VE${n}`)), MARCA);
  checar("o filtro 'lançada' tira a nota que não foi lançada", soLancadas);
  checar("Imprimir está na aba",
    await p.evaluate(() => [...document.querySelectorAll("button")].some((b) => /^imprimir/i.test(b.textContent?.trim() ?? ""))));

  console.log("5. no celular");
  await p.setViewport({ width: 390, height: 844 });
  await p.goto(`${WEB}/estoque/painel?aba=entradas&de=${DIA}&ate=${DIA}`, { waitUntil: "networkidle2", timeout: 180000 });
  await p.waitForSelector("#entradas-situacoes", { timeout: 60000 }).catch(() => {});
  const rola = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  checar("sem rolagem lateral da página", !rola);
} finally {
  await navegador.close();
  if (alvo) await api("DELETE", `/notas/${alvo.id}/receber`, undefined, token);
  if (idNovaNota) await api("DELETE", `/notas/${idNovaNota}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
if (falhas.length) {
  for (const f of falhas) console.log("  -", f);
  process.exit(1);
}
