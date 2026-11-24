"use client";

/**
 * Mudar a quantidade ou excluir uma linha de documento lançado à mão e em aberto.
 *
 * 🔑 Pedido do dono (24/11/2026): *"editar a quantidade e excluir itens em documentos lançados
 * a mão que ainda estão em aberto"*. Quem decide se pode é o servidor (`pode_mudar_itens`).
 * 🔑 O estoque acompanha por ESTORNO e nova baixa (o razão não se reescreve) — a tela só avisa.
 * ⚠️ A última linha não sai: o documento inteiro se desfaz cancelando.
 */

import { FormEvent, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Confirmacao, Modal } from "@/components/ui";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { textoParaNumero } from "@/lib/numeros";

import type { ItemVenda } from "../tipos";

export default function AcoesDoItem({ idVenda, item, nome, ultimo, aoMudar }: {
  idVenda: number;
  item: ItemVenda;
  nome: string;
  ultimo: boolean;
  aoMudar: () => void;
}) {
  const aviso = useAviso();
  const [editando, setEditando] = useState(false);
  const [excluindo, setExcluindo] = useState(false);
  const [quantidade, setQuantidade] = useState(String(Number(item.quantidade)).replace(".", ","));
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const nova = textoParaNumero(quantidade) ?? 0;
  const diferenca = (nova - Number(item.quantidade)) * Number(item.valor_unitario);

  async function salvar(e?: FormEvent) {
    e?.preventDefault();
    if (nova <= 0) return setErro("Informe uma quantidade maior que zero. Para tirar a linha, exclua.");
    setOcupado(true);
    try {
      const r = await api.put<{ message: string }>(`/vendas/${idVenda}/itens/${item.id}`, { quantidade: nova });
      aviso.sucesso(r.message);
      setEditando(false);
      aoMudar();
    } catch (x) {
      setErro(x instanceof Error ? x.message : "Não foi possível mudar a quantidade");
    } finally {
      setOcupado(false);
    }
  }

  async function excluir() {
    setOcupado(true);
    try {
      const r = await api.delete<{ message: string }>(`/vendas/${idVenda}/itens/${item.id}`);
      aviso.sucesso(r.message);
      setExcluindo(false);
      aoMudar();
    } catch (x) {
      aviso.erro(x instanceof Error ? x.message : "Não foi possível excluir o item");
      setExcluindo(false);
    } finally {
      setOcupado(false);
    }
  }

  return (
    <span className="flex justify-end gap-1 whitespace-nowrap">
      <button type="button" className="btn btn-terciario btn-pequeno" data-acao-item="quantidade"
              onClick={() => { setErro(""); setEditando(true); }}>
        Quantidade
      </button>
      <button type="button" className="btn btn-terciario btn-pequeno" data-acao-item="excluir"
              disabled={ultimo}
              title={ultimo ? "É o único item: para desfazer o documento, cancele a venda" : undefined}
              onClick={() => setExcluindo(true)}>
        Excluir
      </button>

      {editando && (
        <Modal titulo={`Quantidade de ${nome}`} aoFechar={() => setEditando(false)} largura="420px"
               rodape={
                 <div className="flex justify-end gap-2">
                   <button type="button" className="btn" onClick={() => setEditando(false)}>Cancelar</button>
                   <button type="button" className="btn btn-primario" id="item-salvar-quantidade"
                           disabled={ocupado} onClick={() => void salvar()}>
                     {ocupado ? "Salvando…" : "Salvar"}
                   </button>
                 </div>
               }>
          <form onSubmit={salvar} className="flex flex-col gap-3 whitespace-normal">
            {erro && <Aviso tipo="erro">{erro}</Aviso>}
            <Campo rotulo="Quantidade">
              <input className="campo" id="item-quantidade" inputMode="decimal" autoFocus
                     value={quantidade} onFocus={(e) => e.target.select()}
                     onChange={(e) => setQuantidade(e.target.value)} />
            </Campo>
            <p className="text-[13px] text-suave">
              {reais(Number(item.valor_unitario))} cada
              {nova > 0 && Math.abs(diferenca) >= 0.005 && (
                <> · a venda {diferenca > 0 ? "sobe" : "cai"} {reais(Math.abs(diferenca))}</>
              )}
              . O estoque acompanha: a baixa deste produto é estornada e lançada de novo com a
              quantidade nova.
            </p>
          </form>
        </Modal>
      )}
      {excluindo && (
        <Confirmacao titulo="Excluir este item?" rotuloConfirmar="Excluir item" rotuloCancelar="Manter"
                     perigo ocupado={ocupado} aoConfirmar={() => void excluir()}
                     aoCancelar={() => setExcluindo(false)}>
          {nome}, {String(Number(item.quantidade)).replace(".", ",")} ×{" "}
          {reais(Number(item.valor_unitario))}, sai do documento. A venda cai{" "}
          {reais(Number(item.valor_total))} e o que ele baixou volta ao estoque.
        </Confirmacao>
      )}
    </span>
  );
}
