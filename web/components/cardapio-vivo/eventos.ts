/**
 * A medição de atenção do Cardápio Vivo — sessão anônima e eventos em lote.
 *
 * 🔑 **O id da sessão é aleatório e não liga a ninguém.** Nada de telefone, nome ou
 * endereço aqui: o dado pessoal só existe na identificação opcional (fase 2), e nunca
 * entra no evento.
 * 🔑 **Lote por `sendBeacon`**: a cada 10 s, a cada 20 eventos e ao sair da página — o
 * navegador entrega o lote mesmo com a aba fechando, sem segurar a navegação.
 * ⚠️ **`text/plain`, não JSON**: em casa a web (3100) e a API (9200) são origens
 * diferentes, e o `sendBeacon` não manda `application/json` entre origens sem preflight.
 */

import { enderecoEventos } from "@/lib/cardapio-vivo";

export type TipoEvento =
  | "abriu_cardapio" | "viu_item" | "tocou_categoria" | "abriu_detalhe" | "adicionou"
  | "removeu" | "enviou_pedido" | "chamou_garcom" | "pediu_conta" | "saiu"
  // O complemento do dono (114).
  | "deslizou_frente" | "deslizou_tras" | "favoritou" | "desfavoritou" | "abriu_personalizacao"
  | "escolheu_opcao" | "abriu_hub" | "clicou_avaliacao" | "clicou_wifi"
  // Os cartões de conteúdo (120).
  | "viu_cartao" | "viu_secao" | "clicou_cartao"
  // Os anúncios (121).
  | "viu_anuncio" | "clicou_anuncio";

type Evento = {
  tipo: TipoEvento; item?: number; categoria?: number; subcategoria?: number; cartao?: number; anuncio?: number;
  /** 125: a variação do texto do anúncio (ausente = a original). */
  variante?: number;
  midia?: string; duracao_ms?: number; quando: number;
};

/** O que um cartão (ou a abertura de uma seção) vira quando sai da tela. */
export type ConteudoVisto =
  | { tipo: "viu_cartao"; cartao: number; midia?: string }
  | { tipo: "viu_secao"; categoria: number; subcategoria?: number; midia?: string }
  | { tipo: "viu_anuncio"; anuncio: number; variante?: number; midia?: string };

const CHAVE_SESSAO = "cardapio.sessao";
const CHAVE_RECUSA = "cardapio.sem_medicao";
const SESSAO_OCIOSA_MS = 4 * 60 * 60 * 1000;

function lerOuCriarSessao(): string {
  const nova = () =>
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      // Navegador antigo sem randomUUID: um v4 montado à mão é suficiente para um id anônimo.
      : "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
          (Number(c) ^ (Math.random() * 16) >> (Number(c) / 4)).toString(16));
  try {
    const guardada = JSON.parse(localStorage.getItem(CHAVE_SESSAO) ?? "null");
    if (guardada?.id && Date.now() - guardada.ultimo < SESSAO_OCIOSA_MS) {
      localStorage.setItem(CHAVE_SESSAO, JSON.stringify({ id: guardada.id, ultimo: Date.now() }));
      return guardada.id;
    }
    const id = nova();
    localStorage.setItem(CHAVE_SESSAO, JSON.stringify({ id, ultimo: Date.now() }));
    return id;
  } catch {
    return nova(); // sem armazenamento: uma sessão por abertura
  }
}

/**
 * O id anônimo da sessão, para quem precisa dele ANTES do medidor — o feed o manda ao servidor
 * para sortear o braço dos testes A/B (116). ⚠️ Quem recusou a medição não entra em teste.
 */
export function sessaoParaTestes(): string | null {
  return medicaoRecusada() ? null : lerOuCriarSessao();
}

export function medicaoRecusada(): boolean {
  try {
    return localStorage.getItem(CHAVE_RECUSA) === "1";
  } catch {
    return false;
  }
}

export function recusarMedicao(recusar: boolean) {
  try {
    if (recusar) localStorage.setItem(CHAVE_RECUSA, "1");
    else localStorage.removeItem(CHAVE_RECUSA);
  } catch {
    /* sem armazenamento: vale só nesta visita */
  }
}

function dispositivo(): string {
  const ua = navigator.userAgent;
  if (/iPad|Tablet/i.test(ua) || (navigator.maxTouchPoints > 1 && /Macintosh/.test(ua))) return "TABLET";
  if (/Mobi|Android|iPhone/i.test(ua)) return "CELULAR";
  return matchMedia("(pointer: fine)").matches ? "DESKTOP" : "OUTRO";
}

export class Medidor {
  private fila: Evento[] = [];
  private relogio: ReturnType<typeof setInterval> | null = null;
  private vendo = new Map<number, { inicio: number; midia: string }>();
  /** 120: os cartões e as aberturas de seção na tela, pela chave do passo ("c12", "s3-7"). */
  private vendoConteudo = new Map<string, { inicio: number; evento: ConteudoVisto }>();
  private sessao: string;
  private desligado: boolean;
  /** 125: o grupo desta visita nos anúncios, como o feed o deu — vai em cada lote. */
  grupoAnuncio: string | null = null;
  /** 125: avisa a tela quanto tempo o anúncio ficou à vista (o ritmo que aprende). */
  aoVerAnuncio: ((anuncio: number, duracaoMs: number) => void) | null = null;

  constructor(
    private loja: number,
    private mesa: string | null,
    private modo: string,
    private idioma: string,
    desligado = false,
    /** O catálogo do Cardápio Vivo aberto (117) — o servidor confere os itens contra ele. */
    private catalogo: number | null = null,
  ) {
    this.sessao = lerOuCriarSessao();
    this.desligado = desligado || medicaoRecusada();
  }

  iniciar() {
    if (this.relogio) return;
    this.relogio = setInterval(() => this.enviar(), 10_000);
    document.addEventListener("visibilitychange", this.aoEsconder);
    window.addEventListener("pagehide", this.aoSair);
  }

  parar() {
    if (this.relogio) clearInterval(this.relogio);
    this.relogio = null;
    document.removeEventListener("visibilitychange", this.aoEsconder);
    window.removeEventListener("pagehide", this.aoSair);
    this.fecharVisualizacoes();
    this.enviar();
  }

  /** O id anônimo da sessão — o pedido da mesa (115) o leva, para o cliente acompanhar. */
  get idSessao() {
    return this.sessao;
  }

  desligar(sim: boolean) {
    this.desligado = sim;
    if (sim) this.fila = [];
  }

  registrar(tipo: TipoEvento, extra: Omit<Evento, "tipo" | "quando"> = {}) {
    if (this.desligado) return;
    this.fila.push({ tipo, ...extra, quando: Date.now() });
    if (this.fila.length >= 20) this.enviar();
  }

  /** O item passou a ocupar ≥ 50% da tela. */
  comecouAVer(item: number, midia: string) {
    if (!this.vendo.has(item)) this.vendo.set(item, { inicio: Date.now(), midia });
  }

  /** Saiu (ou a aba escondeu): fecha o intervalo e vira um `viu_item` com a duração. */
  parouDeVer(item: number) {
    const v = this.vendo.get(item);
    if (!v) return;
    this.vendo.delete(item);
    const duracao = Date.now() - v.inicio;
    // Menos de 300 ms é o item passando na rolagem, não atenção.
    if (duracao >= 300) this.registrar("viu_item", { item, midia: v.midia, duracao_ms: duracao });
  }

  /** Um cartão ou uma abertura de seção passou a ocupar ≥ 50% da tela (120). */
  comecouAVerConteudo(chave: string, evento: ConteudoVisto) {
    if (!this.vendoConteudo.has(chave)) this.vendoConteudo.set(chave, { inicio: Date.now(), evento });
  }

  /** Saiu: vira `viu_cartao` ou `viu_secao`, com a duração — o mesmo piso de 300 ms do prato. */
  parouDeVerConteudo(chave: string) {
    const v = this.vendoConteudo.get(chave);
    if (!v) return;
    this.vendoConteudo.delete(chave);
    const duracao = Date.now() - v.inicio;
    if (duracao >= 300) this.registrar(v.evento.tipo, { ...v.evento, duracao_ms: duracao });
    // ⚠️ Mesmo abaixo de 300 ms: passar voando é exatamente o "pulou" que o ritmo precisa saber.
    if (v.evento.tipo === "viu_anuncio") this.aoVerAnuncio?.(v.evento.anuncio, duracao);
  }

  private fecharVisualizacoes() {
    for (const item of [...this.vendo.keys()]) this.parouDeVer(item);
    for (const chave of [...this.vendoConteudo.keys()]) this.parouDeVerConteudo(chave);
  }

  private aoEsconder = () => {
    if (document.visibilityState === "hidden") {
      this.fecharVisualizacoes();
      this.enviar();
    }
  };

  private aoSair = () => {
    this.fecharVisualizacoes();
    this.registrar("saiu");
    this.enviar();
  };

  enviar() {
    if (this.desligado || !this.fila.length) return;
    const agora = Date.now();
    const eventos = this.fila.splice(0, 60).map(({ quando, ...e }) => ({ ...e, idade_ms: agora - quando }));
    const corpo = JSON.stringify({
      sessao: this.sessao, loja: this.loja, mesa: this.mesa, modo: this.modo,
      dispositivo: dispositivo(), idioma: this.idioma, catalogo: this.catalogo,
      grupo_anuncio: this.grupoAnuncio, eventos,
    });
    const blob = new Blob([corpo], { type: "text/plain" });
    const foi = typeof navigator.sendBeacon === "function" && navigator.sendBeacon(enderecoEventos(), blob);
    if (!foi) {
      // Sem beacon (ou a fila do navegador cheia): um fetch que sobrevive à página.
      fetch(enderecoEventos(), { method: "POST", body: corpo, keepalive: true,
                                 headers: { "Content-Type": "text/plain" } }).catch(() => {});
    }
    if (this.fila.length) this.enviar();
  }
}
