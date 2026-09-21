"use client";

import Link from "next/link";
import Voltar from "@/components/voltar";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { reais } from "@/lib/cadastros";
import { custo, qtd } from "@/lib/numeros";
import {
  Aviso,
  Carregando,
  Cartao,
  Confirmacao,
  Etiqueta,
  Vazio,
} from "@/components/ui";

/**
 * A folha da produção: o que vai ser preciso para fazer aquilo.
 *
 * A linha da agenda diz "22 massas". Quem vai para a bancada precisa da outra
 * metade: quanto de cada insumo isso consome, quanto disso existe no local de
 * onde vai sair, e o que falta. Sem essa folha, a pessoa descobre que acabou a
 * farinha depois de ligar o forno.
 *
 * 🔑 **Esta folha é da COZINHA, não do escritório** (16/09/2026, pedido do dono:
 * *"quem vai ver esta tela precisa saber as quantidades e o modo de preparo, e
 * não os custos; dar mais foco nisto e disponibilizar a impressão desta tela,
 * para que seja passada para a produção"*). Três consequências, e elas andam
 * juntas:
 *
 * 1. **O modo de preparo entrou.** Sem ele a folha era meia folha: a pessoa
 *    levava a lista de ingredientes e abria a ficha noutra tela para saber o que
 *    fazer com eles.
 * 2. **O custo saiu da tabela.** Ele era uma coluna ao lado das quantidades,
 *    disputando a mesma leitura — e quem está na bancada não decide nada com
 *    ele. Continua na tela, numa linha discreta ao pé, para quem tem a permissão.
 * 3. **E o custo NÃO é impresso.** A folha é passada de mão em mão na cozinha;
 *    mandar o custo do prato junto é distribuir margem por engano.
 *
 * ⚠️ A previsão é sempre de AGORA, nunca a de quando se agendou: o estoque
 * mudou desde então, e é o de agora que diz se dá para produzir.
 */

type ItemPrevisto = {
  /** A linha da RECEITA. É por ela que a correção viaja: a mesma ficha pode
      listar o mesmo insumo duas vezes. */
  id_item: number;
  /** As unidades que este insumo aceita — as mesmas que a conversão conhece. */
  unidades: string[];
  id_produto: number;
  produto: string;
  codigo: string;
  preparo: boolean;
  um_ficha: string | null;
  um_estoque: string | null;
  por_unidade: number;
  na_ficha: number;
  necessario: number | null;
  conversao: string;
  saldo_no_local: number;
  saldo_total: number;
  falta: number;
  custo_unitario: number | null;
  custo: number | null;
  observacao: string | null;
};

type Previsao = {
  id_ficha: number;
  versao: number;
  produto: string;
  codigo: string;
  um_estoque: string | null;
  quantidade: number;
  rendimento_qtd: number;
  rendimento_um: string | null;
  lotes: number;
  itens: ItemPrevisto[];
  itens_faltando: number;
  custo_total: number;
  custo_unitario: number;
  /** O que a bancada precisa saber além das quantidades. */
  modo_preparo: string | null;
  tempo_preparo_min: number | null;
  alergenos: string | null;
  ficha_observacao: string | null;
  /** Qual modo de rendimento está valendo — o planejado, ou o padrão. */
  modo?: string | null;
};

type Linha = {
  id: number;
  id_produto: number;
  produto: string;
  codigo: string;
  um_estoque: string | null;
  data_prevista: string;
  quantidade: number;
  status: string;
  origem: string;
  observacao: string | null;
  local: string | null;
  criado_por_nome: string | null;
  produzido_por_nome: string | null;
  previsao: Previsao;
};


const dia = (d: string) => new Date(d + "T12:00").toLocaleDateString("pt-BR");

export default function PaginaOrdemProducao() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const aviso = useAviso();
  const { pode } = useSessao();
  const veCusto = pode("fichas.custos");

  const [linha, setLinha] = useState<Linha | null>(null);
  const [erro, setErro] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [confirmando, setConfirmando] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  /**
   * 🔑 **O que REALMENTE foi usado** (16/09/2026, pedido do dono: *"na lista de
   * insumos, ter uma nova coluna com o que realmente foi usado — por padrão a
   * mesma quantidade, mas o usuário pode alterar, inclusive a unidade; na receita
   * vão 5 ovos, mas por um acaso usei 6"*).
   *
   * ⚠️ **Só viaja o que foi TOCADO.** Mandar todas as linhas faria o número
   * ARREDONDADO da tela virar o número gravado — 0,626 KG no lugar de 0,62642 —
   * e marcaria toda produção como corrigida. Linha não tocada é a receita, e a
   * receita o servidor já sabe calcular.
   */
  const [usado, setUsado] = useState<Record<number, { quantidade: string; um: string }>>({});

  const carregar = useCallback(async () => {
    try {
      const r = await api.get<Linha>(`/producao-agenda/${id}`);
      setLinha(r);
      setQuantidade((a) => a || String(Number(r.quantidade)));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [id]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  /** Refaz a conta quando a quantidade muda: é o "e se eu fizer o dobro?". */
  const recalcular = useCallback(async () => {
    if (!linha) return;
    const n = Number(quantidade.replace(",", "."));
    if (!n || n <= 0 || n === Number(linha.quantidade)) return;
    try {
      const p = await api.get<Previsao>(
        `/producao-agenda/necessario?id_produto=${linha.id_produto}&quantidade=${n}`,
      );
      setLinha({ ...linha, previsao: p });
      // ⚠️ Mudou a quantidade produzida, mudou o que a receita pede: as correções
      // de antes falavam de outra conta.
      setUsado({});
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível recalcular");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linha, quantidade]);

  async function produzir() {
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>(`/producao-agenda/${id}/produzir`, {
        quantidade: Number(quantidade.replace(",", ".")),
        consumos: Object.entries(usado).map(([idItem, v]) => ({
          id_item: Number(idItem),
          quantidade: Number(v.quantidade.replace(",", ".")) || 0,
          um: v.um || null,
        })),
      });
      aviso.sucesso(r.message, {
        texto: "voltar para a agenda",
        ao: () => router.push("/producao"),
      });
      setConfirmando(false);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível produzir");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!linha) return <Carregando />;

  const p = linha.previsao;
  const planejada = Number(linha.quantidade);
  const agora = Number(quantidade.replace(",", ".")) || planejada;
  const aberta = linha.status === "PLANEJADA";

  return (
    <div className="flex flex-col gap-6">
      <header>
        <div className="nao-imprimir">
          <Voltar href="/producao">
            produção
          </Voltar>
        </div>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
            {linha.produto}
          </h1>
          {/* 🔑 **A folha se imprime e vai para a bancada** (pedido do dono). É o
              mesmo Ctrl+P do painel de CMV — `nao-imprimir` tira o menu, os
              botões e o cartão de custo, e sobra a folha. */}
          <button
            className="btn btn-secundario nao-imprimir mt-1"
            onClick={() => window.print()}
          >
            Imprimir a folha
          </button>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <Etiqueta>{linha.codigo}</Etiqueta>
          <Etiqueta>ficha v{p.versao}</Etiqueta>
          <Etiqueta>{dia(linha.data_prevista)}</Etiqueta>
          {aberta ? (
            <Etiqueta cor="alerta">planejada</Etiqueta>
          ) : (
            <Etiqueta cor="erva">{linha.status.toLowerCase()}</Etiqueta>
          )}
          {linha.origem === "ALERTA" && <Etiqueta>veio do alerta</Etiqueta>}
        </div>
        {/* 🔑 **O QUANTO vem primeiro, e grande.** É a única coisa que a pessoa
            precisa ler de longe, com as mãos ocupadas — e era uma frase corrida
            no meio de um parágrafo cinza. */}
        <p className="mt-3 text-[20px] font-semibold tracking-tight sm:text-[24px]">
          Produzir <span className="mono">{qtd(agora)}</span>{" "}
          <span className="text-suave">{p.um_estoque}</span>
          <span className="ml-3 text-[15px] font-normal text-suave">
            {qtd(p.lotes)} receita(s)
          </span>
        </p>
        <p className="mt-1 max-w-[70ch] prosa text-suave">
          A receita rende <b className="mono">{qtd(p.rendimento_qtd)}</b>{" "}
          {p.rendimento_um ?? p.um_estoque} por vez
          {p.modo && (
            <>
              {" "}no modo <b>{p.modo}</b>
            </>
          )}
          {p.tempo_preparo_min ? (
            <>
              {" "}· leva cerca de <b className="mono">{p.tempo_preparo_min}</b> min
            </>
          ) : null}
          {linha.local && <> · vai para <b>{linha.local}</b></>}.
        </p>
      </header>

      {aberta && (
        <div className="nao-imprimir">
        <Cartao titulo="Quanto produzir">
          <div className="flex flex-wrap items-end gap-3">
            <label>
              <span className="rotulo-campo">Quantidade</span>
              <input
                className="campo campo-toque mono mt-1.5 w-[140px] text-right"
                inputMode="decimal"
                value={quantidade}
                onChange={(e) => setQuantidade(e.target.value)}
                onBlur={() => void recalcular()}
              />
            </label>
            <span className="pb-2.5 text-[13.5px] text-suave">
              {p.um_estoque}
              {agora !== planejada && ` · o plano era ${qtd(planejada)}`}
            </span>
            <button
              className="btn btn-primario ml-auto"
              onClick={() => setConfirmando(true)}
              aria-busy={ocupado} disabled={ocupado}
            >
              Produzir
            </button>
          </div>
        </Cartao>
        </div>
      )}

      <Cartao
        titulo="O que vai ser preciso"
        descricao="Por unidade e no total, com o que existe no local de onde vai sair."
        acao={
          p.itens_faltando > 0 ? (
            <Etiqueta cor="alerta">
              {p.itens_faltando} item(ns) faltando
            </Etiqueta>
          ) : (
            <Etiqueta cor="erva">tem tudo</Etiqueta>
          )
        }
      >
        {!p.itens.length ? (
          <Vazio>A ficha não tem ingredientes.</Vazio>
        ) : (
          <div className="grid-rolante">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Insumo</th>
                  <th className="num">Por unidade</th>
                  <th className="num">Total</th>
                  <th className="num">Tem no local</th>
                  {/* 🔑 **O que REALMENTE foi usado** (pedido do dono). Em branco
                      é a receita; quem usou seis ovos onde ela pede cinco
                      escreve seis, e o sexto deixa de sumir do controle.
                      ⚠️ A coluna VAI para o papel: a caixa em branco é onde a
                      banca anota à mão o que gastou, para digitar depois. */}
                  {aberta && <th className="num">Usei</th>}
                </tr>
              </thead>
              <tbody>
                {p.itens.map((i) => (
                  <tr key={i.id_produto}>
                    <td>
                      <span className="font-medium">{i.produto}</span>
                      <span className="block text-[12.5px] text-suave">
                        <span className="mono">{i.codigo}</span>
                        {i.preparo && " · preparo com ficha própria"}
                        {i.observacao && ` · ${i.observacao}`}
                      </span>
                    </td>
                    {/* A ficha fala em grama; o estoque, em quilo. As duas
                        colunas mostram a mesma coisa nas duas linguagens. */}
                    <td className="num whitespace-nowrap text-suave">
                      {qtd(i.por_unidade)} {i.um_ficha ?? i.um_estoque}
                    </td>
                    {/* O número que a bancada vai pesar: é o maior da linha. */}
                    <td className="num whitespace-nowrap text-[16px] font-semibold">
                      {qtd(i.necessario)} {i.um_estoque}
                      {i.um_ficha && i.um_ficha !== i.um_estoque && (
                        <span className="block text-[12px] font-normal text-suave">
                          {qtd(i.na_ficha)} {i.um_ficha} na receita
                        </span>
                      )}
                    </td>
                    <td
                      className={`num whitespace-nowrap ${
                        i.falta > 0 ? "text-erro" : "text-suave"
                      }`}
                    >
                      {qtd(i.saldo_no_local)} {i.um_estoque}
                      {i.falta > 0 && (
                        <span className="block text-[12px]">
                          faltam {qtd(i.falta)}
                        </span>
                      )}
                    </td>
                    {aberta && (
                      <td className="num">
                        {/* ⚠️ **A largura mora no INVÓLUCRO, não no campo.**
                            `.campo` tem `width: 100%` sem camada, e uma
                            utilitária `w-[92px]` perde para ela na cascata — o
                            campo esticava para os 326px da célula e a coluna
                            "Usei" virava a mais larga da tabela. */}
                        <div className="flex items-center justify-end gap-1.5">
                          <span className="block w-[96px]">
                          <input
                            className="campo mono px-2 py-1.5 text-right text-[13.5px]"
                            inputMode="decimal"
                            aria-label={`usado de ${i.produto}`}
                            placeholder={qtd(i.necessario)}
                            value={usado[i.id_item]?.quantidade ?? ""}
                            onChange={(e) =>
                              setUsado((a) => ({
                                ...a,
                                [i.id_item]: {
                                  quantidade: e.target.value,
                                  um: a[i.id_item]?.um ?? (i.um_estoque ?? ""),
                                },
                              }))
                            }
                          />
                          </span>
                          {/* ⚠️ Só oferece o que a conversão SABE traduzir —
                              oferecer o resto seria convidar a recusa. */}
                          {i.unidades.length > 1 ? (
                            <span className="block w-[74px]">
                            <select
                              className="campo px-1.5 py-1.5 text-[13px]"
                              aria-label={`unidade do usado de ${i.produto}`}
                              value={usado[i.id_item]?.um ?? (i.um_estoque ?? "")}
                              onChange={(e) =>
                                setUsado((a) => ({
                                  ...a,
                                  [i.id_item]: {
                                    quantidade:
                                      a[i.id_item]?.quantidade ?? String(i.necessario ?? ""),
                                    um: e.target.value,
                                  },
                                }))
                              }
                            >
                              {i.unidades.map((u) => (
                                <option key={u} value={u}>
                                  {u}
                                </option>
                              ))}
                            </select>
                            </span>
                          ) : (
                            <span className="w-[74px] text-left text-[13px] text-suave">
                              {i.um_estoque}
                            </span>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 🔑 **O custo saiu da tabela** (pedido do dono, 16/09/2026). Ele
            disputava a leitura com as quantidades e quem está na bancada não
            decide nada com ele. Continua aqui, numa linha ao pé, para quem tem a
            permissão — e `nao-imprimir` o mantém fora da folha que circula na
            cozinha: mandar o custo do prato de mão em mão é distribuir margem
            por engano. */}
        {veCusto && !!p.itens.length && (
          <p className="nao-imprimir mt-4 flex flex-wrap items-baseline justify-end gap-x-3
                        border-t border-linha pt-3 text-[13.5px] text-suave">
            <span>custo desta produção</span>
            <b className="mono text-[15px] text-tinta">{reais(p.custo_total)}</b>
            <span className="mono">
              {custo(p.custo_unitario)} / {p.um_estoque}
            </span>
          </p>
        )}

        {p.itens_faltando > 0 && aberta && (
          <p className="mt-4 text-[13.5px] leading-snug text-suave">
            Falta insumo, mas a produção <b>não é barrada</b>: o razão aceita a saída e marca o
            custo como provisório. O saldo negativo fica à vista até a entrada que faltava ser
            lançada — some do controle é que não pode.
          </p>
        )}
      </Cartao>

      {/* 🔑 **Como se faz** (16/09/2026, pedido do dono: *"precisa saber as
          quantidades e o modo de preparo"*). Sem isto a folha era meia folha: a
          pessoa levava a lista de ingredientes e abria a ficha noutra tela para
          saber o que fazer com eles.
          ⚠️ `whitespace-pre-line`: o modo de preparo é digitado em passos, e um
          texto corrido apaga a ordem que alguém escreveu. */}
      {/* ⚠️ **A caixa aparece SEMPRE**, mesmo vazia (16/09/2026 — o dono pediu
          "uma caixa abaixo com os detalhes para preparo, que são cadastrados na
          ficha" depois de ela já existir, porque a ficha dele não tinha nada
          escrito e o cartão sumia). Um cartão que some quando está vazio não
          ensina onde se preenche; um cartão vazio que diz onde, ensina. */}
      {(
        <Cartao
          titulo="Como se faz"
          descricao={
            p.tempo_preparo_min
              ? `Cerca de ${p.tempo_preparo_min} min · ficha v${p.versao}`
              : `Ficha v${p.versao}`
          }
        >
          {p.modo_preparo ? (
            <p className="prosa max-w-[80ch] whitespace-pre-line text-[15px] leading-relaxed">
              {p.modo_preparo}
            </p>
          ) : (
            <Vazio>
              A ficha ainda não tem modo de preparo escrito.{" "}
              <Link className="link-acao" href={`/fichas/${p.id_ficha}`}>
                abrir a ficha
              </Link>{" "}
              para preencher — é de lá que esta caixa vem.
            </Vazio>
          )}
          {p.alergenos && (
            <p className="mt-4 text-[13.5px] text-suave">
              <b className="text-tinta">Alérgenos:</b> {p.alergenos}
            </p>
          )}
          {p.ficha_observacao && (
            <p className="mt-2 text-[13.5px] text-suave">{p.ficha_observacao}</p>
          )}
        </Cartao>
      )}

      {confirmando && (
        <Confirmacao
          titulo="Confirmar a produção"
          rotuloConfirmar="Produzir"
          ocupado={ocupado}
          aoCancelar={() => setConfirmando(false)}
          aoConfirmar={() => void produzir()}
        >
          <p>
            Produzir{" "}
            <b className="mono">
              {qtd(agora)} {p.um_estoque}
            </b>{" "}
            de <b>{linha.produto}</b>?
          </p>
          {p.itens_faltando > 0 && (
            <p className="mt-2 text-[13.5px] text-alerta">
              {p.itens_faltando} insumo(s) sem saldo suficiente — o custo sai provisório.
            </p>
          )}
          {/* 🔑 As correções de consumo entram na pergunta: elas mudam o que sai
              do estoque, e quem confirma tem de saber que vai gravar o que
              digitou, não o que a receita pedia. */}
          {!!Object.keys(usado).length && (
            <p className="mt-2 text-[13.5px]">
              <b>{Object.keys(usado).length} insumo(s)</b> vão sair na quantidade que você
              corrigiu, não na da receita.
            </p>
          )}
          <p className="mt-3 text-[13.5px] text-suave">
            Isto baixa os ingredientes da ficha e devolve o pronto ao estoque. Nada aqui se
            apaga: correção é estorno.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
