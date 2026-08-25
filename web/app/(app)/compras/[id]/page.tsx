"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Local, reais } from "@/lib/cadastros";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fonteProdutos, ItemBusca } from "@/lib/busca-cadastro";
import {
  Aviso,
  Campo,
  Carregando,
  Cartao,
  Confirmacao,
  Etiqueta,
  Vazio,
} from "@/components/ui";
import { CORES, dataBr, ItemNota, NotaDetalhe, ORIGENS } from "../tipos";

/**
 * Uma nota de entrada, inteira, numa página só.
 *
 * Antes ela abria como um cartão dentro da lista: a tabela de itens ficava
 * espremida embaixo de tudo e o rodapé de valores não existia — quem conferia
 * via as linhas mas não via o total que elas somam, que é justamente o número
 * que se bate contra o papel do fornecedor.
 *
 * A página segue o **mesmo modelo da digitação**: cabeçalho, itens, total. Quem
 * digitou uma nota reconhece a de leitura, e a conferência vira comparar duas
 * telas com a mesma forma em vez de traduzir uma na outra.
 */

// Item de nota vira movimento de estoque: só produto que controla estoque.
const PRODUTOS = fonteProdutos((p) => p.controla_estoque);

export default function PaginaNota() {
  const { id } = useParams<{ id: string }>();
  const aviso = useAviso();
  const { pode } = useSessao();

  const [nota, setNota] = useState<NotaDetalhe | null>(null);
  const [locais, setLocais] = useState<Local[]>([]);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [confirmando, setConfirmando] = useState<"estornar" | null>(null);
  const [escolha, setEscolha] = useState<Record<number, string>>({});
  const [rotuloEscolhido, setRotuloEscolhido] = useState<Record<number, string>>({});

  const carregar = useCallback(async () => {
    try {
      const [n, l] = await Promise.all([
        api.get<NotaDetalhe>(`/notas/${id}`),
        api.get<Local[]>("/locais"),
      ]);
      setNota(n);
      setLocais(l);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar a nota");
    }
  }, [id]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function vincular(item: ItemNota) {
    const id_produto = Number(escolha[item.id]);
    if (!id_produto) return;
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>(`/notas/itens/${item.id}/vincular`, {
        id_produto,
        aprender: true,
      });
      aviso.sucesso(r.message);
      setEscolha({ ...escolha, [item.id]: "" });
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível vincular");
    } finally {
      setOcupado(false);
    }
  }

  async function criarProduto(item: ItemNota) {
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>(
        `/notas/itens/${item.id}/criar-produto`,
        {},
      );
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível criar o produto");
    } finally {
      setOcupado(false);
    }
  }

  async function ignorar(item: ItemNota) {
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>(`/notas/itens/${item.id}/ignorar`, {});
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível ignorar");
    } finally {
      setOcupado(false);
    }
  }

  async function reconciliar() {
    setOcupado(true);
    try {
      const r = await api.post<{ vinculados: number; message: string }>(
        `/notas/reconciliar?id_nota=${id}`,
      );
      if (r.vinculados) aviso.sucesso(r.message);
      else aviso.erro(r.message + " — cadastre os produtos ou importe o catálogo do Omie.");
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível reconciliar");
    } finally {
      setOcupado(false);
    }
  }

  async function lancar() {
    setOcupado(true);
    try {
      const r = await api.post<{ itens_lancados: number; valor: number }>(
        `/notas/${id}/lancar`,
        {},
      );
      aviso.sucesso(
        `${r.itens_lancados} item(ns) no estoque, ${reais(Number(r.valor))} — o custo médio de ` +
          "cada insumo foi recalculado.",
      );
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível lançar");
    } finally {
      setOcupado(false);
    }
  }

  async function estornar() {
    setOcupado(true);
    try {
      const r = await api.post<{ estornados: number }>(`/notas/${id}/estornar`, {});
      aviso.sucesso(`${r.estornados} movimento(s) desfeito(s) — o razão guarda os dois lados.`);
      setConfirmando(null);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível estornar");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!nota) return <Carregando />;

  const pendentes = nota.itens.filter((i) => !i.id_produto && !i.ignorado);
  const localDaNota = locais.find((l) => l.id === nota.id_local)?.nome ?? "";
  const lancada = nota.status === "LANCADA";
  // A soma dos itens, como ela aparece na nota — antes de frete, desconto e
  // IPI/ST. É esta linha que se bate contra o papel do fornecedor.
  const somaItens = nota.itens.reduce(
    (s, i) => s + Number(i.valor_total || Number(i.quantidade) * Number(i.valor_unitario)),
    0,
  );

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/compras" className="link-voltar">
          notas de entrada
        </Link>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
          NF {nota.numero ?? "—"}
        </h1>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <Etiqueta cor={CORES[nota.status]}>{nota.status.toLowerCase()}</Etiqueta>
          <Etiqueta>{ORIGENS[nota.origem] ?? nota.origem.toLowerCase()}</Etiqueta>
          {nota.chave_nfe && (
            <Etiqueta>
              chave {nota.chave_nfe.slice(0, 8)}…{nota.chave_nfe.slice(-6)}
            </Etiqueta>
          )}
          {lancada && nota.lancada_em && (
            <Etiqueta cor="erva">lançada em {dataBr(nota.lancada_em)}</Etiqueta>
          )}
        </div>
        <p className="mt-2 max-w-[70ch] text-suave">
          {nota.fornecedor ?? nota.nome_emitente ?? "sem fornecedor"}
          {nota.cnpj_emitente && ` · ${nota.cnpj_emitente}`}
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {!lancada && pode("compras.lancar") && (
            <button
              className="btn btn-primario"
              onClick={lancar}
              disabled={ocupado || !!pendentes.length}
              title={pendentes.length ? "Há item sem produto vinculado" : undefined}
            >
              Lançar no estoque
            </button>
          )}
          {/* Nota digitada e ainda não lançada se corrige: quem digitou vinte
              itens acha o erro no item três, e descartar tudo era a única
              saída. A que veio do XML ou do Omie não entra aqui — ela é o
              documento do fornecedor. */}
          {nota.origem === "MANUAL" && !lancada && pode("compras.notas") && (
            <Link href={`/compras/${nota.id}/editar`} className="btn btn-secundario">
              Corrigir
            </Link>
          )}
          {lancada && pode("estoque.ajuste") && (
            <button
              className="btn btn-secundario"
              onClick={() => setConfirmando("estornar")}
              disabled={ocupado}
            >
              Estornar
            </button>
          )}
        </div>
      </header>

      {!!pendentes.length && (
        <Aviso tipo="info">
          {pendentes.length} item(ns) sem produto vinculado. A nota não entra no estoque enquanto
          isso — importar errado é pior que não importar. Se os produtos já foram cadastrados
          depois desta nota,{" "}
          <button className="underline hover:text-erva" onClick={reconciliar}>
            procure de novo
          </button>
          .
        </Aviso>
      )}

      {/* ------------------------------------------------------- cabeçalho */}
      <Cartao titulo="Cabeçalho" descricao="O que identifica a nota e de quem ela veio.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Campo rotulo="Fornecedor">
            <p className="mt-1.5 text-[15px]">
              {nota.fornecedor ?? nota.nome_emitente ?? "—"}
            </p>
          </Campo>
          <Campo rotulo="Número">
            <p className="mono mt-1.5 text-[15px]">{nota.numero ?? "—"}</p>
          </Campo>
          <Campo rotulo="Série">
            <p className="mono mt-1.5 text-[15px]">{nota.serie ?? "—"}</p>
          </Campo>
          <Campo rotulo="Emissão">
            <p className="mono mt-1.5 text-[15px]">{dataBr(nota.data_emissao)}</p>
          </Campo>
          <Campo rotulo="Entrada">
            <p className="mono mt-1.5 text-[15px]">{dataBr(nota.data_entrada)}</p>
          </Campo>
          <Campo rotulo="CNPJ do emitente">
            <p className="mono mt-1.5 text-[15px]">{nota.cnpj_emitente ?? "—"}</p>
          </Campo>
          <Campo rotulo="Origem">
            <p className="mt-1.5 text-[15px]">{ORIGENS[nota.origem] ?? nota.origem}</p>
          </Campo>
          {/* Reserva, não regra: cada produto entra no local do CADASTRO dele.
              Este vale para o produto que ainda não tem um definido. */}
          <Campo rotulo="Local de reserva" dica="para produto sem local no cadastro">
            <p className="mt-1.5 text-[15px]">{localDaNota || "—"}</p>
          </Campo>
        </div>
        {nota.chave_nfe && (
          <p className="mono mt-4 break-all text-[12.5px] text-suave">
            chave da NF-e: {nota.chave_nfe}
          </p>
        )}
      </Cartao>

      {/* ------------------------------------------------------------ itens */}
      <Cartao
        titulo="Itens"
        descricao="O que veio na nota, para onde vai e por quanto entra no estoque."
        acao={<Etiqueta>{nota.itens.length} item(ns)</Etiqueta>}
      >
        {!nota.itens.length ? (
          <Vazio>Esta nota não tem item nenhum.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  {/* ⚠️ A largura mora na COLUNA, e com `min-w` além do `w`:
                      em `table-layout: auto` o navegador ignora a largura
                      sugerida quando falta espaço. Somadas, elas passavam da
                      área útil e empurravam o "custo un." — a coluna que mais
                      interessa a quem confere — para fora da tela. */}
                  <th className="num w-[36px] min-w-[36px]">#</th>
                  <th className="min-w-[150px]">Item da nota</th>
                  <th className="num w-[96px] min-w-[96px]">Qtd</th>
                  <th className="num w-[92px] min-w-[92px]">Valor un.</th>
                  <th className="num w-[96px] min-w-[96px]">Total do item</th>
                  <th className="num w-[92px] min-w-[92px]">Frete rateado</th>
                  <th className="min-w-[176px]">Produto no Botané</th>
                  <th className="min-w-[96px]">Entra em</th>
                  <th className="num w-[100px] min-w-[100px]">Custo un.</th>
                </tr>
              </thead>
              <tbody>
                {nota.itens.map((i) => (
                  <tr key={i.id} className={i.ignorado ? "opacity-55" : ""}>
                    <td className="num mono text-suave">{i.seq}</td>
                    <td>
                      <span className="font-semibold">{i.descricao_fornecedor}</span>
                      <span className="mono block text-[12px] text-suave">
                        {i.codigo_fornecedor ?? "—"}
                        {i.codigo_barras && ` · EAN ${i.codigo_barras}`}
                        {i.lote_nf && ` · lote ${i.lote_nf}`}
                      </span>
                    </td>
                    <td className="num whitespace-nowrap">
                      {Number(i.quantidade)} {i.um_nota ?? ""}
                      {i.quantidade_convertida && (
                        <span className="block text-[12px] text-suave">
                          = {Number(i.quantidade_convertida)} {i.um_estoque ?? ""}
                        </span>
                      )}
                    </td>
                    <td className="num mono">{reais(Number(i.valor_unitario))}</td>
                    <td className="num mono">
                      {reais(
                        Number(i.valor_total) ||
                          Number(i.quantidade) * Number(i.valor_unitario),
                      )}
                      {(Number(i.valor_desconto) > 0 || Number(i.valor_acrescimo) > 0) && (
                        <span className="block text-[11.5px] text-suave">
                          {Number(i.valor_desconto) > 0 &&
                            `− ${reais(Number(i.valor_desconto))}`}
                          {Number(i.valor_acrescimo) > 0 &&
                            ` + ${reais(Number(i.valor_acrescimo))}`}
                        </span>
                      )}
                    </td>
                    <td className="num mono text-suave">
                      {reais(Number(i.valor_frete_rateado))}
                    </td>
                    <td>
                      {i.id_produto ? (
                        <span className="font-medium text-erva">{i.produto}</span>
                      ) : i.ignorado ? (
                        <Etiqueta>fora do estoque</Etiqueta>
                      ) : pode("compras.conciliar") ? (
                        <div className="flex flex-col gap-1.5">
                          <BuscaCadastro
                            fonte={PRODUTOS}
                            selecionado={
                              escolha[i.id]
                                ? {
                                    id: Number(escolha[i.id]),
                                    rotulo: rotuloEscolhido[i.id] ?? "",
                                  }
                                : null
                            }
                            aoEscolher={(item: ItemBusca | null) => {
                              setEscolha({ ...escolha, [i.id]: item ? String(item.id) : "" });
                              setRotuloEscolhido((r) => ({
                                ...r,
                                [i.id]: item ? rotuloDe(item) : "",
                              }));
                            }}
                          />
                          {i.sugestao_nome && (
                            <span className="text-[12px] text-suave">
                              palpite: {i.sugestao_nome} ({Number(i.sugestao_score).toFixed(0)}%)
                            </span>
                          )}
                          <span className="flex gap-3">
                            <button
                              className="rotulo text-erva hover:underline"
                              onClick={() => void vincular(i)}
                              disabled={!escolha[i.id]}
                            >
                              vincular
                            </button>
                            {/* O insumo ainda não existe no cadastro: criar daqui
                                poupa sair da tela, cadastrar e voltar. */}
                            {pode("cadastros.produtos") && (
                              <button
                                className="rotulo hover:text-erva"
                                onClick={() => void criarProduto(i)}
                              >
                                criar produto
                              </button>
                            )}
                            <button
                              className="rotulo hover:text-erro"
                              onClick={() => void ignorar(i)}
                            >
                              não controla estoque
                            </button>
                          </span>
                        </div>
                      ) : (
                        <Etiqueta cor="alerta">pendente</Etiqueta>
                      )}
                    </td>
                    {/* Cada item vai para o local do CADASTRO do produto: a
                        mesma nota traz congelado e seco. Sem local no produto,
                        vale o da nota — e a coluna diz qual é. */}
                    <td className="whitespace-nowrap text-[13px]">
                      {i.id_produto ? (
                        i.local_destino ? (
                          <span>{i.local_destino}</span>
                        ) : (
                          <span className="text-suave">
                            {localDaNota || "local da nota"}
                            <span className="block text-[11.5px]">sem local no cadastro</span>
                          </span>
                        )
                      ) : (
                        <span className="text-suave">—</span>
                      )}
                    </td>
                    <td className="num">
                      {i.custo_aquisicao_unitario ? (
                        <>
                          <span className="mono font-semibold">
                            {reais(Number(i.custo_aquisicao_unitario))}
                          </span>
                          {i.variacao_preco_pct !== null && (
                            <span
                              className={`block text-[12px] ${
                                Number(i.variacao_preco_pct) > 10 ? "text-erro" : "text-suave"
                              }`}
                            >
                              {Number(i.variacao_preco_pct) > 0 ? "+" : ""}
                              {Number(i.variacao_preco_pct).toFixed(1).replace(".", ",")}% vs. última compra
                            </span>
                          )}
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>

      {/* ------------------------------------------------------------ total */}
      <Cartao titulo="Total" descricao="O que a nota soma — e o que disso vira custo.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Campo rotulo="Produtos">
            <p className="mono mt-1.5 text-[15px]">{reais(somaItens)}</p>
          </Campo>
          <Campo rotulo="Frete">
            <p className="mono mt-1.5 text-[15px]">{reais(Number(nota.valor_frete))}</p>
          </Campo>
          <Campo rotulo="Desconto">
            <p className="mono mt-1.5 text-[15px]">
              {Number(nota.valor_desconto) > 0 ? "− " : ""}
              {reais(Number(nota.valor_desconto))}
            </p>
          </Campo>
          <Campo rotulo="IPI / ST / outros">
            <p className="mono mt-1.5 text-[15px]">
              {reais(Number(nota.valor_outros))}
            </p>
          </Campo>
        </div>

        <div className="mt-5 flex flex-wrap items-baseline justify-between gap-3 border-t-2 border-linha2 pt-4">
          <span className="text-[15px] font-semibold">Total da nota</span>
          <span className="mono text-[22px] font-bold">{reais(Number(nota.valor_total))}</span>
        </div>

        <p className="mt-4 max-w-[80ch] text-[13.5px] leading-snug text-suave">
          O <b>custo un.</b> da coluna dos itens já traz o frete rateado e a conversão da
          embalagem: é ele que vira custo médio no estoque, não o valor unitário da nota.
        </p>
      </Cartao>

      {confirmando === "estornar" && (
        <Confirmacao
          titulo="Desfazer o lançamento da nota"
          rotuloConfirmar="Estornar"
          perigo
          ocupado={ocupado}
          aoCancelar={() => setConfirmando(null)}
          aoConfirmar={() => void estornar()}
        >
          <p>
            Estornar a <b>NF {nota.numero ?? "—"}</b> de{" "}
            <b>{nota.fornecedor ?? nota.nome_emitente ?? "—"}</b>?
          </p>
          <p className="mt-3 text-[13.5px] text-suave">
            Cada entrada ganha uma contrapartida no razão e o custo médio volta a ser
            recalculado. Nada se apaga: os dois movimentos ficam à vista.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
