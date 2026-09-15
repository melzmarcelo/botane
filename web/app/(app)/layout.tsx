"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ProvedorSessao, useSessao } from "@/lib/sessao";
import { api, definirUnidade, urlArquivo } from "@/lib/api";
import { abrirBuscaDeTelas, EVENTO_EMPRESA } from "@/lib/eventos";
import { gravarAtalhos, lerAtalhos, TETO_ATALHOS } from "@/lib/atalhos";
import { INICIO, montarMenu, telasDisponiveis, type ItemMenu } from "@/lib/menu";
import { Carregando } from "@/components/ui";
import { ConviteInstalar } from "@/components/pwa";
import { ProvedorAvisos } from "@/components/aviso-flutuante";
import BarraSuperior from "@/components/barra-superior";
import BarraInferior from "@/components/barra-inferior";
import BarraNavegacao from "@/components/barra-navegacao";
import PaletaTelas from "@/components/paleta-telas";
import Icone from "@/components/icone";

/**
 * 🔑 **O MENU saiu daqui em 15/09/2026** e mora em `lib/menu.ts`: a mesma
 * lista passou a servir ao menu lateral, à busca do `Ctrl+K` e aos atalhos
 * fixados. Lista de navegação duplicada é lista que diverge — a tela nova
 * entra numa e não na outra, e a busca vira uma coisa em que não se confia.
 */

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
  const { eu, carregando, pode, unidade } = useSessao();
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
  // ⚠️ O valor marcado vem da SESSÃO, que aplica a mesma regra do servidor.
  // `unidadeAtual()` sozinho é nulo até alguém mexer no seletor, e o "primeiro
  // da lista" como reserva não é o padrão do servidor quando a matriz não é a
  // de menor id — o seletor mostraria uma loja e o pedido iria para outra.
  const daLoja =
    eu.unidades.length > 1 ? (
      <select
        className="mono mt-0.5 -ml-1 max-w-[170px] truncate rounded border border-transparent bg-transparent px-1 py-0 text-[11.5px] text-suave hover:border-linha2"
        value={String(unidade)}
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
      temReservas={!!eu?.reservas_ligado}
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

      {/* ⚠️ **276px, e nao 240** (15/09/2026, relatado pelo dono: *"alguns itens
          cortaram a descricao"*). Com o icone e o alfinete, a coluna de 240
          deixava ~169px para o texto — e "Saldos e movimentos", "Exportacao
          para o PDV" e "Papeis e permissoes" nao cabiam. Nome de tela cortado
          obriga a pessoa a adivinhar o destino, que e o contrario do que um
          menu faz. */}
      <div className="lg:grid lg:grid-cols-[276px_minmax(0,1fr)]">
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
        className={`fixed inset-y-0 left-0 z-50 flex w-[292px] flex-col overflow-y-auto border-r border-linha bg-superficie transition-transform duration-200 lg:sticky lg:top-14 lg:z-auto lg:h-[calc(100vh-3.5rem)] lg:w-auto lg:translate-x-0 ${
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
          o último botão de um formulário fica atrás dele.
          ⚠️ **No celular a folga é MAIOR** (`pb-28`): lá são duas barras fixas,
          a de navegação sobre a da versão. Sem isto o último botão do
          formulário nasce embaixo da navegação — e o defeito só apareceria no
          telefone, que é onde ninguém testa primeiro. */}
      <main className="min-w-0 px-4 py-6 pb-28 sm:px-6 lg:px-10 lg:py-9 lg:pb-14">
        <div className="mx-auto max-w-[1180px]">
          {/* 🔑 **A fronteira de Suspense que o `useSearchParams` exige.**
              As listas guardam filtro, página e "por página" na URL — é o que
              faz o voltar do navegador restaurar tudo.
              ⚠️ **Sem esta fronteira, o BUILD DE PRODUÇÃO quebra**, não o
              desenvolvimento: em `next dev` as rotas são montadas sob demanda e
              o hook não suspende, então tudo parece funcionar. É o próprio
              manual do Next que avisa ("a static page that calls
              useSearchParams from a Client Component must be wrapped in a
              Suspense boundary, otherwise the build fails"). Aqui em cima ela
              cobre as catorze listas de uma vez — e o custo, a página deixar de
              ser pré-renderizada, é zero neste app: tudo já é cliente atrás do
              login. */}
          <Suspense fallback={<Carregando />}>{children}</Suspense>

          {/* 🔑 **Depois do conteúdo, e não antes** (14/09/2026). Ele vinha no
              topo e aparecia TARDE — o `beforeinstallprompt` é disparado pelo
              navegador quando ele quer —, empurrando a página inteira 78px para
              baixo depois que ela já estava sendo lida. Quem estava prestes a
              clicar numa linha clicava noutra.
              ⚠️ Foi a bateria que expôs: a rolagem que posiciona a lista ao virar
              de página era calculada ANTES do convite chegar, e o topo do cartão
              parava fora da vista. O defeito era do convite, não da rolagem.
              ⚠️ Aqui embaixo ele continua aparecendo sozinho e sem deslocar nada:
              não há conteúdo depois dele para empurrar. */}
          <ConviteInstalar />
        </div>
      </main>
      </div>

      {/* 🔑 **No celular, as telas do dia a dia a um toque** (14/09/2026). A
          gaveta continua existindo — ela só deixa de ser o único caminho. */}
      <BarraNavegacao />
      <BarraInferior />

      {/* 🔑 **A busca de telas** (`Ctrl+K`, 15/09/2026). Fica aqui em cima, e
          não dentro do menu: o atalho de teclado tem de valer com a gaveta
          fechada, que é o estado normal no computador. */}
      <PaletaTelas />
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
  temReservas,
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
  temReservas: boolean;
  abertos: Record<string, boolean>;
  alternarGrupo: (grupo: string, expandidoAgora: boolean) => void;
  aoNavegar: () => void;
}) {
  const ambiente = { pode, enviaAoPdv, variasLojas, temReservas };
  const entradas = useMemo(
    () => montarMenu(ambiente),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pode, enviaAoPdv, variasLojas, temReservas],
  );
  const telas = useMemo(
    () => telasDisponiveis(ambiente),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pode, enviaAoPdv, variasLojas, temReservas],
  );

  /**
   * 🔑 **Ler o `localStorage` no inicializador é seguro AQUI**, e não seria em
   * qualquer lugar: este componente só monta depois do `/auth/me` (a casca
   * devolve `null` enquanto não há `eu`), então ele nunca participa da
   * hidratação. Num `useEffect`, os atalhos apareceriam um quadro depois e
   * empurrariam os grupos para baixo — a mesma classe de defeito do convite de
   * instalação, que deslocava a página inteira depois de ela já estar sendo lida.
   */
  const [atalhos, setAtalhos] = useState<string[]>(() => lerAtalhos(telas.map((t) => t.href)));

  const fixar = (href: string) =>
    setAtalhos((atuais) => {
      const novos = atuais.includes(href)
        ? atuais.filter((h) => h !== href)
        : [...atuais, href].slice(-TETO_ATALHOS);
      gravarAtalhos(novos);
      return novos;
    });

  const porHref = new Map(telas.map((t) => [t.href, t]));

  /**
   * Uma linha do menu: o link, e o alfinete ao lado.
   *
   * ⚠️ O alfinete é IRMÃO do link, nunca filho — `<button>` dentro de `<a>` é
   * HTML inválido, e o navegador desmancha a árvore em silêncio.
   */
  const linha = (item: ItemMenu, fixavel: boolean) => {
    const ativo = caminho === item.href;
    const fixado = atalhos.includes(item.href);
    return (
      <div key={item.href} className={`menu-linha ${fixavel ? "menu-linha-fixavel" : ""}`}>
        <Link
          href={item.href}
          // A gaveta do celular fecha por mudança de CAMINHO, e as quatro
          // tabelas de apoio compartilham o mesmo: sem fechar aqui, trocar de
          // aba deixava o menu por cima.
          onClick={aoNavegar}
          aria-current={ativo ? "page" : undefined}
          className={`menu-item ${ativo ? "menu-item-ativo" : ""}`}
        >
          <span className="menu-ico">
            <Icone nome={item.icone} />
          </span>
          <span className="truncate">{item.nome}</span>
        </Link>
        {fixavel && (
          <button
            type="button"
            aria-pressed={fixado}
            aria-label={fixado ? `Tirar ${item.nome} dos atalhos` : `Fixar ${item.nome} nos atalhos`}
            title={fixado ? "tirar dos atalhos" : "fixar nos atalhos"}
            onClick={() => fixar(item.href)}
            className={`menu-fixar ${fixado ? "menu-fixar-marcado" : ""}`}
          >
            <Icone nome="alfinete" tamanho={13} />
          </button>
        )}
      </div>
    );
  };

  return (
    // ⚠️ A folga do topo vive no `nav`, e não no `aside`: com a marca e a loja
    // na barra superior, a busca é o primeiro elemento da lateral e encostaria
    // na borda de baixo da barra — dois blocos colados, sem respiro entre eles.
    <nav className="px-3 pb-5 pt-4">
      {/* 🔑 **A busca abre o menu inteiro em três teclas.** Ela não desfaz a
          regra dos grupos recolhidos: torna-a irrelevante, porque quem sabe
          para onde vai deixa de navegar pela árvore. */}
      <button type="button" id="menu-busca" className="menu-busca" onClick={abrirBuscaDeTelas}>
        <Icone nome="lupa" tamanho={16} />
        <span>Buscar tela…</span>
        {/* ⚠️ Só no ponteiro: no telefone não há `Ctrl`, e anunciar um atalho
            que não existe ali é ruído. */}
        <span className="menu-tecla hidden lg:inline">CTRL K</span>
      </button>

      {/* Fora de grupo: a primeira tela não se abre com um clique a mais. */}
      {linha(INICIO, false)}

      {/* 🔑 **Os atalhos ocupam o espaço que já estava vazio.** A lateral
          mostrava seis títulos numa coluna de 900px — 85% dela sem uso — e o
          menu não sabia que a cozinha não abre as mesmas telas que o escritório. */}
      {atalhos.length > 0 && (
        <>
          <div className="menu-divisor" />
          <p className="menu-secao">Seus atalhos</p>
          {atalhos.map((href) => {
            const item = porHref.get(href);
            return item ? linha(item, true) : null;
          })}
        </>
      )}

      <div className="menu-divisor" />

      {entradas.map((e) =>
        e.tipo === "item" ? (
          // Grupo que sobrou com um item só — ver `montarMenu`.
          linha(e.item, true)
        ) : (
          <div key={e.grupo} className="mb-0.5 shrink-0">
            {/* 🔑 **O padrão é RECOLHIDO — todos.** O grupo da tela aberta já veio
                expandido sozinho, e o efeito era um menu que ia abrindo grupos
                conforme se navegava: ao fim de dez minutos estavam todos abertos, e
                a lista de vinte itens não cabia mais na altura da tela. A pista de
                "você está aqui" não se perde — o título do grupo fica verde, e ele
                continua abrindo com um clique. */}
            {(() => {
              const expandido = abertos[e.grupo] ?? false;
              const temAtivo = e.itens.some((i) => i.href === caminho);
              return (
                <>
                  <button
                    type="button"
                    aria-expanded={expandido}
                    onClick={() => alternarGrupo(e.grupo, expandido)}
                    className={`menu-grupo ${temAtivo ? "menu-grupo-ativo" : ""}`}
                  >
                    <span className="menu-ico">
                      <Icone nome={e.icone} />
                    </span>
                    <span>{e.grupo}</span>
                    <span className="menu-conta">{e.itens.length}</span>
                    <svg
                      viewBox="0 0 10 6"
                      aria-hidden="true"
                      className={`ml-1.5 h-[6px] w-[10px] shrink-0 opacity-70 transition-transform duration-200 ${
                        expandido ? "" : "-rotate-90"
                      }`}
                    >
                      <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6"
                            strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                  <div className={`menu-filhos pb-1.5 ${expandido ? "" : "hidden"}`}>
                    {e.itens.map((i) => linha(i, true))}
                  </div>
                </>
              );
            })()}
          </div>
        ),
      )}
    </nav>
  );
}
