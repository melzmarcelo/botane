"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { Local, ProdutoResumo, reais } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

type Nota = {
  id: number;
  chave_nfe: string | null;
  numero: string | null;
  nome_emitente: string | null;
  fornecedor: string | null;
  data_emissao: string | null;
  valor_total: number;
  status: string;
  itens: number;
  pendentes: number;
};

type ItemNota = {
  id: number;
  seq: number;
  descricao_fornecedor: string;
  codigo_fornecedor: string | null;
  codigo_barras: string | null;
  quantidade: number;
  um_nota: string | null;
  valor_unitario: number;
  valor_frete_rateado: number;
  quantidade_convertida: number | null;
  custo_aquisicao_unitario: number | null;
  variacao_preco_pct: number | null;
  id_produto: number | null;
  produto: string | null;
  um_estoque: string | null;
  sugestao_produto: number | null;
  sugestao_nome: string | null;
  sugestao_score: number | null;
  ignorado: boolean;
};

type NotaDetalhe = Nota & { itens_lista?: ItemNota[]; valor_frete: number; id_local: number | null };

const CORES: Record<string, "erva" | "alerta" | "neutro"> = {
  LANCADA: "erva",
  CONCILIADA: "alerta",
  IMPORTADA: "neutro",
};

export default function PaginaCompras() {
  const { pode } = useSessao();
  const [notas, setNotas] = useState<Nota[] | null>(null);
  const [aberta, setAberta] = useState<(NotaDetalhe & { itens: ItemNota[] }) | null>(null);
  const [produtos, setProdutos] = useState<ProdutoResumo[]>([]);
  const [locais, setLocais] = useState<Local[]>([]);
  const [escolha, setEscolha] = useState<Record<number, string>>({});
  const [erro, setErro] = useState("");
  const [ok, setOk] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const [n, p, l] = await Promise.all([
        api.get<Nota[]>("/omie/notas?limite=50"),
        api.get<ProdutoResumo[]>("/produtos"),
        api.get<Local[]>("/locais"),
      ]);
      setNotas(n);
      setProdutos(p.filter((x) => x.controla_estoque));
      setLocais(l);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function abrir(id: number) {
    setErro("");
    setOk("");
    try {
      const nota = await api.get<NotaDetalhe & { itens: ItemNota[] }>(`/omie/notas/${id}`);
      setAberta(nota);
      // Sugestão já vem marcada: confirmar é um clique, e nunca automático.
      setEscolha(
        Object.fromEntries(
          nota.itens
            .filter((i) => !i.id_produto && i.sugestao_produto)
            .map((i) => [i.id, String(i.sugestao_produto)]),
        ),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao abrir a nota");
    }
  }

  async function sincronizar() {
    setOcupado(true);
    setErro("");
    setOk("");
    try {
      const r = await api.post<{ novas: number; repetidas: number; modo: string }>(
        "/omie/sincronizar?dias=60",
      );
      setOk(
        `${r.novas} nota(s) nova(s), ${r.repetidas} já existia(m).` +
          (r.modo === "simulado" ? " (modo simulado — dados de demonstração)" : ""),
      );
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível sincronizar");
    } finally {
      setOcupado(false);
    }
  }

  async function vincular(item: ItemNota) {
    const id_produto = Number(escolha[item.id]);
    if (!id_produto) return;
    setOcupado(true);
    setErro("");
    try {
      await api.post(`/omie/itens/${item.id}/vincular`, { id_produto, aprender: true });
      await abrir(aberta!.id);
      await carregar();
      setOk("Item vinculado — as próximas notas com esse código entram sozinhas.");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível vincular");
    } finally {
      setOcupado(false);
    }
  }

  async function ignorar(item: ItemNota) {
    setOcupado(true);
    try {
      await api.post(`/omie/itens/${item.id}/ignorar`);
      await abrir(aberta!.id);
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível marcar");
    } finally {
      setOcupado(false);
    }
  }

  async function lancar() {
    if (!aberta) return;
    setOcupado(true);
    setErro("");
    setOk("");
    try {
      const r = await api.post<{ itens_lancados: number; valor: number }>(
        `/omie/notas/${aberta.id}/lancar`,
        {},
      );
      setOk(
        `${r.itens_lancados} item(ns) no estoque, ${reais(Number(r.valor))} — o custo médio de cada insumo foi recalculado.`,
      );
      await abrir(aberta.id);
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível lançar");
    } finally {
      setOcupado(false);
    }
  }

  async function estornar() {
    if (!aberta) return;
    setOcupado(true);
    setErro("");
    setOk("");
    try {
      const r = await api.post<{ estornados: number }>(`/omie/notas/${aberta.id}/estornar`);
      setOk(`${r.estornados} movimento(s) estornado(s) — o razão guarda os dois lados.`);
      await abrir(aberta.id);
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível estornar");
    } finally {
      setOcupado(false);
    }
  }

  const pendentes = aberta?.itens.filter((i) => !i.id_produto && !i.ignorado) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">Compras</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
            Notas de entrada
          </h1>
          <p className="mt-1 max-w-[66ch] text-suave">
            A nota vem do Omie e vira estoque avaliado aqui. O que decide o custo não é o valor
            unitário da nota: é ele menos desconto, mais frete rateado, dividido pelo que
            realmente entra na prateleira.
          </p>
        </div>
        {pode("integracao.omie") && (
          <button className="btn btn-primario" onClick={sincronizar} disabled={ocupado}>
            {ocupado ? "Sincronizando…" : "Buscar no Omie"}
          </button>
        )}
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {ok && <Aviso tipo="ok">{ok}</Aviso>}

      {aberta && (
        <Cartao
          titulo={`NF ${aberta.numero ?? "—"} · ${aberta.fornecedor ?? aberta.nome_emitente ?? ""}`}
          descricao={
            aberta.chave_nfe
              ? `chave ${aberta.chave_nfe.slice(0, 8)}…${aberta.chave_nfe.slice(-6)}`
              : undefined
          }
          acao={
            <div className="flex flex-wrap items-center gap-2">
              <Etiqueta cor={CORES[aberta.status]}>{aberta.status.toLowerCase()}</Etiqueta>
              {aberta.status === "LANCADA" && pode("estoque.ajuste") && (
                <button className="btn btn-secundario" onClick={estornar} disabled={ocupado}>
                  Estornar
                </button>
              )}
              {aberta.status !== "LANCADA" && pode("compras.lancar") && (
                <button
                  className="btn btn-primario"
                  onClick={lancar}
                  disabled={ocupado || !!pendentes.length}
                  title={pendentes.length ? "Há item sem produto vinculado" : undefined}
                >
                  Lançar no estoque
                </button>
              )}
              <button className="rotulo hover:text-erro" onClick={() => setAberta(null)}>
                fechar
              </button>
            </div>
          }
        >
          {!!pendentes.length && (
            <div className="mb-4">
              <Aviso tipo="info">
                {pendentes.length} item(ns) sem produto vinculado. A nota não entra no estoque
                enquanto isso — importar errado é pior que não importar.
              </Aviso>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Item da nota</th>
                  <th className="num">Qtd</th>
                  <th className="num">Valor un.</th>
                  <th className="num">Frete rateado</th>
                  <th>Produto no Botané</th>
                  <th className="num">Custo real</th>
                </tr>
              </thead>
              <tbody>
                {aberta.itens.map((i) => (
                  <tr key={i.id} className={i.ignorado ? "opacity-55" : ""}>
                    <td>
                      <span className="font-semibold">{i.descricao_fornecedor}</span>
                      <span className="mono block text-[12px] text-suave">
                        {i.codigo_fornecedor ?? "—"}
                        {i.codigo_barras && ` · EAN ${i.codigo_barras}`}
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
                    <td className="num">{reais(Number(i.valor_unitario))}</td>
                    <td className="num text-suave">{reais(Number(i.valor_frete_rateado))}</td>
                    <td>
                      {i.id_produto ? (
                        <span className="font-medium text-erva">{i.produto}</span>
                      ) : i.ignorado ? (
                        <Etiqueta>fora do estoque</Etiqueta>
                      ) : pode("compras.conciliar") ? (
                        <div className="flex flex-col gap-1.5">
                          <select
                            className="campo py-1 text-[13px]"
                            value={escolha[i.id] ?? ""}
                            onChange={(e) => setEscolha({ ...escolha, [i.id]: e.target.value })}
                          >
                            <option value="">— escolha o produto —</option>
                            {produtos.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.nome} {p.um_estoque ? `(${p.um_estoque})` : ""}
                              </option>
                            ))}
                          </select>
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
                    <td className="num">
                      {i.custo_aquisicao_unitario ? (
                        <>
                          <span className="font-semibold">
                            {reais(Number(i.custo_aquisicao_unitario))}
                          </span>
                          {i.variacao_preco_pct !== null && (
                            <span
                              className={`block text-[12px] ${
                                Number(i.variacao_preco_pct) > 10 ? "text-erro" : "text-suave"
                              }`}
                            >
                              {Number(i.variacao_preco_pct) > 0 ? "+" : ""}
                              {Number(i.variacao_preco_pct).toFixed(1)}% vs. última compra
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
        </Cartao>
      )}

      <Cartao titulo={notas ? `${notas.length} nota(s)` : "Notas"}>
        {!notas ? (
          <Carregando />
        ) : !notas.length ? (
          <Vazio>
            Nenhuma nota ainda. Use &quot;Buscar no Omie&quot; — sem credencial, ele traz as
            notas de demonstração.
          </Vazio>
        ) : (
          <ul className="flex flex-col gap-px bg-linha">
            {notas.map((n) => (
              <li
                key={n.id}
                className="flex flex-wrap items-center justify-between gap-3 bg-superficie py-3"
              >
                <button className="min-w-0 text-left" onClick={() => void abrir(n.id)}>
                  <span className="font-semibold hover:text-erva">
                    NF {n.numero ?? "—"} · {n.fornecedor ?? n.nome_emitente ?? "sem fornecedor"}
                  </span>
                  <span className="block text-[13px] text-suave">
                    {n.data_emissao
                      ? new Date(n.data_emissao + "T12:00:00").toLocaleDateString("pt-BR")
                      : "sem data"}{" "}
                    · {n.itens} item(ns) · {reais(Number(n.valor_total))}
                  </span>
                </button>
                <span className="flex items-center gap-2">
                  {n.pendentes > 0 && <Etiqueta cor="alerta">{n.pendentes} pendente(s)</Etiqueta>}
                  <Etiqueta cor={CORES[n.status]}>{n.status.toLowerCase()}</Etiqueta>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Cartao>
    </div>
  );
}
