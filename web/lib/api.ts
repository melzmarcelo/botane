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

export const guardarSessao = (s: { access_token: string; refresh_token: string }) => {
  localStorage.setItem(CHAVE_ACCESS, s.access_token);
  localStorage.setItem(CHAVE_REFRESH, s.refresh_token);
};

export const limparSessao = () => {
  localStorage.removeItem(CHAVE_ACCESS);
  localStorage.removeItem(CHAVE_REFRESH);
  // A loja escolhida é da sessão: quem entra depois não herda a escolha de
  // quem saiu — e pode nem enxergar aquela loja.
  localStorage.removeItem(CHAVE_UNIDADE);
};

/** Caminho de imagem devolvido pela API (`/arquivos/...`) vira URL completa. */
export const urlArquivo = (u?: string | null) =>
  !u ? null : u.startsWith("http") ? u : BASE + u;

export const temSessao = () =>
  typeof window !== "undefined" && !!localStorage.getItem(CHAVE_ACCESS);

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

async function renovar(): Promise<boolean> {
  const refresh = localStorage.getItem(CHAVE_REFRESH);
  if (!refresh) return false;
  const r = await bruto("POST", "/auth/refresh", { refresh_token: refresh });
  if (!r.ok) return false;
  guardarSessao(await r.json());
  return true;
}

async function pedir<T>(metodo: string, caminho: string, corpo?: unknown): Promise<T> {
  let token = localStorage.getItem(CHAVE_ACCESS);
  let r = await bruto(metodo, caminho, corpo, token);

  if (r.status === 401 && (await renovar())) {
    token = localStorage.getItem(CHAVE_ACCESS);
    r = await bruto(metodo, caminho, corpo, token);
  }

  if (r.status === 401) {
    limparSessao();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new ErroApi(401, "Sessão expirada, entre de novo");
  }

  const texto = await r.text();
  const dados = texto ? JSON.parse(texto) : null;
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
    let token = localStorage.getItem(CHAVE_ACCESS);
    let r = await bruto("GET", caminho, undefined, token);
    if (r.status === 401 && (await renovar())) {
      token = localStorage.getItem(CHAVE_ACCESS);
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
        headers: { Authorization: `Bearer ${localStorage.getItem(CHAVE_ACCESS)}` },
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
        headers: { Authorization: `Bearer ${localStorage.getItem(CHAVE_ACCESS)}` },
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

  async login(email: string, senha: string): Promise<Sessao> {
    const r = await bruto("POST", "/auth/login", { email, senha });
    const texto = await r.text();
    const dados = texto ? JSON.parse(texto) : null;
    if (!r.ok) throw new ErroApi(r.status, mensagemDoErro(dados, r.status));
    guardarSessao(dados);
    return dados as Sessao;
  },

  async logout() {
    const refresh = localStorage.getItem(CHAVE_REFRESH);
    try {
      if (refresh) await pedir("POST", "/auth/logout", { refresh_token: refresh });
    } catch {
      // sessão já morta do outro lado: seguir e limpar aqui do mesmo jeito
    }
    limparSessao();
  },
};
