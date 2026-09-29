"use client";

import { useEffect, useMemo, useState } from "react";

import { Aviso, Carregando, Modal } from "@/components/ui";
import { catalogoParaTroca, reais, type ItemDoCatalogo, type PedidoCompleto } from "@/lib/pedidos";

/**
 * Trocar produtos antes de confirmar (decisão do dono: *"a casa precisa aceitar e, caso
 * necessário, pode trocar produtos"*).
 *
 * ⚠️ Item que já estava mantém o preço do envio; item novo entra pelo preço vigente do cardápio.
 * O total que aparece aqui é PRÉVIA — quem calcula o que vale é o servidor.
 */
type Linha = { id_produto: number; id_item_catalogo: number | null; nome: string; preco: number; quantidade: number; observacao: string | null };

export default function TrocarProdutos({ pedido, aoFechar, aoConfirmar }: {
  pedido: PedidoCompleto;
  aoFechar: () => void;
  aoConfirmar: (itens: { id_produto?: number | null; id_item_catalogo?: number | null; quantidade: number; observacao?: string | null }[]) => Promise<void>;
}) {
  const [catalogo, setCatalogo] = useState<ItemDoCatalogo[] | null>(null);
  const [linhas, setLinhas] = useState<Linha[]>(() => pedido.itens.map((i) => ({
    id_produto: i.id_produto, id_item_catalogo: null, nome: i.nome, preco: i.preco_unitario,
    quantidade: i.quantidade, observacao: i.observacao,
  })));
  const [novo, setNovo] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    catalogoParaTroca(pedido.id).then(setCatalogo).catch(() => setCatalogo([]));
  }, [pedido.id]);

  const total = useMemo(() => linhas.reduce((s, l) => s + l.preco * l.quantidade, 0) + pedido.taxa_entrega,
    [linhas, pedido.taxa_entrega]);
  const fora = catalogo?.filter((c) => !linhas.some((l) => l.id_produto === c.id_produto)) ?? [];

  function acrescentar() {
    const c = catalogo?.find((x) => String(x.id_item) === novo);
    if (!c) return;
    setLinhas([...linhas, { id_produto: c.id_produto, id_item_catalogo: c.id_item, nome: c.nome, preco: c.preco, quantidade: 1, observacao: null }]);
    setNovo("");
  }

  async function confirmar() {
    setOcupado(true);
    try {
      await aoConfirmar(linhas.map((l) => (l.id_item_catalogo
        ? { id_item_catalogo: l.id_item_catalogo, quantidade: l.quantidade, observacao: l.observacao }
        : { id_produto: l.id_produto, quantidade: l.quantidade, observacao: l.observacao })));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Modal titulo={`Trocar produtos do pedido ${pedido.numero}`}
           descricao="Ajuste as quantidades, tire ou ponha itens do mesmo cardápio. O que o cliente pediu fica no histórico, e ele vê o pedido como ficou."
           aoFechar={aoFechar}
           rodape={
             <div className="flex flex-wrap items-center justify-end gap-3">
               <span className="text-[14px]">Total: <b className="mono">{reais(total)}</b></span>
               <button className="btn btn-secundario" onClick={aoFechar}>Voltar</button>
               <button className="btn btn-primario" disabled={ocupado || !linhas.length} aria-busy={ocupado}
                       onClick={() => void confirmar()}>{ocupado ? "…" : "Confirmar com as trocas"}</button>
             </div>
           }>
      {!linhas.length && <Aviso tipo="erro">O pedido precisa de ao menos um item — para desistir, recuse.</Aviso>}
      <table className="tabela">
        <thead><tr><th>Produto</th><th className="w-[110px]">Qtd</th><th className="text-right">Preço</th><th /></tr></thead>
        <tbody>
          {linhas.map((l, k) => (
            <tr key={`${l.id_produto}-${k}`}>
              <td>{l.nome}{l.id_item_catalogo && <span className="block text-[12px] text-suave">novo no pedido</span>}</td>
              <td>
                <input className="campo mono" type="number" min={1} step={1} value={l.quantidade}
                       onChange={(e) => setLinhas(linhas.map((x, j) => j === k ? { ...x, quantidade: Math.max(1, Number(e.target.value) || 1) } : x))} />
              </td>
              <td className="num">{reais(l.preco)}</td>
              <td className="text-right">
                <button className="link-acao" onClick={() => setLinhas(linhas.filter((_, j) => j !== k))}>tirar</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4 flex flex-wrap items-end gap-2">
        {!catalogo ? <Carregando /> : (
          <>
            <label className="min-w-0 flex-1">
              <span className="rotulo-campo">Pôr outro produto do cardápio</span>
              <select className="campo mt-1.5" value={novo} onChange={(e) => setNovo(e.target.value)}>
                <option value="">—</option>
                {fora.map((c) => <option key={c.id_item} value={c.id_item}>{c.nome} · {reais(c.preco)}</option>)}
              </select>
            </label>
            <button className="btn btn-secundario" disabled={!novo} onClick={acrescentar}>Acrescentar</button>
          </>
        )}
      </div>
    </Modal>
  );
}
