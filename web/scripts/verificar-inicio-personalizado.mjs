/**
 * Três melhorias pedidas pelo dono (06/11/2026), no navegador:
 *
 * 1. **O valor não estoura o cartão** — *"dependendo do monitor, o valor faturado e ticket médio do
 *    dashboard está estourando o quadrado"*: em várias larguras de tela, o número de cada cartão da
 *    faixa e do período cabe nele.
 * 2. **Prévia na janela de Imprimir** — *"adicionar a opção Prévia. Selecionando, na janela de
 *    filtros irá mostrar os dados do relatório, e no topo o botão de imprimir com as opções PDF ou
 *    Planilha"*.
 * 3. **A tela inicial de cada um** — *"permitir configuração no dashboard … com os dados que
 *    preferir e a posição que preferir. Gravar isto por usuário"*: ocultar, mudar a largura,
 *    reordenar, tirar um indicador, salvar; recarregada, a tela volta como ficou. No fim a
 *    preferência do admin volta a ser a que era.
 *
 *    node scripts/verificar-inicio-personalizado.mjs     (API na 9200 e o Next na 3100 de pé)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const API = "http://127.0.0.1:9200";
const WEB = "http://127.0.0.1:3100";
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
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const texto = await r.text();
  return { status: r.status, dados: texto ? JSON.parse(texto) : null };
}

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;
const CHAVE = "painel:inicio";
const { dados: antes } = await api("GET", `/preferencias/${CHAVE}`, undefined, token);
// Começa do padrão: um layout salvo de outra rodada mudaria o que se confere.
await api("DELETE", `/preferencias/${CHAVE}`, undefined, token);

const navegador = await puppeteer.launch({
  executablePath: CHROME, headless: "new", userDataDir: "scripts/_chrome-perfil-site",
  args: ["--no-sandbox"], defaultViewport: { width: 1280, height: 900 },
});
try {
  const p = await navegador.newPage();
  const erros = [];
  p.on("pageerror", (e) => erros.push(e.message));
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);

  console.log("1. o valor cabe no cartão, em várias larguras de tela");
  for (const largura of [1024, 1280, 1366, 1440, 1600, 1920]) {
    await p.setViewport({ width: largura, height: 900 });
    await p.goto(WEB + "/", { waitUntil: "networkidle2" });
    await p.waitForSelector("[data-grade-inicio]", { timeout: 20000 });
    const estouros = await p.$$eval(".faixa-valor, .periodo-valor", (els) => els
      .filter((e) => e.scrollWidth > e.parentElement.clientWidth + 1 || e.getBoundingClientRect().right > e.parentElement.getBoundingClientRect().right + 1)
      .map((e) => `${e.textContent} (${e.scrollWidth} > ${e.parentElement.clientWidth})`));
    const quantos = await p.$$eval(".faixa-valor, .periodo-valor", (els) => els.length);
    checar(`${largura}px: ${quantos} valores, nenhum passa da borda`, quantos > 0 && !estouros.length, estouros);
  }
  await p.setViewport({ width: 1440, height: 900 });

  console.log("\n2. a prévia na janela de Imprimir (Estoque)");
  await p.goto(WEB + "/estoque", { waitUntil: "networkidle2" });
  const abriu = await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "Imprimir");
    b?.click();
    return !!b;
  });
  checar("o botão Imprimir abre a janela", abriu);
  await p.waitForSelector('[data-formato="previa"]', { timeout: 15000 });
  checar("a janela oferece Planilha, PDF e Prévia",
    (await p.$$eval("[data-formato]", (els) => els.map((e) => e.dataset.formato))).join() === "csv,pdf,previa");
  await p.click('[data-formato="previa"]');
  await p.waitForSelector("[data-previa-dados] table tbody tr", { timeout: 30000 });
  const linhas = await p.$$eval("[data-previa-dados] table tbody tr", (els) => els.length);
  checar("selecionada, a prévia mostra os dados do relatório na janela", linhas > 0, linhas);
  checar("e o botão Imprimir fica no topo", !!(await p.$("[data-barra-previa] #previa-imprimir")));
  checar("o rodapé não tem mais o 'Gerar planilha'", !(await p.$$eval("button", (els) =>
    els.some((e) => /Gerar planilha|Imprimir PDF/.test(e.textContent)))));
  await p.click("#previa-imprimir");
  const opcoes = await p.$$eval("[data-imprimir]", (els) => els.map((e) => e.dataset.imprimir));
  checar("o Imprimir abre as opções PDF e Planilha", opcoes.join() === "pdf,csv", opcoes);
  // O filtro refaz a prévia: o título da folha continua lá depois de uma troca.
  await p.click('[data-formato="csv"]');
  checar("voltando para Planilha, a prévia sai e o botão do rodapé volta",
    !(await p.$("[data-previa-dados]")) && await p.$$eval("button", (els) => els.some((e) => e.textContent.includes("Gerar planilha"))));
  await p.keyboard.press("Escape");

  console.log("\n3. a tela inicial de cada um");
  await p.goto(WEB + "/", { waitUntil: "networkidle2" });
  await p.waitForSelector("#inicio-personalizar");
  const ordemAntes = await p.$$eval("[data-bloco]", (els) => els.map((e) => e.dataset.bloco));
  checar("sem nada salvo, o padrão: a faixa do dia primeiro", ordemAntes[0] === "hoje", ordemAntes);
  await p.click("#inicio-personalizar");
  await p.waitForSelector("[data-personalizar]");
  checar("Personalizar põe a moldura em cada quadro",
    (await p.$$eval("[data-moldura]", (els) => els.length)) === ordemAntes.length);
  // Oculta os atalhos; a atenção vira largura inteira; o período sobe uma posição.
  await p.click('[data-ocultar="atalhos"]');
  checar("o oculto vai para a bandeja", !!(await p.$('[data-mostrar="atalhos"]')));
  await p.click('[data-moldura="atencao"] [data-largura="12"]');
  const temPeriodo = !!(await p.$('[data-moldura="periodo"]'));
  if (temPeriodo) await p.click('[data-moldura="periodo"] [data-mover="-1"]');
  const temTicket = !!(await p.$('[data-indicador="ticket"]'));
  if (temTicket) await p.click('[data-indicador="ticket"]');
  const ordemEditada = await p.$$eval("[data-bloco]", (els) => els.map((e) => e.dataset.bloco));
  await p.click("#inicio-salvar-layout");
  await p.waitForFunction(() => !document.querySelector("[data-personalizar]"), { timeout: 10000 });

  const { dados: salvo } = await api("GET", `/preferencias/${CHAVE}`, undefined, token);
  const v = salvo?.valor;
  checar("gravou no servidor, por usuário", !!v && Array.isArray(v.blocos), salvo);
  checar("com os atalhos ocultos e a atenção inteira",
    v?.blocos.find((b) => b.id === "atalhos")?.oculto === true && v?.blocos.find((b) => b.id === "atencao")?.largura === 12, v?.blocos);
  if (temTicket) checar("e o ticket médio fora da faixa", v?.indicadores_ocultos?.includes("ticket"), v?.indicadores_ocultos);

  await p.reload({ waitUntil: "networkidle2" });
  await p.waitForSelector("[data-grade-inicio]");
  const ordemDepois = await p.$$eval("[data-bloco]", (els) => els.map((e) => e.dataset.bloco));
  checar("recarregada, a tela volta como ficou (ordem)", ordemDepois.join() === ordemEditada.join(), { ordemEditada, ordemDepois });
  checar("sem os atalhos", !ordemDepois.includes("atalhos"));
  // No padrão o período vem logo depois dos mais vendidos; subiu um, fica antes deles.
  if (temPeriodo) checar("com o período uma posição acima (antes dos mais vendidos)",
    ordemDepois.indexOf("periodo") === ordemDepois.indexOf("mais_vendidos") - 1, ordemDepois);
  checar("a atenção ocupa a linha inteira",
    await p.$eval('[data-bloco="atencao"]', (e) => e.className.includes("lg:col-span-12")));
  if (temTicket) checar("e a faixa sem o Ticket médio",
    !(await p.$$eval(".faixa-numero", (els) => els.some((e) => e.textContent.includes("Ticket médio")))));

  console.log("\n4. restaurar o padrão");
  await p.click("#inicio-personalizar");
  await p.waitForSelector("[data-personalizar]");
  await p.evaluate(() => [...document.querySelectorAll("[data-personalizar] button")].find((b) => b.textContent.includes("Restaurar"))?.click());
  await p.click("#inicio-salvar-layout");
  await p.waitForFunction(() => !document.querySelector("[data-personalizar]"), { timeout: 10000 });
  const ordemRestaurada = await p.$$eval("[data-bloco]", (els) => els.map((e) => e.dataset.bloco));
  checar("Restaurar o padrão devolve a tela de antes", ordemRestaurada.join() === ordemAntes.join(), ordemRestaurada);

  checar("sem erro de página", !erros.length, erros);
} finally {
  await navegador.close();
  // A preferência do admin volta a ser a que era antes da suíte.
  if (antes?.valor) await api("PUT", `/preferencias/${CHAVE}`, { valor: antes.valor }, token);
  else await api("DELETE", `/preferencias/${CHAVE}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const f of falhas) console.log("  -", f);
process.exit(falhas.length ? 1 : 0);
