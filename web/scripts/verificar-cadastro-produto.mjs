/**
 * O cadastro de produto no estilo do protótipo (pedido do dono, 05/11/2026).
 *
 * 🔑 *"gostei como no protótipo ficou o cadastro de produtos… com o resumo, o estilo do botão de
 * situação, colocar como visível se ele está no PDV, mas caso não utilize o envio das informações
 * não deixa alterar"*. Confere: o selo de situação ao lado do nome, o interruptor (a caixa nativa
 * redesenhada, com alvo de 44px), o Resumo com margem que mexe enquanto se digita o preço, e o
 * "Vende no PDV" sempre à vista — travado com o envio desligado, editável com ele ligado.
 * O produto de teste é criado pela API e desativado no fim; o envio volta ao que era.
 *
 *    node scripts/verificar-cadastro-produto.mjs     (API na 9200 e o Next na 3100 de pé)
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const API = "http://127.0.0.1:9200";
const WEB = "http://127.0.0.1:3100";
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
    headers: { "Content-Type": "application/json", "X-Unidade": "1", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const texto = await r.text();
  return { status: r.status, dados: texto ? JSON.parse(texto) : null };
}

const { dados: login } = await api("POST", "/auth/login", { email: "admin@botane.com.br", senha: "botane123" });
const token = login.access_token;

console.log("0. cenário: produto a R$ 20,00 com custo informado de R$ 5,00, sem código do PDV");
const { dados: prod } = await api("POST", "/produtos", { nome: `RESUMO TELA ${MARCA}`, tipo: "INSUMO", um_estoque: "UN", controla_estoque: false }, token);
const { dados: atual } = await api("GET", `/produtos/${prod.id}`, undefined, token);
await api("PUT", `/produtos/${prod.id}`, { ...atual, preco_venda: 20 }, token);
await api("PUT", `/produtos/${prod.id}/custo-informado`, { custo: 5 }, token);
const { dados: pdvAntes } = await api("GET", "/pdv/config", undefined, token);
const envio = (ligado) => api("PUT", "/pdv/config", {
  modo: pdvAntes?.modo ?? "simulado", ativa: pdvAntes?.ativa ?? false, enviar_ao_pdv: ligado,
  agenda_frequencia: pdvAntes?.agenda_frequencia ?? "MANUAL", agenda_hora: pdvAntes?.agenda_hora ?? 4,
  agenda_janela_dias: pdvAntes?.agenda_janela_dias ?? null,
}, token);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"],
                                           defaultViewport: { width: 1440, height: 1000 } });
try {
  await envio(false);
  const p = await navegador.newPage();
  const erros = [];
  p.on("pageerror", (e) => erros.push(e.message));
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  const abrir = async () => {
    await p.goto(`${WEB}/produtos/${prod.id}`, { waitUntil: "networkidle2" });
    await p.waitForFunction(() => document.querySelector('[data-resumo="custo"]')?.textContent.includes("5,00"), { timeout: 30000 }).catch(() => {});
  };
  await abrir();

  console.log("1. cabeçalho e interruptor");
  checar("o selo de situação diz Ativo, ao lado do nome",
    await p.$eval("#situacao-produto", (x) => x.textContent.trim()).catch(() => "") === "Ativo");
  const sw = await p.evaluate(() => {
    const i = document.querySelector('input[aria-label="Produto ativo"]');
    if (!i) return null;
    const e = getComputedStyle(i);
    return { aparencia: e.appearance, largura: e.width, alvo: i.closest("label")?.getBoundingClientRect().height ?? 0,
             papel: i.getAttribute("role") };
  });
  checar("Ativo é um interruptor (caixa redesenhada, role=switch)",
    sw?.aparencia === "none" && sw?.largura === "40px" && sw?.papel === "switch", sw);
  checar("com alvo de pelo menos 44px", (sw?.alvo ?? 0) >= 44, sw);
  await p.$eval('input[aria-label="Produto ativo"]', (i) => i.click());
  await esperar(200);
  checar("desligar troca o selo para Inativo antes de salvar",
    await p.$eval("#situacao-produto", (x) => x.textContent.trim()) === "Inativo");
  await p.$eval('input[aria-label="Produto ativo"]', (i) => i.click());

  console.log("\n2. o Resumo");
  const resumo = await p.evaluate(() => Object.fromEntries(
    [...document.querySelectorAll("[data-resumo]")].map((x) => [x.dataset.resumo, x.textContent.trim()])));
  checar("mostra custo, preço e a margem bruta (20 − 5) ÷ 20 = 75%",
    /5,00/.test(resumo.custo ?? "") && /20,00/.test(resumo.preco ?? "") && resumo.margem === "75,0%", resumo);
  checar("e diz que o produto não vai ao PDV", resumo.pdv === "Não vai ao PDV", resumo);
  // A margem mexe enquanto se digita o preço — sem salvar.
  const campoPreco = await p.evaluateHandle(() => [...document.querySelectorAll("label")]
    .find((l) => /^Preço de venda/.test(l.textContent?.trim() ?? ""))?.querySelector("input"));
  await campoPreco.focus();
  await p.keyboard.down("Control"); await p.keyboard.press("KeyA"); await p.keyboard.up("Control");
  await p.keyboard.press("Backspace");
  await campoPreco.type("10,00");
  await esperar(300);
  checar("digitar o preço muda a margem na hora (R$ 10 → 50%)",
    await p.$eval('[data-resumo="margem"]', (x) => x.textContent.trim()) === "50,0%",
    await p.$eval('[data-resumo="margem"]', (x) => x.textContent.trim()));

  console.log("\n3. Vende no PDV");
  const desligado = await p.evaluate(() => ({
    editavel: !!document.querySelector("#integrado_pdv"),
    travada: document.querySelector("#vende-no-pdv")?.disabled ?? null,
    explica: /envio ao PDV está desligado/.test(document.body.innerText),
  }));
  checar("com o envio desligado aparece travado e diz por quê",
    !desligado.editavel && desligado.travada === true && desligado.explica, desligado);
  await envio(true);
  await abrir();
  const ligado = await p.evaluate(() => ({
    editavel: document.querySelector("#integrado_pdv")?.disabled === false,
    travada: !!document.querySelector("#vende-no-pdv"),
  }));
  checar("com o envio ligado vira editável", ligado.editavel && !ligado.travada, ligado);

  console.log("\n4. no celular");
  await p.setViewport({ width: 390, height: 844 });
  await abrir();
  await esperar(500);
  checar("a tela não rola para o lado (390 px)", await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  checar("e o Resumo vem antes dos campos",
    await p.evaluate(() => {
      const r = document.querySelector("#resumo-produto")?.getBoundingClientRect().top ?? 1e9;
      const n = document.querySelector("#campo-nome")?.getBoundingClientRect().top ?? 0;
      return r < n;
    }));
  checar("nenhum erro de JavaScript", !erros.length, erros);
} finally {
  await navegador.close();
  await envio(!!pdvAntes?.enviar_ao_pdv);
  const { dados: fim } = await api("GET", `/produtos/${prod.id}`, undefined, token);
  if (fim) await api("PUT", `/produtos/${prod.id}`, { ...fim, ativo: false }, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((x) => console.log(`  - ${x}`));
process.exit(falhas.length ? 1 : 0);
