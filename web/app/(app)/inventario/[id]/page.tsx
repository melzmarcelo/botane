"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { nomeTipo, reais, UnidadeMedida } from "@/lib/cadastros";
import BotaoExportar from "@/components/exportar";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import IncluirProduto from "./incluir-produto";
import Voltar from "@/components/voltar";

import { concorda, plural, qtd } from "@/lib/numeros";
/**
 * A contagem — tela própria, feita para o celular na mão de quem conta.
 *
 * Contar estoque é andar pela despensa com o telefone: uma tabela larga com
 * dez colunas não serve. Aqui cada produto é um cartão, com o alvo do dedo
 * grande, e o que importa em cima: o nome, quanto o sistema acha que tem, e o
 * campo para digitar o que se viu.
 *
 * Três decisões que vêm de como a coisa acontece de verdade:
 *
 * * **Grava item a item, sozinho.** Quem conta anda, é interrompido, o telefone
 *   trava. Contagem que só existe na tela até um "salvar tudo" no fim é
 *   contagem que se perde.
 * * **A unidade é escolhível**, e vem a do estoque por padrão. Quem conta conta
 *   caixa, não unidade; converter de cabeça é onde o erro entra — e o erro do
 *   inventário vira ajuste no razão.
 * * **O que falta contar fica à mão**, porque a pergunta do fim da contagem é
 *   sempre "o que ainda não contei?".
 */

type Unidade = { um: string; fator: number };

/** Um pedaço da contagem, como digitado: as 3 UN fechadas, ou os 948 ML da aberta. */
type Parcela = { qtd: string; um: string };

type Item = {
  id_produto: number;
  /** ⚠️ A linha é o par produto × local: o mesmo café pode estar em dois. */
  id_local: number | null;
  local: string | null;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  categoria: string | null;
  /** Vem `null` na contagem cega enquanto ela está aberta. */
  qtd_sistema: number | null;
  qtd_contada: number | null;
  qtd_informada: number | null;
  um_informada: string | null;
  /** Contagem em mais de uma unidade (135): "3 UN + 948 ML". Nulo com uma só. */
  parcelas: { qtd: number; um: string }[] | null;
  custo_medio: number;
  diferenca: number | null;
  contado_por: string | null;
  observacao: string | null;
  setor: string | null;
  tipo: string | null;
  unidades: Unidade[];
  /** Achado na prateleira e incluído depois da abertura (096). */
  incluido?: boolean;
};

type Inventario = {
  id: number;
  nome: string | null;
  /** Nulo quando a contagem cobre mais de um local. */
  id_local: number | null;
  local: string;
  data: string;
  status: string;
  cega: boolean;
  itens: Item[];
  contados: number;
  total_itens: number;
  diferenca_valor: number | null;
  filtros?: {
    locais: string[];
    setores: string[];
    categorias: string[];
    tipos: string[];
  } | null;
  /** Quem foi escalado. Vazio = qualquer um com permissão de contar. */
  contadores?: { id_usuario: number; nome: string }[];
  /** Onde se pode incluir um produto achado fora da lista (096). */
  locais_da_contagem?: { id: number; nome: string }[];
};

/**
 * A identidade de uma linha da contagem.
 *
 * ⚠️ **Não é o produto.** Desde que a contagem virou um recorte, o mesmo café
 * pode aparecer na câmara e no estoque seco — duas linhas, duas quantidades,
 * dois ajustes. Com a chave sendo só `id_produto`, o rascunho de uma
 * sobrescreveria o da outra e o React reclamaria de chave repetida.
 */
const chaveDe = (i: { id_produto: number; id_local: number | null }) =>
  `${i.id_produto}:${i.id_local ?? 0}`;


export default function PaginaContagem() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const aviso = useAviso();
  const { pode } = useSessao();

  const [inv, setInv] = useState<Inventario | null>(null);
  const [erro, setErro] = useState("");
  const [busca, setBusca] = useState("");
  const [soPendentes, setSoPendentes] = useState(false);
  // ⚠️ A chave é `produto:local`, não o id do produto — ver `chaveDe`.
  const [rascunho, setRascunho] = useState<Record<string, Parcela[]>>({});
  const [gravando, setGravando] = useState<string | null>(null);
  const [renomeando, setRenomeando] = useState(false);
  const [nomeNovo, setNomeNovo] = useState("");
  const [fechando, setFechando] = useState(false);
  const [incluindo, setIncluindo] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [ums, setUms] = useState<UnidadeMedida[]>([]);

  const carregar = useCallback(async () => {
    try {
      setInv(await api.get<Inventario>(`/inventarios/${id}`));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [id]);

  useEffect(() => {
    void carregar();
    api.get<UnidadeMedida[]>("/unidades-medida").then(setUms).catch(() => {});
  }, [carregar]);

  const aberto = inv?.status === "ABERTO";

  // O que a pessoa digitou, item a item — o servidor devolve o convertido, e
  // sobrescrever o campo enquanto ela digita seria arrancar o texto da mão.
  // 🔑 **Em PARCELAS** (135, 27/10/2026, o CAMPARI do dono): "3 UN + 948 ML" — as
  // garrafas fechadas e a aberta. Uma parcela é a contagem de sempre.
  const parcelasDe = (i: Item): Parcela[] => {
    const r = rascunho[chaveDe(i)];
    if (r) return r;
    if (i.parcelas?.length) {
      return i.parcelas.map((x) => ({ qtd: String(Number(x.qtd)), um: x.um }));
    }
    return [
      {
        qtd:
          i.qtd_informada !== null && i.qtd_informada !== undefined
            ? String(Number(i.qtd_informada))
            : i.qtd_contada !== null
              ? String(Number(i.qtd_contada))
              : "",
        um: i.um_informada ?? i.um_estoque ?? "",
      },
    ];
  };

  /**
   * Em que unidades este produto pode ser contado.
   *
   * Três origens, e todas convertem de verdade:
   *
   * 1. a unidade de ESTOQUE, que é o padrão;
   * 2. as embalagens do cadastro do produto (a caixa desta água tem 12);
   * 3. as unidades da MESMA GRANDEZA — quem estoca em KG pode contar em G, e
   *    isso não depende de cadastro nenhum.
   *
   * O que fica de fora é embalagem que ninguém cadastrou: oferecer CX para um
   * produto sem caixa definida seria oferecer um erro.
   */
  const opcoesDe = (i: Item) => {
    const estoque = (i.um_estoque ?? "").toUpperCase();
    const grandeza = ums.find((u) => u.sigla === estoque)?.grandeza;
    const base = ums.find((u) => u.sigla === estoque)?.fator_base;

    const vistas = new Set<string>();
    const lista: Unidade[] = [];
    const juntar = (sigla: string, fator: number) => {
      const s = (sigla ?? "").toUpperCase();
      if (!s || vistas.has(s) || !Number.isFinite(fator) || fator <= 0) return;
      vistas.add(s);
      lista.push({ um: s, fator });
    };

    juntar(estoque, 1);
    for (const u of i.unidades ?? []) juntar(u.um, Number(u.fator));
    if (grandeza && base) {
      for (const u of ums) {
        if (u.grandeza !== grandeza) continue;
        // Dentro de UNIDADE, caixa/fardo/pacote têm o mesmo fator base e NÃO
        // se convertem entre si: quantas cabem depende do produto. Dúzia entra
        // porque doze é doze em qualquer um.
        if (grandeza === "UNIDADE" && Number(u.fator_base) === Number(base)) continue;
        juntar(u.sigla, Number(u.fator_base) / Number(base));
      }
    }
    return lista;
  };

  async function salvarNome() {
    try {
      await api.put(`/inventarios/${id}/nome`, { nome: nomeNovo.trim() });
      setRenomeando(false);
      await carregar();
      aviso.sucesso("Nome atualizado.");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível renomear");
    }
  }

  async function gravarItem(item: Item, parcelas: Parcela[]) {
    // Só as parcelas preenchidas vão: a linha nova em branco é a que a pessoa
    // ainda vai digitar.
    const cheias = parcelas
      .map((x) => ({ qtd: x.qtd.trim().replace(",", "."), um: x.um }))
      .filter((x) => x.qtd !== "");
    setGravando(chaveDe(item));
    try {
      const r = await api.put<Inventario>(`/inventarios/${id}/contagem`, {
        itens: [
          {
            id_produto: item.id_produto,
            // ⚠️ Vai sempre, mesmo na contagem de um local só: sem ele o
            // servidor recusa quando o produto está em duas prateleiras.
            id_local: item.id_local,
            // Uma parcela vai como sempre foi; várias, como lista — o servidor
            // converte cada uma e soma.
            ...(cheias.length > 1
              ? { parcelas: cheias.map((x) => ({ qtd: Number(x.qtd), um: x.um || null })) }
              : {
                  qtd_contada: cheias.length ? Number(cheias[0].qtd) : null,
                  um: cheias[0]?.um || parcelas[0]?.um || null,
                }),
            observacao: item.observacao,
          },
        ],
      });
      setInv(r);
      // O rascunho sai do caminho: daqui em diante vale o que o servidor diz.
      // ⚠️ MENOS quando o rascunho JÁ NÃO é o que foi gravado, ou tem parcela em
      // branco. Clicar em "+ somar" tira o foco do campo de cima (que grava) e abre
      // a linha nova; a resposta chega DEPOIS, e apagar o rascunho levaria junto a
      // linha que a pessoa acabou de abrir — o campo some debaixo do dedo.
      setRascunho((a) => {
        const atual = a[chaveDe(item)];
        if (
          atual &&
          (JSON.stringify(atual) !== JSON.stringify(parcelas) ||
            (atual.length > 1 && atual.some((x) => x.qtd.trim() === "")))
        ) {
          return a;
        }
        const { [chaveDe(item)]: _fora, ...resto } = a;
        return resto;
      });
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar a contagem");
    } finally {
      setGravando(null);
    }
  }

  async function fechar() {
    setFechando(true);
    try {
      const r = await api.post<{ ajustes: number; valor: number; message: string }>(
        `/inventarios/${id}/fechar`,
      );
      aviso.sucesso(
        `${r.message} — ${plural(r.ajustes, "ajuste", "ajustes")}, ${reais(Number(r.valor))} de diferença.`,
        { texto: "voltar para os inventários", ao: () => router.push("/inventario") },
      );
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível fechar");
    } finally {
      setFechando(false);
    }
  }

  const itens = useMemo(() => {
    if (!inv) return [];
    const alvo = busca.trim().toLowerCase();
    return inv.itens.filter((i) => {
      if (soPendentes && i.qtd_contada !== null) return false;
      if (!alvo) return true;
      return (
        i.produto.toLowerCase().includes(alvo) ||
        (i.codigo ?? "").toLowerCase().includes(alvo)
      );
    });
  }, [inv, busca, soPendentes]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!inv) return <Carregando />;

  const faltam = inv.total_itens - inv.contados;

  return (
    <div className="flex flex-col gap-5">
      <header>
        <Voltar href="/inventario">
          inventários
        </Voltar>
        {/* ⚠️ "Contagem" saiu do <h1> e virou o rótulo acima dele. O título
            agora é o NOME que a pessoa deu — e "Contagem · Contagem do Natal"
            seria a palavra duas vezes. Sem o rótulo, uma contagem chamada
            "Estoque seco" pareceria a tela do local. */}
        <p className="rotulo mt-3">Contagem</p>
        {/* ⚠️ O nome é editável DEPOIS de aberta, e também depois de fechada.
            Quem procura "a contagem do Natal" seis meses depois não deveria
            depender de ter acertado o nome na abertura — é rótulo, não mexe em
            item nem em razão. */}
        {renomeando ? (
          <form
            className="mt-1 flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void salvarNome();
            }}
          >
            <label className="min-w-0 flex-1">
              <span className="rotulo-campo">Nome da contagem</span>
              <input
                className="campo mt-1.5"
                autoFocus
                required
                minLength={2}
                maxLength={80}
                value={nomeNovo}
                onChange={(e) => setNomeNovo(e.target.value)}
              />
            </label>
            <button className="btn btn-primario" type="submit">
              Salvar
            </button>
            <button
              className="btn btn-secundario"
              type="button"
              onClick={() => setRenomeando(false)}
            >
              Cancelar
            </button>
          </form>
        ) : (
          <h1 className="mt-1 flex flex-wrap items-baseline gap-x-3 text-[24px] font-bold tracking-tight sm:text-[30px]">
            {inv.nome || inv.local}
            {/* Renomear é rótulo, mas é configuração da contagem: fica com
                quem a monta. */}
            {pode("estoque.inventario_criar") && (
              <button
                className="link-acao"
                onClick={() => {
                  setNomeNovo(inv.nome || inv.local);
                  setRenomeando(true);
                }}
              >
                renomear
              </button>
            )}
          </h1>
        )}
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <Etiqueta>
            {new Date(inv.data + "T12:00").toLocaleDateString("pt-BR")}
          </Etiqueta>
          {/* Quando a contagem cobre mais de um local, o cabeçalho diz de onde
              ela é — a lista de itens sozinha não responde isso de relance. */}
          {inv.id_local === null && <Etiqueta>vários locais</Etiqueta>}
          {/* A escala fica à vista: quem abre a contagem e não consegue digitar
              precisa saber por quê, sem ter de perguntar a alguém. */}
          {!!inv.contadores?.length && (
            <Etiqueta>
              contam: {inv.contadores.map((c) => c.nome.split(" ")[0]).join(", ")}
            </Etiqueta>
          )}
          {aberto ? (
            <Etiqueta cor="alerta">aberto</Etiqueta>
          ) : (
            <Etiqueta cor="erva">fechado</Etiqueta>
          )}
          {inv.cega && <Etiqueta>contagem cega</Etiqueta>}
          {(inv.filtros?.setores ?? []).map((x) => (
            <Etiqueta key={`s-${x}`}>setor {x}</Etiqueta>
          ))}
          {(inv.filtros?.categorias ?? []).map((x) => (
            <Etiqueta key={`c-${x}`}>{x}</Etiqueta>
          ))}
          {(inv.filtros?.tipos ?? []).map((x) => (
            <Etiqueta key={`t-${x}`}>{nomeTipo(x)}</Etiqueta>
          ))}
          {/* ⚠️ A folha de contagem existe desde a etapa 4 e NENHUMA tela
              oferecia o botão — só se chegava a ela pela URL. Contar no papel e
              digitar depois é o caminho previsto para quem não leva o celular
              à câmara fria, e ele estava fechado. Em contagem CEGA aberta a
              folha sai sem as colunas do sistema: o papel é o jeito mais fácil
              de furar o sigilo, e quem esconde é o servidor. */}
          <BotaoExportar
            className="link-acao"
            rotulo="folha de contagem"
            formatoPadrao="pdf"
            relatorio={`inventario/${inv.id}`}
            avulso={{
              rotulo: "Folha de contagem",
              descricao: inv.cega && aberto
                ? "Contagem cega: o saldo do sistema não sai na folha."
                : "Para imprimir, contar no papel e digitar depois.",
            }}
          />
        </div>
      </header>

      {/* O progresso é a pergunta do fim da contagem: quanto falta. Grudado no
          topo porque no celular ele sai da tela na primeira rolagem. */}
      <div className="sticky top-0 z-20 -mx-4 border-b border-linha bg-papel/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[15px]">
            <b className="mono">{inv.contados}</b> de{" "}
            <b className="mono">{inv.total_itens}</b> contado(s)
            {faltam > 0 && (
              <span className="text-suave"> · faltam {faltam}</span>
            )}
          </p>
          {inv.diferenca_valor !== null && inv.diferenca_valor !== undefined && (
            <p className="text-[13.5px] text-suave">
              diferença até agora{" "}
              <b
                className={`mono ${
                  Number(inv.diferenca_valor) < 0 ? "text-erro" : "text-erva"
                }`}
              >
                {reais(Number(inv.diferenca_valor))}
              </b>
            </p>
          )}
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-superficie2">
          <div
            className="h-full bg-erva transition-all"
            style={{
              width: `${inv.total_itens ? (inv.contados / inv.total_itens) * 100 : 0}%`,
            }}
          />
        </div>
      </div>

      {inv.cega && aberto && (
        <Aviso tipo="info">
          Contagem cega: o saldo do sistema não aparece — nem aqui, nem na folha impressa. Conte
          o que está na prateleira; a diferença surge quando a contagem fechar.
        </Aviso>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="min-w-0 flex-1">
          <span className="rotulo-campo">Achar produto</span>
          <input
            className="campo campo-toque mt-1.5"
            placeholder="produto ou código"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </label>
        <label className="flex items-center gap-2 pb-2.5">
          <input
            type="checkbox"
            className="h-5 w-5 accent-erva"
            checked={soPendentes}
            onChange={(e) => setSoPendentes(e.target.checked)}
          />
          <span className="text-[15px]">só o que falta</span>
        </label>
        {/* 🔑 **Produto achado fora da lista** (pedido do dono, 26/09/2026). Só com a
            contagem aberta — fechada, a diferença já virou ajuste. */}
        {aberto && (
          <button type="button" className="btn btn-secundario" onClick={() => setIncluindo(true)}>
            Incluir produto achado
          </button>
        )}
      </div>

      {incluindo && (
        <IncluirProduto<Inventario>
          idInventario={id}
          locais={inv.locais_da_contagem ?? []}
          aoFechar={() => setIncluindo(false)}
          aoIncluir={(nova, nome) => {
            setInv(nova);
            setIncluindo(false);
            // Mostra o produto recém-incluído: é o próximo a ser contado.
            setBusca(nome.split(" · ").pop() ?? "");
            setSoPendentes(false);
            aviso.sucesso(`${nome} incluído na contagem. Digite a quantidade.`);
          }}
        />
      )}

      {!itens.length ? (
        <Vazio>
          {soPendentes
            ? "Tudo contado neste local."
            : busca
              ? `Nenhum produto com “${busca}”.`
              : "Nenhum item nesta contagem."}
        </Vazio>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {itens.map((i) => (
            <LinhaContagem
              key={chaveDe(i)}
              item={i}
              aberto={!!aberto}
              // O local aparece na linha só quando a contagem tem mais de um:
              // repetir a mesma palavra em todas seria ruído.
              mostrarLocal={inv.id_local === null}
              podeCadastrar={pode("cadastros.produtos")}
              gravando={gravando === chaveDe(i)}
              parcelas={parcelasDe(i)}
              opcoes={opcoesDe(i)}
              aoDigitar={(ps) => setRascunho((a) => ({ ...a, [chaveDe(i)]: ps }))}
              aoGravar={(ps) => void gravarItem(i, ps)}
            />
          ))}
        </ul>
      )}

      {aberto && pode("estoque.ajuste") && (
        <Cartao titulo="Fechar a contagem">
          <p className="text-[14.5px] text-suave">
            Fechar acerta o razão: cada diferença vira um movimento de ajuste, com o custo médio
            do momento. Produto não contado fica como está — não vira zero.
            {faltam > 0 && (
              <>
                {" "}
                <b className="text-tinta">Ainda faltam {plural(faltam, "produto", "produtos")}.</b>
              </>
            )}
          </p>
          <button
            className="btn btn-primario mt-4"
            onClick={() => setConfirmando(true)}
            aria-busy={fechando} disabled={fechando || !inv.contados}
          >
            {fechando ? "Fechando…" : "Fechar e acertar o estoque"}
          </button>
        </Cartao>
      )}

      {confirmando && (
        <Confirmacao
          titulo="Fechar a contagem"
          rotuloConfirmar="Fechar e acertar"
          ocupado={fechando}
          aoCancelar={() => setConfirmando(false)}
          aoConfirmar={() => {
            setConfirmando(false);
            void fechar();
          }}
        >
          <p>
            Fechar a contagem de <b>{inv.local}</b>, com{" "}
            <b className="mono">{inv.contados}</b> de{" "}
            <b className="mono">{inv.total_itens}</b> {concorda(inv.total_itens, "item contado", "itens contados")}?
          </p>
          {faltam > 0 && (
            <p className="mt-2 text-[13.5px] text-alerta">
              {plural(faltam, "produto", "produtos")} sem contar ficam como estão — não viram zero.
            </p>
          )}
          <p className="mt-3 text-[13.5px] text-suave">
            Cada diferença vira um movimento de ajuste no razão, com o custo médio do momento.
            Depois disso a contagem não se reabre.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}

function LinhaContagem({
  item,
  aberto,
  mostrarLocal,
  podeCadastrar,
  gravando,
  parcelas,
  opcoes,
  aoDigitar,
  aoGravar,
}: {
  item: Item;
  aberto: boolean;
  mostrarLocal: boolean;
  podeCadastrar: boolean;
  gravando: boolean;
  parcelas: Parcela[];
  opcoes: Unidade[];
  aoDigitar: (parcelas: Parcela[]) => void;
  aoGravar: (parcelas: Parcela[]) => void;
}) {
  const contado = item.qtd_contada !== null && item.qtd_contada !== undefined;
  const dif =
    contado && item.qtd_sistema !== null && item.qtd_sistema !== undefined
      ? Number(item.qtd_contada) - Number(item.qtd_sistema)
      : null;
  const fatorDe = (um: string) => opcoes.find((o) => o.um === um)?.fator ?? 1;
  const numero = (t: string) => Number((t || "0").replace(",", "."));
  const total = parcelas.reduce((soma, x) => soma + numero(x.qtd) * fatorDe(x.um), 0);
  // Quanto isso vira no estoque. Só aparece quando há conta a fazer — outra
  // unidade, ou mais de uma parcela: senão repetiria o número do campo.
  const precisaConta =
    parcelas.length > 1 || (parcelas[0] && fatorDe(parcelas[0].um) !== 1);
  const emEstoque = precisaConta && total ? total : null;
  const trocar = (n: number, mudanca: Partial<Parcela>) =>
    parcelas.map((x, k) => (k === n ? { ...x, ...mudanca } : x));
  // 🔑 **Somar outra unidade** (135, 27/10/2026): a garrafa aberta em ML ao lado das
  // fechadas em UN. A parcela nova vem na primeira unidade que ainda não foi usada.
  const livre = opcoes.find((o) => !parcelas.some((x) => x.um === o.um))?.um;

  return (
    <li className="rounded border border-linha bg-superficie p-3.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[15.5px] font-semibold leading-tight">{item.produto}</p>
          <p className="mt-0.5 text-[12.5px] text-suave">
            <span className="mono">{item.codigo}</span>
            {item.categoria ? ` · ${item.categoria}` : ""}
          </p>
          {/* ⚠️ O local vira o destaque da linha quando a contagem cobre mais
              de um: sem ele, duas linhas do mesmo produto ficam idênticas na
              tela, e quem conta não sabe qual prateleira está na frente. */}
          {item.incluido && (
            <p className="mt-1 text-[12.5px] font-medium text-[var(--color-alerta)]">
              incluído na contagem — não estava na lista
            </p>
          )}
          {mostrarLocal && item.local && (
            <p className="mt-1 text-[13px] font-semibold text-erva">{item.local}</p>
          )}
        </div>
        {contado && dif !== null && (
          <Etiqueta cor={dif === 0 ? "erva" : "alerta"}>
            {dif === 0 ? "confere" : `${dif > 0 ? "+" : ""}${qtd(dif)}`}
          </Etiqueta>
        )}
        {contado && dif === null && <Etiqueta cor="erva">contado</Etiqueta>}
      </div>

      <div className="mt-3 flex flex-wrap items-end gap-2">
        {/* Na contagem cega o servidor NÃO manda o esperado — não é a tela que
            esconde. Sem a coluna, quem conta olha a prateleira e não o número. */}
        {item.qtd_sistema !== null && item.qtd_sistema !== undefined && (
          <div className="w-[104px] shrink-0">
            <span className="rotulo">Sistema</span>
            <p className="mono mt-1.5 py-2 text-[15px] text-suave">
              {qtd(item.qtd_sistema)} {item.um_estoque ?? ""}
            </p>
          </div>
        )}
        <div className="flex flex-col gap-2" data-parcelas={parcelas.length}>
          {parcelas.map((x, n) => (
            <div key={n} className="flex items-end gap-2">
              <label className="w-[118px] shrink-0">
                <span className={`rotulo-campo ${n ? "sr-only" : ""}`}>
                  {n ? `Mais (parcela ${n + 1})` : "Contei"}
                </span>
                <input
                  // `campo-toque`: 16px e alvo grande. Abaixo de 16px o Safari do
                  // iPhone dá zoom ao focar e a tela salta a cada produto contado —
                  // e a utilitária do Tailwind perde para `.campo`, por isso a classe.
                  className={`campo campo-toque mono text-right ${n ? "" : "mt-1.5"}`}
                  inputMode="decimal"
                  data-parcela={n}
                  disabled={!aberto}
                  value={x.qtd}
                  onChange={(e) => aoDigitar(trocar(n, { qtd: e.target.value }))}
                  onBlur={(e) => aoGravar(trocar(n, { qtd: e.target.value }))}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      (e.target as HTMLInputElement).blur();
                    }
                  }}
                />
              </label>
              <label className="w-[92px] shrink-0">
                <span className={`rotulo-campo ${n ? "sr-only" : ""}`}>Unidade</span>
                <select
                  className={`campo campo-toque ${n ? "" : "mt-1.5"}`}
                  data-parcela-um={n}
                  disabled={!aberto}
                  value={x.um}
                  onChange={(e) => {
                    const novas = trocar(n, { um: e.target.value });
                    aoDigitar(novas);
                    if (x.qtd.trim()) aoGravar(novas);
                  }}
                >
                  {opcoes.map((o) => (
                    <option key={o.um} value={o.um}>
                      {o.um}
                    </option>
                  ))}
                </select>
              </label>
              {n > 0 && aberto && (
                <button
                  type="button"
                  className="link-acao pb-2.5 text-[13px]"
                  aria-label={`tirar a parcela ${n + 1}`}
                  onClick={() => {
                    const novas = parcelas.filter((_, k) => k !== n);
                    aoDigitar(novas);
                    aoGravar(novas);
                  }}
                >
                  tirar
                </button>
              )}
            </div>
          ))}
          {aberto && livre && parcelas.length < 8 && (
            <button
              type="button"
              className="link-acao self-start text-[13px]"
              data-somar-parcela
              onClick={() => aoDigitar([...parcelas, { qtd: "", um: livre }])}
            >
              + somar outra unidade
            </button>
          )}
        </div>
        <div className="min-w-0 flex-1 pb-2.5 text-[13px] text-suave">
          <p>
            {gravando
              ? "gravando…"
              : emEstoque
                ? `= ${qtd(emEstoque)} ${item.um_estoque ?? ""}`
                : item.contado_por
                  ? `contado por ${item.contado_por}`
                  : ""}
          </p>
          {/* A lista só traz o que converte de verdade. Quando a embalagem da
              mão não está lá, o caminho é o cadastro do produto — dizer isso
              aqui evita a pessoa achar que o seletor está travado. */}
          {aberto && podeCadastrar && (
            <Link
              href={`/produtos/${item.id_produto}`}
              className="underline underline-offset-2 hover:text-erva"
            >
              contar em outra embalagem?
            </Link>
          )}
        </div>
      </div>
    </li>
  );
}
