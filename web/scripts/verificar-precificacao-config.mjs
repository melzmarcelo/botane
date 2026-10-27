/**
 * Precificação ▸ Configuração: a linha presa a uma categoria DESATIVADA, no navegador.
 *
 * 🔑 Relato do dono (27/10/2026): *"todas elas estão apresentando VALE PARA tudo, não
 * está mostrando a categoria correta"*. A reestruturação de 25/10 desativou as categorias
 * antigas; o seletor só oferecia as ativas, e o navegador mostrava a primeira opção
 * ("tudo") com o valor certo guardado por baixo. Confere:
 *   1. a linha mostra a categoria dela, marcada "(desativada)", e o cartão avisa;
 *   2. a margem de categoria igual à geral diz "igual à geral";
 *   3. salvar sem mexer mantém a categoria (nada vira "tudo").
 * A configuração da loja é guardada antes e devolvida no fim.
 *
 *    node scripts/verificar-precificacao-config.mjs   (API na 9200 e web na 3100 de pé)
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

const { dados: antes } = await api("GET", "/precificacao/config", undefined, token);
const devolver = {
  id_unidade_origem: antes.id_unidade_origem ?? null, arredondamento: antes.arredondamento,
  linhas: (antes.linhas ?? []).map((l) => ({ nome: l.nome, tipo: l.tipo, valor: l.valor, alcance: l.alcance,
                                            id_categoria: l.id_categoria, id_setor: l.id_setor })),
};

console.log("0. cenário: uma categoria desativada com margem, e uma ativa igual à geral");
const { dados: velha } = await api("POST", "/categorias", { nome: `VELHA PRECIF ${MARCA}` }, token);
const { dados: nova } = await api("POST", "/categorias", { nome: `NOVA PRECIF ${MARCA}` }, token);
await api("PUT", `/categorias/${velha.id}`, { nome: `VELHA PRECIF ${MARCA}`, ativo: false }, token);
const r0 = await api("PUT", "/precificacao/config", {
  id_unidade_origem: null, arredondamento: "NOVENTA",
  linhas: [
    { nome: "Impostos", tipo: "PERCENTUAL", valor: 10, alcance: "TUDO" },
    { nome: "Margem", tipo: "MARGEM", valor: 30, alcance: "TUDO" },
    { nome: "Margem", tipo: "MARGEM", valor: 48.5, alcance: "CATEGORIA", id_categoria: velha.id },
    { nome: "Margem", tipo: "MARGEM", valor: 30, alcance: "CATEGORIA", id_categoria: nova.id },
  ],
}, token);
checar("a configuração de teste grava", r0.status === 200, r0.dados);

const navegador = await puppeteer.launch({ executablePath: CHROME, headless: true });
try {
  const p = await navegador.newPage();
  await p.setViewport({ width: 1366, height: 1100 });
  await p.goto(WEB + "/login");
  await p.evaluate((a, r) => { localStorage.setItem("botane.access", a); localStorage.setItem("botane.refresh", r); localStorage.setItem("botane.unidade", "1"); },
                   login.access_token, login.refresh_token);
  await p.goto(`${WEB}/precificacao/configuracao`, { waitUntil: "networkidle2" });
  await p.waitForSelector(`[data-linha-precificacao="C:${velha.id}"]`, { timeout: 30000 }).catch(() => {});
  await esperar(1000);

  console.log("1. a linha da categoria desativada");
  const tela = await p.evaluate((idVelha, idNova) => {
    const linha = (v) => document.querySelector(`[data-linha-precificacao="${v}"]`);
    const sel = (v) => linha(v)?.querySelector('select[aria-label="Vale para"]');
    const mostrado = (v) => { const s = sel(v); return s ? s.options[s.selectedIndex]?.textContent : null; };
    return {
      velha: mostrado(`C:${idVelha}`), velhaTexto: linha(`C:${idVelha}`)?.innerText ?? "",
      nova: mostrado(`C:${idNova}`), novaTexto: linha(`C:${idNova}`)?.innerText ?? "",
      aviso: document.body.innerText.includes("apontam para categoria ou setor desativado"),
      ofereceVelhaNaGeral: [...(sel("TUDO")?.options ?? [])].some((o) => o.value === `C:${idVelha}`),
    };
  }, velha.id, nova.id);
  checar("mostra a categoria dela, marcada desativada (não 'tudo')",
    (tela.velha ?? "").includes(`VELHA PRECIF ${MARCA}`) && /desativada/.test(tela.velha ?? ""), tela.velha);
  checar("a linha diz que não vale para os produtos de hoje", /não vale para os produtos/.test(tela.velhaTexto), tela.velhaTexto);
  checar("o cartão avisa", tela.aviso);
  checar("a desativada não é oferecida às outras linhas", !tela.ofereceVelhaNaGeral);

  console.log("\n2. igual à geral");
  checar("a ativa com o mesmo valor da geral diz 'igual à geral'",
    (tela.nova ?? "").includes(`NOVA PRECIF ${MARCA}`) && /igual à geral/.test(tela.novaTexto), tela);

  console.log("\n3. salvar sem mexer mantém a categoria");
  await p.evaluate(() => [...document.querySelectorAll("button")].find((b) => /^Salvar/i.test(b.textContent?.trim() ?? ""))?.click());
  await esperar(2000);
  const { dados: depois } = await api("GET", "/precificacao/config", undefined, token);
  const l = (depois.linhas ?? []).find((x) => x.id_categoria === velha.id);
  checar("a linha segue na categoria desativada, não virou 'tudo'", !!l && l.alcance === "CATEGORIA",
    (depois.linhas ?? []).map((x) => [x.nome, x.alcance, x.id_categoria]));
} finally {
  await navegador.close();
  await api("PUT", "/precificacao/config", devolver, token);
  await api("DELETE", `/categorias/${velha.id}`, undefined, token);
  await api("DELETE", `/categorias/${nova.id}`, undefined, token);
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
for (const x of falhas) console.log("  -", x);
process.exit(falhas.length ? 1 : 0);
