"use client";

/**
 * Cliente único de API. Nenhuma tela chama fetch direto — é a regra da casa.
 * Cuida do token, renova sozinho quando o access expira e derruba a sessão
 * quando nem o refresh vale mais.
 */

const BASE = process.env.NEXT_PUBLIC_API ?? "http://127.0.0.1:9200";

const CHAVE_ACCESS = "botane.access";
const CHAVE_REFRESH = "botane.refresh";
const CHAVE_UNIDADE = "botane.unidade";

/**
 * A loja escolhida no seletor.
 *
 * Vai em cabeçalho, não em parâmetro de cada chamada: assim vale para toda a
 * API de uma vez e nenhuma tela precisa lembrar de repassá-la. O servidor
 * confere se a pessoa enxerga aquela loja — mandar o cabeçalho não dá acesso a
 * nada.
 */
export const unidadeAtual = () =>
  typeof window === "undefined" ? null : localStorage.getItem(CHAVE_UNIDADE);

export const definirUnidade = (id: number | null) => {
  if (id === null) localStorage.removeItem(CHAVE_UNIDADE);
  else localStorage.setItem(CHAVE_UNIDADE, String(id));
};

export type Sessao = { access_token: string; refresh_token: string; usuario: Usuario };

export type Usuario = {
  id: number;
  nome: string;
  email: string;
  trocar_senha?: boolean;
};

export type Eu = {
  id: number;
  nome: string;
  email: string;
  telefone: string | null;
  foto_url: string | null;
  trocar_senha: boolean;
  permissoes: string[];
  papeis: string[];
  unidades: { id: number; nome: string; apelido: string | null; matriz: boolean }[];
  todas_unidades: boolean;
};

export class ErroApi extends Error {
  status: number;
  constructor(status: number, mensagem: string) {
    super(mensagem);
    this.status = status;
  }
}

/**
 * Onde a sessão mora — e é a escolha de quem entrou que decide.
 *
 * `sessionStorage` morre quando o navegador fecha; `localStorage` sobrevive.
 * Antes era sempre `localStorage`: fechar o navegador não encerrava nada, e
 * num computador compartilhado a sessão ficava aberta para o próximo.
 *
 * ⚠️ **`sessionStorage` é POR ABA.** Abrir o sistema numa aba nova pede login
 * de novo — é o preço de "fecha quando eu fecho o navegador", e é justamente
 * o que "manter conectado" resolve para quem prefere o contrário.
 *
 * ⚠️ **O front esquecer não é segurança.** Quem garante a promessa é a
 * validade curta do refresh no servidor (`REFRESH_SESSAO_HORAS`): um token
 * copiado não está preso ao navegador de ninguém.
 */
const guarda = (persistente: boolean) => (persistente ? localStorage : sessionStorage);

/** Lê dos dois: a sessão pode estar em qualquer um, e só um deles a tem. */
const lerSessao = (chave: string) =>
  typeof window === "undefined"
    ? null
    : sessionStorage.getItem(chave) ?? localStorage.getItem(chave);

export const guardarSessao = (
  s: { access_token: string; refresh_token: string },
  persistente?: boolean,
) => {
  // Sem dizer o modo (é o caso da RENOVAÇÃO), mantém onde já estava — senão
  // renovar mudaria a escolha da pessoa pelas costas.
  // ⚠️ Aqui a pergunta é "está no localStorage?", e não "existe em algum
  // lugar?" — por isso NÃO passa por `lerSessao`, que olha os dois.
  const onde =
    persistente === undefined
      ? localStorage.getItem(CHAVE_REFRESH) !== null
        ? localStorage
        : sessionStorage
      : guarda(persistente);
  // Nunca deixar cópia no outro: duas fontes divergentes fariam `lerSessao`
  // devolver um token velho depois de um logout parcial.
  [localStorage, sessionStorage].forEach((s2) => {
    if (s2 !== onde) {
      s2.removeItem(CHAVE_ACCESS);
      s2.removeItem(CHAVE_REFRESH);
    }
  });
  onde.setItem(CHAVE_ACCESS, s.access_token);
  onde.setItem(CHAVE_REFRESH, s.refresh_token);
};

export const limparSessao = () => {
  [localStorage, sessionStorage].forEach((s2) => {
    s2.removeItem(CHAVE_ACCESS);
    s2.removeItem(CHAVE_REFRESH);
    // A loja escolhida é da sessão: quem entra depois não herda a escolha de
    // quem saiu — e pode nem enxergar aquela loja.
    s2.removeItem(CHAVE_UNIDADE);
  });
};

/** Caminho de imagem devolvido pela API (`/arquivos/...`) vira URL completa. */
export const urlArquivo = (u?: string | null) =>
  !u ? null : u.startsWith("http") ? u : BASE + u;

export const temSessao = () => !!lerSessao(CHAVE_ACCESS);

async function bruto(metodo: string, caminho: string, corpo?: unknown, token?: string | null) {
  const r = await fetch(BASE + caminho, {
    method: metodo,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(unidadeAtual() ? { "X-Unidade": unidadeAtual()! } : {}),
    },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
    cache: "no-store",
  });
  return r;
}

function mensagemDoErro(dados: unknown, status: number): string {
  const d = dados as { detail?: unknown };
  if (typeof d?.detail === "string") return d.detail;
  if (Array.isArray(d?.detail)) {
    // erro de validação do Pydantic: mostra o primeiro campo, não o JSON inteiro
    const primeiro = d.detail[0] as { loc?: string[]; msg?: string };
    const campo = primeiro?.loc?.slice(1).join(".") ?? "";
    return campo ? `${campo}: ${primeiro?.msg}` : String(primeiro?.msg ?? "Dados inválidos");
  }
  return `Erro ${status}`;
}

/**
 * Lê o corpo da resposta sem nunca estourar por não ser JSON.
 *
 * ⚠️ **Quem responde não é só a API.** Entre o navegador e o FastAPI há o
 * roteamento do App Platform, e quando ELE responde — app reiniciando, tempo
 * esgotado, 502 — o corpo é uma página HTML. `JSON.parse` nela levantava
 * `Unexpected token '<', "<!DOCTYPE "...`, e como isso acontecia **antes** de
 * olhar `r.ok`, o status real (503, 504) era engolido: a tela dizia um erro de
 * sintaxe onde a resposta certa era "o servidor não respondeu, tente de novo".
 *
 * ⚠️ Corpo vazio com status de erro também é caso real (504 sem corpo), e a
 * mensagem tem de continuar dizendo o status em vez de "null".
 */
async function corpoDaResposta(r: Response): Promise<{ dados: unknown; erro?: string }> {
  const texto = await r.text();
  if (!texto) return { dados: null };
  try {
    return { dados: JSON.parse(texto) };
  } catch {
    // Não é JSON. O texto pode ser uma página inteira — não vai para a tela.
    const fora = r.status >= 500 || r.status === 0;
    return {
      dados: null,
      erro: fora
        ? `O servidor não respondeu (erro ${r.status}). Se acabou de ser publicada uma versão, `
          + "espere alguns segundos e tente de novo."
        : `Resposta inesperada do servidor (${r.status}).`,
    };
  }
}

/**
 * 🔑 **Uma renovação por vez — e é isto que conserta a queda no meio do uso.**
 *
 * O refresh do servidor é ROTATIVO: o token antigo morre no instante em que o
 * novo nasce. As telas disparam várias chamadas ao mesmo tempo (Integrações
 * pede quatro), então, quando o access vence, TODAS levam 401 juntas e todas
 * chamavam `renovar()` com o **mesmo** refresh. A primeira rotacionava e
 * revogava; as outras chegavam com token morto, recebiam 401 e caíam no
 * `limparSessao()` — sessão encerrada sem ninguém ter feito nada errado.
 *
 * Agora a primeira chamada cria a promessa e as demais **esperam a mesma**:
 * uma requisição de refresh, um token novo, todo mundo segue com ele.
 *
 * ⚠️ A trava é por ABA. Duas abas ainda podem correr entre si — quem cobre
 * esse caso é a janela de graça do servidor (`REFRESH_GRACA_SEGUNDOS`).
 */
let renovacaoEmCurso: Promise<boolean> | null = null;

async function renovar(): Promise<boolean> {
  if (!renovacaoEmCurso) {
    renovacaoEmCurso = (async () => {
      const refresh = lerSessao(CHAVE_REFRESH);
      if (!refresh) return false;
      const r = await bruto("POST", "/auth/refresh", { refresh_token: refresh });
      if (!r.ok) return false;
      // ⚠️ Sem dizer o modo: a renovação MANTÉM onde a sessão já estava. Dizer
      // aqui mudaria a escolha da pessoa pelas costas.
      guardarSessao(await r.json());
      return true;
    })().finally(() => {
      // Liberar só depois de gravar o token novo — soltar antes deixaria a
      // próxima chamada ler o refresh velho e recomeçar a corrida.
      renovacaoEmCurso = null;
    });
  }
  return renovacaoEmCurso;
}

async function pedir<T>(metodo: string, caminho: string, corpo?: unknown): Promise<T> {
  let token = lerSessao(CHAVE_ACCESS);
  let r = await bruto(metodo, caminho, corpo, token);

  if (r.status === 401 && (await renovar())) {
    token = lerSessao(CHAVE_ACCESS);
    r = await bruto(metodo, caminho, corpo, token);
  }

  if (r.status === 401) {
    limparSessao();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new ErroApi(401, "Sessão expirada, entre de novo");
  }

  const { dados, erro } = await corpoDaResposta(r);
  if (erro) throw new ErroApi(r.status, erro);
  if (!r.ok) throw new ErroApi(r.status, mensagemDoErro(dados, r.status));
  return dados as T;
}

export const api = {
  get: <T,>(caminho: string) => pedir<T>("GET", caminho),

  /**
   * Como `get`, mas devolve também quantos existem no total (cabeçalho X-Total).
   *
   * ⚠️ `total` vem **nulo** quando o servidor não mandou o cabeçalho — o que
   * acontece de propósito ao virar a página: o total não muda dentro do mesmo
   * filtro, e contar de novo custaria a tabela inteira. Quem chama guarda o
   * total que já tinha (é o que `usePaginacao.setTotal` faz).
   */
  async listar<T>(caminho: string): Promise<{ itens: T[]; total: number | null }> {
    let token = lerSessao(CHAVE_ACCESS);
    let r = await bruto("GET", caminho, undefined, token);
    if (r.status === 401 && (await renovar())) {
      token = lerSessao(CHAVE_ACCESS);
      r = await bruto("GET", caminho, undefined, token);
    }
    const texto = await r.text();
    const dados = texto ? JSON.parse(texto) : [];
    if (!r.ok) throw new ErroApi(r.status, mensagemDoErro(dados, r.status));
    const cabecalho = r.headers.get("X-Total");
    return { itens: dados as T[], total: cabecalho === null ? null : Number(cabecalho) };
  },
  post: <T,>(caminho: string, corpo?: unknown) => pedir<T>("POST", caminho, corpo ?? {}),
  put: <T,>(caminho: string, corpo?: unknown) => pedir<T>("PUT", caminho, corpo ?? {}),
  delete: <T,>(caminho: string) => pedir<T>("DELETE", caminho),

  /** Envio de arquivo: sem Content-Type na mão — o browser monta o boundary. */
  async upload<T>(caminho: string, corpo: FormData): Promise<T> {
    const enviar = async () =>
      fetch(BASE + caminho, {
        method: "POST",
        headers: { Authorization: `Bearer ${lerSessao(CHAVE_ACCESS)}` },
        body: corpo,
      });

    let r = await enviar();
    if (r.status === 401 && (await renovar())) r = await enviar();

    const texto = await r.text();
    const dados = texto ? JSON.parse(texto) : null;
    if (!r.ok) throw new ErroApi(r.status, mensagemDoErro(dados, r.status));
    return dados as T;
  },

  /**
   * Baixa um arquivo da API. Não dá para usar um link simples: o endpoint exige
   * o token no cabeçalho, e o navegador não manda cabeçalho em navegação.
   */
  async baixar(caminho: string): Promise<void> {
    const pegar = async () =>
      fetch(BASE + caminho, {
        headers: { Authorization: `Bearer ${lerSessao(CHAVE_ACCESS)}` },
      });

    let r = await pegar();
    if (r.status === 401 && (await renovar())) r = await pegar();
    if (!r.ok) {
      const texto = await r.text();
      let dados: unknown = null;
      try {
        dados = texto ? JSON.parse(texto) : null;
      } catch {
        dados = null;
      }
      throw new ErroApi(r.status, mensagemDoErro(dados, r.status));
    }

    // O nome vem do servidor, no Content-Disposition.
    const cabecalho = r.headers.get("Content-Disposition") ?? "";
    const nome = /filename="?([^"]+)"?/.exec(cabecalho)?.[1] ?? "botane.csv";
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    a.remove();
    // Revogar na hora cancela o download em alguns navegadores.
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  },

  /**
   * @param manterConectado guarda a sessão no navegador (localStorage) em vez
   * de encerrá-la ao fechar. O servidor também precisa saber: é ele que decide
   * a validade do refresh, e o front esquecer não é segurança nenhuma.
   */
  async login(email: string, senha: string, manterConectado = false): Promise<Sessao> {
    const r = await bruto("POST", "/auth/login", {
      email,
      senha,
      manter_conectado: manterConectado,
    });
    // ⚠️ Mesmo cuidado do `pedir`: o login é a PRIMEIRA tela, e é justamente
    // durante uma publicação que ele pega o HTML do roteamento. Dizer "erro de
    // sintaxe" ali faz parecer senha errada.
    const { dados, erro } = await corpoDaResposta(r);
    if (erro) throw new ErroApi(r.status, erro);
    if (!r.ok) throw new ErroApi(r.status, mensagemDoErro(dados, r.status));
    guardarSessao(dados as Sessao, manterConectado);
    return dados as Sessao;
  },

  async logout() {
    const refresh = lerSessao(CHAVE_REFRESH);
    try {
      if (refresh) await pedir("POST", "/auth/logout", { refresh_token: refresh });
    } catch {
      // sessão já morta do outro lado: seguir e limpar aqui do mesmo jeito
    }
    limparSessao();
  },
};
