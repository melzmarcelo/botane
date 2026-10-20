"use client";

/**
 * Acrescentar itens a uma venda já lançada — o mesmo documento, mais linhas.
 *
 * 🔑 Pedido do dono (20/10/2026): *"permitir editar um documento, adicionar mais itens,
 * desde que o período que ele esteja já não foi fechado"*. Quem decide se pode é o
 * servidor (`pode_acrescentar`); aqui só se monta a lista.
 * ⚠️ Só ACRESCENTA: o que já entrou está no razão, que é append-only. Tirar uma linha é
 * cancelar a venda e lançar de novo.
 * 🔑 O preço que entra sozinho é o do DIA DA VENDA, não o de hoje — o mesmo do lançamento.
 */

import { useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { reais } from "@/lib/cadastros";
import { CampoMoeda, Cartao } from "@/components/ui";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fonteProdutos, ItemBusca } from "@/lib/busca-cadastro";
import { moedaParaNumero, numeroParaMoeda } from "@/lib/numeros";

const PRODUTOS = fonteProdutos();

type Linha = { id_produto: string; rotulo: string; quantidade: string; valor_unitario: string };
const VAZIA: Linha = { id_produto: "", rotulo: "", quantidade: "", valor_unitario: "" };

export default function AcrescentarItens({ idVenda, data, aoAcrescentar }: {
  idVenda: number; data: string; aoAcrescentar: () => void;
}) {
  const aviso = useAviso();
  const [aberto, setAberto] = useState(false);
  const [linhas, setLinhas] = useState<Linha[]>([{ ...VAZIA }]);
  const [ocupado, setOcupado] = useState(false);

  const qtd = (l: Linha) => Number(l.quantidade.replace(",", ".")) || 0;
  const prontas = linhas.filter((l) => l.id_produto && qtd(l) > 0);
  const total = prontas.reduce((s, l) => s + qtd(l) * (moedaParaNumero(l.valor_unitario) ?? 0), 0);

  function trocar(n: number, mudanca: Partial<Linha>) {
    setLinhas((atual) => atual.map((l, i) => (i === n ? { ...l, ...mudanca } : l)));
  }

  async function escolher(n: number, item: ItemBusca | null) {
    const emBranco = !linhas[n].valor_unitario.trim();
    trocar(n, { id_produto: item ? String(item.id) : "", rotulo: item ? rotuloDe(item) : "" });
    if (!item || !emBranco) return;
    try {
      const q = new URLSearchParams({ data });
      q.append("ids", String(item.id));
      const r = await api.get<{ precos: Record<string, number | null> }>(`/vendas/precos?${q}`);
      const preco = r.precos[String(item.id)];
      if (preco && preco > 0) {
        setLinhas((atual) => atual.map((l, i) =>
          i === n && l.id_produto === String(item.id) && !l.valor_unitario.trim()
            ? { ...l, valor_unitario: numeroParaMoeda(preco) } : l));
      }
    } catch {
      // Em branco, o servidor põe o preço do dia.
    }
  }

  async function gravar() {
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>(`/vendas/${idVenda}/itens`, {
        itens: prontas.map((l) => ({
          id_produto: Number(l.id_produto),
          quantidade: qtd(l),
          valor_unitario: moedaParaNumero(l.valor_unitario) ?? 0,
        })),
      });
      aviso.sucesso(r.message);
      setLinhas([{ ...VAZIA }]);
      setAberto(false);
      aoAcrescentar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível acrescentar");
    } finally {
      setOcupado(false);
    }
  }

  if (!aberto) {
    return (
      <div>
        <button type="button" id="venda-acrescentar" className="btn btn-secundario" onClick={() => setAberto(true)}>
          Acrescentar itens
        </button>
      </div>
    );
  }
  return (
    <Cartao titulo="Acrescentar itens"
            descricao="Entram neste mesmo documento: custo congelado agora, baixa do estoque e a política da pessoa, como os outros. O preço é o do dia da venda.">
      <div className="grid-rolante" id="venda-acrescentar-itens">
        <table className="tabela">
          <thead>
            <tr>
              <th style={{ minWidth: 260 }}>Produto</th>
              <th className="num" style={{ width: 120, minWidth: 120 }}>Qtd</th>
              <th className="num" style={{ width: 140, minWidth: 140 }}>Valor unitário</th>
              <th className="num" style={{ width: 120, minWidth: 120 }}>Total</th>
              <th style={{ width: 40 }}></th>
            </tr>
          </thead>
          <tbody>
            {linhas.map((l, n) => (
              <tr key={n}>
                <td>
                  <BuscaCadastro fonte={PRODUTOS}
                                 selecionado={l.id_produto ? { id: Number(l.id_produto), rotulo: l.rotulo } : null}
                                 aoEscolher={(item: ItemBusca | null) => void escolher(n, item)} />
                </td>
                <td>
                  <input className="campo mono" type="number" step="0.001" min="0" value={l.quantidade}
                         onChange={(e) => trocar(n, { quantidade: e.target.value })} />
                </td>
                <td>
                  <CampoMoeda valor={l.valor_unitario} aoMudar={(v) => trocar(n, { valor_unitario: v })} />
                </td>
                <td className="num tabular-nums">{reais(qtd(l) * (moedaParaNumero(l.valor_unitario) ?? 0))}</td>
                <td className="text-right">
                  {linhas.length > 1 && (
                    <button type="button" className="link-acao link-acao-erro"
                            onClick={() => setLinhas(linhas.filter((_, i) => i !== n))}>
                      tirar
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <button type="button" className="btn btn-secundario" onClick={() => setLinhas([...linhas, { ...VAZIA }])}>
          Mais um item
        </button>
        <p className="text-[15px]"><span className="text-suave">acrescenta </span><b className="tabular-nums">{reais(total)}</b></p>
      </div>
      <div className="mt-4 flex gap-2">
        <button type="button" id="venda-acrescentar-gravar" className="btn btn-primario"
                aria-busy={ocupado} disabled={ocupado || !prontas.length} onClick={() => void gravar()}>
          {ocupado ? "Acrescentando…" : `Acrescentar ${prontas.length || ""} item(ns)`}
        </button>
        <button type="button" className="btn btn-secundario" onClick={() => setAberto(false)}>Cancelar</button>
      </div>
    </Cartao>
  );
}
