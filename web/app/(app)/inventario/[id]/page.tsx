"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { reais, UnidadeMedida } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";

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

type Item = {
  id_produto: number;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  categoria: string | null;
  /** Vem `null` na contagem cega enquanto ela está aberta. */
  qtd_sistema: number | null;
  qtd_contada: number | null;
  qtd_informada: number | null;
  um_informada: string | null;
  custo_medio: number;
  diferenca: number | null;
  contado_por: string | null;
  observacao: string | null;
  unidades: Unidade[];
};

type Inventario = {
  id: number;
  id_local: number;
  local: string;
  data: string;
  status: string;
  cega: boolean;
  itens: Item[];
  contados: number;
  total_itens: number;
  diferenca_valor: number | null;
};

const qtd = (n: number | string) =>
  Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 3 });

export default function PaginaContagem() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const aviso = useAviso();
  const { pode } = useSessao();

  const [inv, setInv] = useState<Inventario | null>(null);
  const [erro, setErro] = useState("");
  const [busca, setBusca] = useState("");
  const [soPendentes, setSoPendentes] = useState(false);
  const [rascunho, setRascunho] = useState<Record<number, { qtd: string; um: string }>>({});
  const [gravando, setGravando] = useState<number | null>(null);
  const [fechando, setFechando] = useState(false);
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
  const valorDe = (i: Item) =>
    rascunho[i.id_produto]?.qtd ??
    (i.qtd_informada !== null && i.qtd_informada !== undefined
      ? String(Number(i.qtd_informada))
      : i.qtd_contada !== null
        ? String(Number(i.qtd_contada))
        : "");

  const unidadeDe = (i: Item) =>
    rascunho[i.id_produto]?.um ?? i.um_informada ?? i.um_estoque ?? "";

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

  async function gravarItem(item: Item, texto: string, um: string) {
    const limpo = texto.trim().replace(",", ".");
    setGravando(item.id_produto);
    try {
      const r = await api.put<Inventario>(`/inventarios/${id}/contagem`, {
        itens: [
          {
            id_produto: item.id_produto,
            qtd_contada: limpo === "" ? null : Number(limpo),
            um: um || null,
            observacao: item.observacao,
          },
        ],
      });
      setInv(r);
      // O rascunho sai do caminho: daqui em diante vale o que o servidor diz.
      setRascunho((a) => {
        const { [item.id_produto]: _fora, ...resto } = a;
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
        `${r.message} — ${r.ajustes} ajuste(s), ${reais(Number(r.valor))} de diferença.`,
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
        <Link href="/inventario" className="link-voltar">
          inventários
        </Link>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
          Contagem · {inv.local}
        </h1>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <Etiqueta>
            {new Date(inv.data + "T12:00").toLocaleDateString("pt-BR")}
          </Etiqueta>
          {aberto ? (
            <Etiqueta cor="alerta">aberto</Etiqueta>
          ) : (
            <Etiqueta cor="erva">fechado</Etiqueta>
          )}
          {inv.cega && <Etiqueta>contagem cega</Etiqueta>}
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
          <span className="rotulo">Achar produto</span>
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
      </div>

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
              key={i.id_produto}
              item={i}
              aberto={!!aberto}
              podeCadastrar={pode("cadastros.produtos")}
              gravando={gravando === i.id_produto}
              valor={valorDe(i)}
              unidade={unidadeDe(i)}
              opcoes={opcoesDe(i)}
              aoDigitar={(qtdTexto, um) =>
                setRascunho((a) => ({ ...a, [i.id_produto]: { qtd: qtdTexto, um } }))
              }
              aoGravar={(qtdTexto, um) => void gravarItem(i, qtdTexto, um)}
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
                <b className="text-tinta">Ainda faltam {faltam} produto(s).</b>
              </>
            )}
          </p>
          <button
            className="btn btn-primario mt-4"
            onClick={() => setConfirmando(true)}
            disabled={fechando || !inv.contados}
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
            <b className="mono">{inv.total_itens}</b> item(ns) contado(s)?
          </p>
          {faltam > 0 && (
            <p className="mt-2 text-[13.5px] text-alerta">
              {faltam} produto(s) sem contar ficam como estão — não viram zero.
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
  podeCadastrar,
  gravando,
  valor,
  unidade,
  opcoes,
  aoDigitar,
  aoGravar,
}: {
  item: Item;
  aberto: boolean;
  podeCadastrar: boolean;
  gravando: boolean;
  valor: string;
  unidade: string;
  opcoes: Unidade[];
  aoDigitar: (qtd: string, um: string) => void;
  aoGravar: (qtd: string, um: string) => void;
}) {
  const campo = useRef<HTMLInputElement>(null);
  const contado = item.qtd_contada !== null && item.qtd_contada !== undefined;
  const dif =
    contado && item.qtd_sistema !== null && item.qtd_sistema !== undefined
      ? Number(item.qtd_contada) - Number(item.qtd_sistema)
      : null;
  const fator = opcoes.find((o) => o.um === unidade)?.fator ?? 1;
  const digitado = Number((valor || "0").replace(",", "."));
  // Quanto isso vira no estoque. Só aparece quando a unidade contada não é a de
  // estoque: em caso contrário seria repetir o número que já está no campo.
  const emEstoque = fator !== 1 && digitado ? digitado * fator : null;

  return (
    <li className="rounded border border-linha bg-superficie p-3.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[15.5px] font-semibold leading-tight">{item.produto}</p>
          <p className="mt-0.5 text-[12.5px] text-suave">
            <span className="mono">{item.codigo}</span>
            {item.categoria ? ` · ${item.categoria}` : ""}
          </p>
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
        <label className="w-[118px] shrink-0">
          <span className="rotulo">Contei</span>
          <input
            ref={campo}
            // `campo-toque`: 16px e alvo grande. Abaixo de 16px o Safari do
            // iPhone dá zoom ao focar e a tela salta a cada produto contado —
            // e a utilitária do Tailwind perde para `.campo`, por isso a classe.
            className="campo campo-toque mono mt-1.5 text-right"
            inputMode="decimal"
            disabled={!aberto}
            value={valor}
            onChange={(e) => aoDigitar(e.target.value, unidade)}
            onBlur={(e) => aoGravar(e.target.value, unidade)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                campo.current?.blur();
              }
            }}
          />
        </label>
        <label className="w-[92px] shrink-0">
          <span className="rotulo">Unidade</span>
          <select
            className="campo campo-toque mt-1.5"
            disabled={!aberto}
            value={unidade}
            onChange={(e) => {
              aoDigitar(valor, e.target.value);
              if (valor.trim()) aoGravar(valor, e.target.value);
            }}
          >
            {opcoes.map((o) => (
              <option key={o.um} value={o.um}>
                {o.um}
              </option>
            ))}
          </select>
        </label>
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
