"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ProvedorSessao, useSessao } from "@/lib/sessao";
import { api, definirUnidade, unidadeAtual, urlArquivo } from "@/lib/api";
import { EVENTO_EMPRESA } from "@/lib/eventos";
import { ConviteInstalar } from "@/components/pwa";
import { ProvedorAvisos } from "@/components/aviso-flutuante";
import BarraSuperior from "@/components/barra-superior";
import BarraInferior from "@/components/barra-inferior";

/** O menu é montado pelas permissões de quem entrou. */
/** `chave` pode ser uma lista: a tela de Ajustes serve a quatro permissões e
    quem tem só a de perda também precisa chegar nela. */
const MENU: {
  grupo: string;
  itens: {
    href: string;
    nome: string;
    chave?: string | string[];
    /** Só entra no menu com o envio ao PDV ligado — ver `enviar_ao_pdv`. */
    soComEnvioAoPdv?: boolean;
    /** 🔑 Só entra com MAIS DE UMA loja. Com uma só, a visão da rede é o
        Início repetido — e item de menu que leva a uma tela redundante ensina
        a ignorar o menu. */
    soComVariasLojas?: boolean;
  }[];
}[] = [
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
      // ⚠️ Só aparece com o envio ao PDV LIGADO. Item de menu para um recurso
      // desligado é uma porta que abre numa tela que explica que não faz nada.
      {
        href: "/exportacao",
        nome: "Exportação para o PDV",
        chave: ["integracao.pdv", "admin.integracoes"],
        soComEnvioAoPdv: true,
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
      { href: "/rede", nome: "Visão da rede", chave: "cmv.painel", soComVariasLojas: true },
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

/**
 * O Início não pertence a grupo nenhum.
 *
 * 🔑 **Um grupo de um item só é uma pasta com um papel dentro.** "Operação"
 * existia para abrigar Início, Alertas e Ajuda — e as duas últimas foram para o
 * menu do usuário, onde a pessoa as procura: alerta e manual são de QUEM está
 * usando, não de um assunto do sistema. Sobrou o Início, e um cabeçalho de
 * grupo sobre ele só custava um clique para chegar à primeira tela.
 */
const INICIO = { href: "/", nome: "Início" };

const CHAVE_MENU = "botane.menu";

/**
 * A marca — e, embaixo dela, em que LOJA se está.
 *
 * 🔑 **A loja é legenda da empresa, não item de menu.** Ela vivia no topo do
 * menu lateral, do tamanho de um rótulo de seção, e no celular só aparecia com
 * a gaveta aberta — ou seja, justamente quem tem duas lojas não via em qual
 * estava sem abrir o menu. Aqui ela fica sempre à vista, e a hierarquia diz o
 * que é: o nome da casa em cima, a loja embaixo, menor.
 */
function Marca({
  logo,
  nome,
  loja,
}: {
  logo: string | null;
  nome: string;
  loja?: React.ReactNode;
}) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      {logo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={logo} alt="" className="h-8 w-8 shrink-0 rounded object-contain" />
      ) : null}
      <span className="flex min-w-0 flex-col leading-none">
        <span className="truncate text-[19px] font-extrabold tracking-[-0.03em]">{nome}</span>
        {loja}
      </span>
    </span>
  );
}

function Casca({ children }: { children: React.ReactNode }) {
  const { eu, carregando, pode } = useSessao();
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

  // Com uma loja só, é legenda; com mais de uma, é escolha — e a escolha fica no
  // mesmo lugar onde a legenda estaria, que é onde se olha para saber onde se está.
  const daLoja =
    eu.unidades.length > 1 ? (
      <select
        className="mono mt-0.5 -ml-1 max-w-[170px] truncate rounded border border-transparent bg-transparent px-1 py-0 text-[11.5px] text-suave hover:border-linha2"
        value={unidadeAtual() ?? String(eu.unidades[0].id)}
        aria-label="Loja"
        onChange={(e) => {
          definirUnidade(Number(e.target.value));
          // Recarrega a página inteira de propósito: cada tela já buscou saldo,
          // alerta e apuração da loja anterior, e atualizar uma por uma deixaria
          // número de loja trocada na tela até a próxima navegação.
          window.location.reload();
        }}
      >
        {eu.unidades.map((u) => (
          <option key={u.id} value={u.id}>
            {u.apelido ?? u.nome}
          </option>
        ))}
      </select>
    ) : loja ? (
      <span className="mono mt-0.5 truncate text-[11.5px] uppercase tracking-[0.06em] text-suave">
        {loja.apelido ?? loja.nome}
      </span>
    ) : null;

  const navegacao = (
    <MenuLateral
            enviaAoPdv={!!eu?.enviar_ao_pdv}
      variasLojas={(eu?.unidades.length ?? 0) > 1}
      caminho={caminho}
      pode={pode}
      abertos={abertos}
      alternarGrupo={alternarGrupo}
      aoNavegar={() => setAberto(false)}
    />
  );

  // 🔑 **O bloco de usuário saiu do pé do menu e foi para o topo.** Aqui ele
  // era texto com dois botões pequenos, e no celular — onde a gaveta nasce
  // fechada — sair do sistema exigia abrir o menu e rolar até o fim. Agora vive
  // em `BarraSuperior`, no canto superior direito, que é onde todo mundo já
  // procura. O menu lateral voltou a ser só navegação.

  return (
    <div className="min-h-screen">
      {/* A barra do topo atravessa a tela inteira — inclusive no desktop, onde
          antes só existia no celular. É ela que carrega a marca e quem entrou. */}
      <BarraSuperior
        marca={<Marca logo={marca.logo} nome={marca.nome} loja={daLoja} />}
        aoAbrirMenu={() => setAberto(true)}
      />

      <div className="lg:grid lg:grid-cols-[240px_minmax(0,1fr)]">
      {aberto && (
        <div
          className="fixed inset-0 z-40 bg-tinta/35 lg:hidden"
          onClick={() => setAberto(false)}
          aria-hidden
        />
      )}

      {/* ⚠️ `top-14` e `h-[calc(100vh-3.5rem)]`: a barra do topo tem 56px, e sem
          descontá-los o menu ficava com o próprio topo escondido atrás dela. */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-[268px] flex-col overflow-y-auto border-r border-linha bg-superficie transition-transform duration-200 lg:sticky lg:top-14 lg:z-auto lg:h-[calc(100vh-3.5rem)] lg:w-auto lg:translate-x-0 ${
          aberto ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* No desktop a marca já está na barra do topo — repeti-la aqui seria o
            mesmo nome duas vezes na mesma linha do olho. Na gaveta do celular
            ela fica, porque a gaveta COBRE a barra. */}
        <div className="flex shrink-0 items-center justify-between gap-2 px-5 pb-4 pt-5 lg:hidden">
          <Marca logo={marca.logo} nome={marca.nome} />
          <button
            className="link-acao lg:hidden"
            onClick={() => setAberto(false)}
            aria-label="Fechar menu"
          >
            fechar
          </button>
        </div>

        {/* min-h-0 + overflow no meio: sem isso o flex comprime os grupos do menu
            quando ele cresce, e os rótulos se sobrepõem. */}
        <div className="min-h-0 flex-1 overflow-y-auto">{navegacao}</div>
      </aside>

      {/* ⚠️ `pb-14`: o rodapé é FIXO, então ele não empurra nada — sem a folga,
          o último botão de um formulário fica atrás dele. */}
      <main className="min-w-0 px-4 py-6 pb-14 sm:px-6 lg:px-10 lg:py-9 lg:pb-14">
        <div className="mx-auto max-w-[1180px]">
          <ConviteInstalar />
          {children}
        </div>
      </main>
      </div>

      <BarraInferior />
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
  enviaAoPdv,
  variasLojas,
  abertos,
  alternarGrupo,
  aoNavegar,
}: {
  caminho: string;
  pode: (chave: string) => boolean;
  /** Dica de interface: item de menu para recurso desligado é porta que não leva a nada. */
  enviaAoPdv: boolean;
  /** A casa tem mais de uma loja que esta pessoa enxerga. */
  variasLojas: boolean;
  abertos: Record<string, boolean>;
  alternarGrupo: (grupo: string, expandidoAgora: boolean) => void;
  aoNavegar: () => void;
}) {
  return (
    // ⚠️ A folga do topo vive no `nav`, e não no `aside`: com a marca e a loja
    // na barra superior, o Início era o primeiro elemento da lateral e encostava
    // na borda de baixo da barra — dois blocos colados, sem respiro entre eles.
    <nav className="px-3 pb-5 pt-4">
      {/* Fora de grupo: a primeira tela não se abre com um clique a mais. */}
      <Link
        href={INICIO.href}
        onClick={aoNavegar}
        className={`menu-raiz mb-0.5 ${caminho === INICIO.href ? "menu-raiz-ativo" : ""}`}
      >
        {INICIO.nome}
      </Link>
      {MENU.map((g) => {
        const itens = g.itens.filter(
          (i) =>
            (!i.chave || (Array.isArray(i.chave) ? i.chave.some(pode) : pode(i.chave))) &&
            (!i.soComEnvioAoPdv || enviaAoPdv) &&
            (!i.soComVariasLojas || variasLojas),
        );
        if (!itens.length) return null;
        const temAtivo = itens.some((i) => i.href === caminho);
        // 🔑 **O padrão é RECOLHIDO — todos.** O grupo da tela aberta já veio
        // expandido sozinho, e o efeito era um menu que ia abrindo grupos
        // conforme se navegava: ao fim de dez minutos estavam todos abertos, e
        // a lista de vinte itens não cabia mais na altura da tela. A pista de
        // "você está aqui" não se perde — o título do grupo fica verde, e ele
        // continua abrindo com um clique.
        const expandido = abertos[g.grupo] ?? false;
        return (
          <div key={g.grupo} className="mb-0.5 shrink-0">
            <button
              type="button"
              aria-expanded={expandido}
              onClick={() => alternarGrupo(g.grupo, expandido)}
              className={`menu-grupo ${temAtivo ? "menu-grupo-ativo" : ""}`}
            >
              <span>{g.grupo}</span>
              <svg
                viewBox="0 0 10 6"
                aria-hidden="true"
                className={`h-[6px] w-[10px] shrink-0 opacity-70 transition-transform duration-200 ${
                  expandido ? "" : "-rotate-90"
                }`}
              >
                <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6"
                      strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <ul className={`flex flex-col gap-px pb-2 ${expandido ? "" : "hidden"}`}>
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
                      className={`menu-item ${ativo ? "menu-item-ativo" : ""}`}
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
