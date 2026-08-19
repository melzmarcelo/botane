/**
 * Testa as regras do service worker sem navegador nenhum.
 *
 *   node scripts/testar-sw.mjs
 *
 * O `sw.js` roda num mundo que o Node não tem (`self`, `caches`, `fetch` com
 * evento). Em vez de simular tudo, monta-se um mundo mínimo, executa-se o
 * arquivo de verdade dentro dele e observa-se **o que ele decide**: respondeu
 * ao pedido (interceptou) ou deixou passar para a rede.
 *
 * A pergunta que este teste existe para responder é uma só: **a API pode ter
 * sido cacheada?** Se um dia alguém afrouxar essa regra, o saldo de um usuário
 * aparece para o próximo que entrar no mesmo aparelho.
 */

import { readFileSync } from "node:fs";
import vm from "node:vm";

let ok = 0;
const falhas = [];
const checar = (nome, condicao, extra = "") => {
  if (condicao) {
    ok++;
    console.log(`  ok   ${nome}`);
  } else {
    falhas.push(nome);
    console.log(`  FALHA ${nome} ${extra}`);
  }
};

/** Sobe o service worker num contexto de mentira e devolve o que ele registrou. */
function carregar({ dev = false } = {}) {
  const ouvintes = {};
  const guardados = new Set();

  const cacheFalso = {
    addAll: async (urls) => urls.forEach((u) => guardados.add(u)),
    put: async (req) => guardados.add(typeof req === "string" ? req : req.url),
    match: async () => undefined,
  };
  const contexto = {
    self: {
      location: { href: `http://127.0.0.1:3100/sw.js${dev ? "?dev=1" : ""}`, origin: "http://127.0.0.1:3100" },
      addEventListener: (nome, fn) => (ouvintes[nome] = fn),
      skipWaiting: async () => {},
      clients: { claim: async () => {} },
    },
    caches: {
      open: async () => cacheFalso,
      keys: async () => [],
      delete: async () => true,
      match: async () => undefined,
    },
    fetch: async () => ({ ok: true, clone: () => ({}) }),
    URL,
    Promise,
    console,
  };
  contexto.self.caches = contexto.caches;
  vm.createContext(contexto);
  vm.runInContext(readFileSync("public/sw.js", "utf8"), contexto);
  return { ouvintes, guardados, contexto };
}

/** Simula um pedido e diz se o worker interceptou (`respondWith`) ou não. */
function pedir(ouvintes, url, { mode = "no-cors", method = "GET" } = {}) {
  let interceptou = false;
  ouvintes.fetch({
    request: { url, method, mode },
    respondWith: () => {
      interceptou = true;
    },
  });
  return interceptou;
}

console.log("1. o que o worker guarda ao instalar");
const producao = carregar();
await producao.ouvintes.install({ waitUntil: (p) => p });
await new Promise((r) => setImmediate(r));
checar("guarda a página de sem-conexão", producao.guardados.has("/offline"),
  [...producao.guardados]);
checar("guarda o ícone", producao.guardados.has("/icone-192.png"));
checar("e mais nada — a casca é mínima", producao.guardados.size === 2,
  [...producao.guardados]);

console.log("2. a API nunca passa pelo cache");
const { ouvintes } = producao;
checar("a API na outra porta é ignorada",
  pedir(ouvintes, "http://127.0.0.1:9200/estoque/saldos") === false);
checar("o login é ignorado", pedir(ouvintes, "http://127.0.0.1:9200/auth/login") === false);
checar("um /api na mesma origem também é ignorado",
  pedir(ouvintes, "http://127.0.0.1:3100/api/qualquer") === false);
checar("as fontes do Google são ignoradas",
  pedir(ouvintes, "https://fonts.googleapis.com/css2?family=Newsreader") === false);

console.log("3. estático versionado é cache-first; HTML é network-first");
checar("o pedaço do Next é interceptado (tem hash no nome)",
  pedir(ouvintes, "http://127.0.0.1:3100/_next/static/chunks/main-abc123.js") === true);
checar("a navegação é interceptada, para ter a página de sem-conexão",
  pedir(ouvintes, "http://127.0.0.1:3100/estoque", { mode: "navigate" }) === true);
checar("o ícone é interceptado", pedir(ouvintes, "http://127.0.0.1:3100/icone-192.png") === true);
checar("POST nunca é interceptado",
  pedir(ouvintes, "http://127.0.0.1:3100/qualquer", { method: "POST" }) === false);

console.log("4. em desenvolvimento o cache de estático sai da frente");
const dev = carregar({ dev: true });
checar("o pedaço do Next passa direto no dev (senão o HMR quebra)",
  pedir(dev.ouvintes, "http://127.0.0.1:3100/_next/static/chunks/main.js") === false);
checar("o canal de recarga do dev é ignorado",
  pedir(dev.ouvintes, "http://127.0.0.1:3100/_next/webpack-hot-update.json") === false);
checar("mas a navegação continua tendo rede de segurança",
  pedir(dev.ouvintes, "http://127.0.0.1:3100/estoque", { mode: "navigate" }) === true);
checar("e a API segue ignorada no dev",
  pedir(dev.ouvintes, "http://127.0.0.1:9200/alertas") === false);

console.log("5. subir a versão joga fora o cache anterior");
const fonte = readFileSync("public/sw.js", "utf8");
checar("o nome do cache carrega a versão", /const VERSAO = "botane-v\d+"/.test(fonte));
checar("o activate apaga todo cache que não seja o da versão atual",
  /nomes\.filter\(\(n\) => n !== CACHE\)/.test(fonte));

console.log();
console.log(`${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((f) => console.log(`  - ${f}`));
process.exit(falhas.length ? 1 : 0);
