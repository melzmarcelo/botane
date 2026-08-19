/* eslint-disable no-restricted-globals */
/**
 * Service worker do Botané.
 *
 * As regras, em ordem de importância — nenhuma delas é afrouxável:
 *
 * 1. **A API nunca é cacheada.** Ela mora em outra origem (a 9200). Guardar
 *    resposta dela serviria saldo velho como novo, e — pior — o dado de um
 *    usuário para o próximo que entrasse no mesmo aparelho. O que a casa
 *    decide com esse número é comprar ou não comprar.
 * 2. **HTML é sempre network-first.** A tela tem de ser a que está no
 *    servidor; o cache só entra quando não há rede, e aí vira a página de
 *    "sem conexão".
 * 3. **Só o estático versionado é cache-first**, porque o nome carrega hash e
 *    o conteúdo nunca muda para a mesma URL.
 * 4. **Em desenvolvimento não se cacheia nada** além da casca offline: o
 *    servidor do Next troca os pedaços da página a cada gravação, e um cache
 *    esperto no meio faria o desenvolvedor caçar um bug que não existe.
 *
 * O nome do cache carrega a VERSAO: subir a versão joga fora o cache anterior
 * inteiro no `activate`. Sem isso, quem instalou ficaria preso numa versão
 * antiga sem nenhuma forma de sair.
 */

const VERSAO = "botane-v1";
const CACHE = `${VERSAO}-shell`;
const OFFLINE = "/offline";

// A página de "sem conexão" é o mínimo que precisa estar guardado desde a
// instalação: é justamente quando não há rede que ela é pedida.
const ESSENCIAIS = [OFFLINE, "/icone-192.png"];

const DESENVOLVIMENTO = new URL(self.location.href).searchParams.get("dev") === "1";

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ESSENCIAIS)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((nomes) =>
        Promise.all(nomes.filter((n) => n !== CACHE).map((n) => caches.delete(n))),
      )
      .then(() => self.clients.claim()),
  );
});

/** O estático do Next tem hash no nome: mesma URL, mesmo conteúdo, para sempre. */
const ehEstaticoVersionado = (url) =>
  url.origin === self.location.origin && url.pathname.startsWith("/_next/static/");

/** Ícone, manifesto e afins: mudam raramente e podem servir do cache enquanto revalidam. */
const ehAssetProprio = (url) =>
  url.origin === self.location.origin &&
  /\.(png|svg|ico|webmanifest)$/.test(url.pathname);

self.addEventListener("fetch", (evento) => {
  const requisicao = evento.request;
  if (requisicao.method !== "GET") return;

  const url = new URL(requisicao.url);

  // Regra 1: qualquer coisa de outra origem — a API e as fontes do Google —
  // passa direto, sem o service worker no meio.
  if (url.origin !== self.location.origin) return;

  // Cinto e suspensório: se um dia a API passar a morar na mesma origem
  // (atrás de um proxy), o caminho /api continua fora do cache.
  if (url.pathname.startsWith("/api")) return;

  // O canal de recarga automática do servidor de desenvolvimento.
  if (url.pathname.includes("__nextjs") || url.pathname.includes("hot-update")) return;

  if (!DESENVOLVIMENTO && ehEstaticoVersionado(url)) {
    evento.respondWith(
      caches.match(requisicao).then(
        (guardado) =>
          guardado ||
          fetch(requisicao).then((resposta) => {
            if (resposta.ok) {
              const copia = resposta.clone();
              caches.open(CACHE).then((cache) => cache.put(requisicao, copia));
            }
            return resposta;
          }),
      ),
    );
    return;
  }

  if (!DESENVOLVIMENTO && ehAssetProprio(url)) {
    evento.respondWith(
      fetch(requisicao)
        .then((resposta) => {
          if (resposta.ok) {
            const copia = resposta.clone();
            caches.open(CACHE).then((cache) => cache.put(requisicao, copia));
          }
          return resposta;
        })
        .catch(() => caches.match(requisicao)),
    );
    return;
  }

  // Regra 2: navegação é network-first, com a página de "sem conexão" como
  // rede de segurança.
  if (requisicao.mode === "navigate") {
    evento.respondWith(
      fetch(requisicao).catch(() =>
        caches.match(requisicao).then((guardado) => guardado || caches.match(OFFLINE)),
      ),
    );
    return;
  }

  // O resto (inclusive tudo em desenvolvimento) vai direto para a rede.
});
