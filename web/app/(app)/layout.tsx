"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ProvedorSessao, useSessao } from "@/lib/sessao";
import { api, definirUnidade, unidadeAtual, urlArquivo } from "@/lib/api";
import { EVENTO_EMPRESA } from "@/lib/eventos";
import { ConviteInstalar } from "@/components/pwa";
import { ProvedorAvisos } from "@/components/aviso-flutuante";

/** O menu é montado pelas permissões de quem entrou. */
/** `chave` pode ser uma lista: a tela de Ajustes serve a quatro permissões e
    quem tem só a de perda também precisa chegar nela. */
const MENU: {
  grupo: string;
  itens: { href: string; nome: string; chave?: string | string[] }[];
}[] = [
  {
    grupo: "Operação",
    itens: [
      { href: "/", nome: "Início" },
      { href: "/alertas", nome: "Alertas" },
      // Sem chave: o manual explica o sistema a quem usa o sistema, e quem tem
      // menos permissão é justamente quem mais precisa dele.
      { href: "/ajuda", nome: "Ajuda" },
    ],
  },
  {
    grupo: "Cadastros",
    itens: [
      { href: "/produtos", nome: "Produtos", chave: "cadastros.produtos" },
      { href: "/fichas", nome: "Fichas técnicas", chave: "fichas.visualizar" },
      { href: "/fornecedores", nome: "Fornecedores", chave: "cadastros.fornecedores" },
      // As quatro num item só. Quem procura "local de estoque" no menu não o
      // encontra pelo nome — por isso a tela DIZ o que tem dentro, logo abaixo
      // do título, e cada aba tem endereço próprio (`?aba=locais`).
      {
        href: "/cadastros",
        nome: "Tabelas de apoio",
        chave: ["cadastros.setores", "cadastros.locais", "cadastros.categorias",
                "cadastros.unidades_medida", "cmv.grupos"],
      },
    ],
  },
  {
    grupo: "Estoque",
    itens: [
      { href: "/estoque", nome: "Saldos e movimentos", chave: "estoque.saldos" },
      {
        href: "/ajustes",
        nome: "Ajustes",
        // ⚠️ Lista de chaves: a tela serve a cinco tipos, e quem tem só a de
        // custo (ou só a de perda) também precisa chegar nela.
        chave: ["estoque.entradas", "estoque.saidas", "estoque.perdas",
                "estoque.transferencias", "estoque.custo"],
      },
      { href: "/producao", nome: "Produção", chave: "estoque.saidas" },
      { href: "/inventario", nome: "Inventário", chave: "estoque.inventario" },
    ],
  },
  {
    grupo: "Compras",
    itens: [{ href: "/compras", nome: "Notas de entrada", chave: "compras.notas" }],
  },
  {
    grupo: "CMV",
    itens: [
      { href: "/cmv", nome: "Painel de CMV", chave: "cmv.painel" },
      { href: "/vendas", nome: "Vendas", chave: "cmv.painel" },
    ],
  },
  {
    grupo: "Administração",
    itens: [
      { href: "/empresa", nome: "Empresa", chave: "admin.empresa" },
      { href: "/lojas", nome: "Lojas e parâmetros", chave: "admin.unidades" },
      { href: "/usuarios", nome: "Usuários", chave: "admin.usuarios" },
      { href: "/papeis", nome: "Papéis e permissões", chave: "admin.papeis" },
      { href: "/integracoes", nome: "Integrações", chave: "admin.integracoes" },
      { href: "/auditoria", nome: "Auditoria", chave: "admin.auditoria" },
    ],
  },
];

const CHAVE_MENU = "botane.menu";

function Marca({ logo, nome }: { logo: string | null; nome: string }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      {logo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={logo} alt="" className="h-7 w-7 shrink-0 rounded object-contain" />
      ) : null}
      <span className="truncate text-[20px] font-extrabold tracking-[-0.03em]">{nome}</span>
    </span>
  );
}

function Casca({ children }: { children: React.ReactNode }) {
  const { eu, carregando, pode, sair } = useSessao();
  const caminho = usePathname();
  const [aberto, setAberto] = useState(false);
  // Quais grupos do menu estão abertos. Fica no navegador porque é preferência
  // de quem usa: quem só mexe em estoque abre estoque uma vez e pronto.
  const [abertos, setAbertos] = useState<Record<string, boolean>>({});

  useEffect(() => {
    try {
      setAbertos(JSON.parse(localStorage.getItem(CHAVE_MENU) ?? "{}"));
    } catch {
      setAbertos({});
    }
  }, []);

  /**
   * Abre ou fecha um grupo.
   *
   * Recebe o estado que está na tela, e não só o que está guardado: o grupo da
   * página aberta começa expandido sem ninguém ter clicado nele, e sem isso o
   * primeiro clique gravaria "abrir" no que já está aberto — o grupo não
   * fecharia.
   */
  const alternarGrupo = (grupo: string, expandidoAgora: boolean) =>
    setAbertos((atuais) => {
      const novos = { ...atuais, [grupo]: !expandidoAgora };
      localStorage.setItem(CHAVE_MENU, JSON.stringify(novos));
      return novos;
    });
  const [marca, setMarca] = useState<{ nome: string; logo: string | null }>({
    nome: "Botané Deli e Café",
    logo: null,
  });

  // Fecha a gaveta ao navegar — no celular ela cobre a tela inteira.
  useEffect(() => setAberto(false), [caminho]);

  useEffect(() => {
    const fechar = (e: KeyboardEvent) => e.key === "Escape" && setAberto(false);
    window.addEventListener("keydown", fechar);
    return () => window.removeEventListener("keydown", fechar);
  }, []);

  useEffect(() => {
    if (!eu) return;
    const buscarMarca = () =>
      api
        .get<{ nome_fantasia: string | null; razao_social: string | null; logo_url: string | null }>(
          "/empresa",
        )
        .then((e) =>
          setMarca({
            nome: e.nome_fantasia || e.razao_social || "Botané Deli e Café",
            logo: urlArquivo(e.logo_url),
          }),
        )
        .catch(() => {});

    void buscarMarca();
    // A tela de empresa avisa quando o nome ou a logo mudam — sem isso o topo
    // só atualizaria no próximo carregamento da página.
    const ouvir = () => void buscarMarca();
    window.addEventListener(EVENTO_EMPRESA, ouvir);
    return () => window.removeEventListener(EVENTO_EMPRESA, ouvir);
  }, [eu]);

  if (carregando) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="rotulo">carregando…</p>
      </main>
    );
  }
  if (!eu) return null;

  const loja = eu.unidades[0];

  const navegacao = (
    <MenuLateral
      caminho={caminho}
      pode={pode}
      abertos={abertos}
      alternarGrupo={alternarGrupo}
      aoNavegar={() => setAberto(false)}
    />
  );

  // Trocar senha e sair são AÇÕES: em maiúsculas miúdas pareciam legenda, e
  // ninguém clica no que parece rótulo. Botão com borda, texto na caixa normal
  // e alvo grande o bastante para o dedo.
  const rodapeUsuario = (
    <div className="border-t border-linha px-4 py-4">
      <p className="truncate px-1 text-[14px] font-semibold">{eu.nome}</p>
      <p className="truncate px-1 text-[12.5px] text-suave">
        {eu.papeis.join(", ") || "sem papel"}
      </p>
      <div className="mt-3 grid grid-cols-[1fr_auto] gap-2">
        <Link
          href="/trocar-senha"
          className="btn btn-secundario whitespace-nowrap px-3 text-center text-[13px] no-underline"
        >
          Trocar senha
        </Link>
        <button
          type="button"
          className="btn btn-secundario whitespace-nowrap px-4 text-[13px] hover:border-erro hover:text-erro"
          onClick={() => void sair()}
        >
          Sair
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[240px_minmax(0,1fr)]">
      {/* ---------- celular: barra fixa + gaveta ---------- */}
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-linha bg-superficie px-4 py-3 lg:hidden">
        <button
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded border border-linha2 bg-superficie"
          onClick={() => setAberto(true)}
          aria-label="Abrir menu"
          aria-expanded={aberto}
        >
          <span className="flex flex-col gap-[3px]">
            <span className="block h-[2px] w-4 bg-tinta" />
            <span className="block h-[2px] w-4 bg-tinta" />
            <span className="block h-[2px] w-4 bg-tinta" />
          </span>
        </button>
        <Marca logo={marca.logo} nome={marca.nome} />
      </header>

      {aberto && (
        <div
          className="fixed inset-0 z-40 bg-tinta/35 lg:hidden"
          onClick={() => setAberto(false)}
          aria-hidden
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-[268px] flex-col overflow-y-auto border-r border-linha bg-superficie transition-transform duration-200 lg:sticky lg:top-0 lg:z-auto lg:h-screen lg:w-auto lg:translate-x-0 ${
          aberto ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex shrink-0 items-center justify-between gap-2 px-5 pb-4 pt-5">
          <Marca logo={marca.logo} nome={marca.nome} />
          <button
            className="link-acao lg:hidden"
            onClick={() => setAberto(false)}
            aria-label="Fechar menu"
          >
            fechar
          </button>
        </div>

        {/* Com uma loja só o seletor não aparece — mas o dado já é por loja. */}
        {loja && eu.unidades.length === 1 && (
          <p className="rotulo shrink-0 truncate px-5 pb-3">{loja.apelido ?? loja.nome}</p>
        )}
        {eu.unidades.length > 1 && (
          <div className="px-5 pb-3">
            <select
              className="campo mono py-1.5 text-[12px]"
              value={unidadeAtual() ?? String(eu.unidades[0].id)}
              onChange={(e) => {
                definirUnidade(Number(e.target.value));
                // Recarrega a página inteira de propósito: cada tela já buscou
                // saldo, alerta e apuração da loja anterior, e atualizar uma por
                // uma deixaria número de loja trocada na tela até a próxima
                // navegação.
                window.location.reload();
              }}
            >
              {eu.unidades.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.apelido ?? u.nome}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* min-h-0 + overflow no meio: sem isso o flex comprime os grupos do menu
            quando ele cresce, e os rótulos se sobrepõem. */}
        <div className="min-h-0 flex-1 overflow-y-auto">{navegacao}</div>
        <div className="shrink-0">{rodapeUsuario}</div>
      </aside>

      <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-10 lg:py-9">
        <div className="mx-auto max-w-[1180px]">
          <ConviteInstalar />
          {children}
        </div>
      </main>
    </div>
  );
}

export default function LayoutApp({ children }: { children: React.ReactNode }) {
  return (
    <ProvedorSessao>
      <ProvedorAvisos>
        <Casca>{children}</Casca>
      </ProvedorAvisos>
    </ProvedorSessao>
  );
}

/** O menu, num componente à parte — a casca já é grande o bastante. */
function MenuLateral({
  caminho,
  pode,
  abertos,
  alternarGrupo,
  aoNavegar,
}: {
  caminho: string;
  pode: (chave: string) => boolean;
  abertos: Record<string, boolean>;
  alternarGrupo: (grupo: string, expandidoAgora: boolean) => void;
  aoNavegar: () => void;
}) {
  return (
    <nav className="px-3 pb-5">
      {MENU.map((g) => {
        const itens = g.itens.filter(
          (i) => !i.chave || (Array.isArray(i.chave) ? i.chave.some(pode) : pode(i.chave)),
        );
        if (!itens.length) return null;
        const temAtivo = itens.some((i) => i.href === caminho);
        // O grupo da tela aberta começa expandido — mas é só o padrão: se a
        // pessoa o recolher, ele fica recolhido, inclusive nela. Quem quer o
        // menu enxuto não deve ser obrigado a manter um grupo aberto. A pista
        // de "você está aqui" não se perde: o título do grupo fica verde.
        const expandido = abertos[g.grupo] ?? temAtivo;
        return (
          <div key={g.grupo} className="mb-1.5 shrink-0">
            <button
              type="button"
              aria-expanded={expandido}
              onClick={() => alternarGrupo(g.grupo, expandido)}
              className={`flex w-full items-center justify-between rounded px-2 py-1.5 text-left hover:bg-superficie2 ${
                temAtivo ? "text-erva" : ""
              }`}
            >
              <span className="rotulo">{g.grupo}</span>
              <svg
                viewBox="0 0 10 6"
                aria-hidden="true"
                className={`h-[6px] w-[10px] shrink-0 transition-transform duration-150 ${
                  expandido ? "" : "-rotate-90"
                }`}
              >
                <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6"
                      strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <ul className={`flex flex-col gap-0.5 pb-2 ${expandido ? "" : "hidden"}`}>
              {itens.map((i) => {
                const ativo = caminho === i.href;
                return (
                  <li key={i.href}>
                    <Link
                      href={i.href}
                      // A gaveta do celular fecha por mudança de CAMINHO, e as
                      // quatro tabelas de apoio compartilham o mesmo: sem
                      // fechar aqui, trocar de aba deixava o menu por cima.
                      onClick={aoNavegar}
                      className={`block rounded py-2.5 pl-4 pr-2 text-[15px] lg:py-1.5 lg:text-[14.5px] ${
                        ativo
                          ? "bg-erva-claro font-semibold text-erva"
                          : "text-tinta hover:bg-superficie2"
                      }`}
                    >
                      {i.nome}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}
