"use client";

import { useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { Campo, Modal } from "@/components/ui";
import { fonteProdutos, type ItemBusca } from "@/lib/busca-cadastro";
import { incluirNaContagem } from "@/lib/inventario";

/**
 * Incluir na contagem um produto achado na prateleira que não estava na lista.
 *
 * 🔑 **Pedido do dono (26/09/2026):** *"ao realizar um inventário de um setor, e for
 * encontrado um produto que não estava no inventário ou não estava naquele setor, como
 * proceder? … pode incluir."* O produto entra com o saldo que o sistema tinha NAQUELA
 * prateleira (quase sempre zero), marcado "incluído", e a quantidade se digita como nos
 * outros. No fechamento, a sobra entra pelo custo médio dele.
 *
 * ⚠️ **Antes de incluir, a pergunta que evita ajuste falso:** o produto mora mesmo aqui,
 * ou só foi guardado no lugar errado? Fora do lugar, o certo é devolvê-lo e contá-lo onde
 * ele mora — contado aqui, ele vira sobra aqui e falta lá.
 */
const PRODUTOS = fonteProdutos("controla_estoque=true");

export default function IncluirProduto<T>({
  idInventario,
  locais,
  aoIncluir,
  aoFechar,
}: {
  idInventario: string;
  locais: { id: number; nome: string }[];
  aoIncluir: (contagem: T, nome: string) => void;
  aoFechar: () => void;
}) {
  const aviso = useAviso();
  const [produto, setProduto] = useState<{ id: number; rotulo: string } | null>(null);
  const [local, setLocal] = useState<number | null>(locais.length === 1 ? locais[0].id : null);
  const [ocupado, setOcupado] = useState(false);

  async function incluir() {
    if (!produto) return;
    setOcupado(true);
    try {
      const r = await incluirNaContagem<T>(idInventario, produto.id, local);
      aoIncluir(r, produto.rotulo);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível incluir o produto");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Modal
      titulo="Incluir produto achado"
      descricao="Para o que está na prateleira e não apareceu na lista desta contagem."
      aoFechar={aoFechar}
      largura="520px"
      rodape={
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className="btn btn-secundario" onClick={aoFechar}>
            Cancelar
          </button>
          <button
            type="button"
            className="btn btn-primario"
            disabled={!produto || (locais.length > 1 && !local) || ocupado}
            aria-busy={ocupado}
            onClick={() => void incluir()}
          >
            {ocupado ? "…" : "Incluir na contagem"}
          </button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <Campo rotulo="Produto">
          <BuscaCadastro
            fonte={PRODUTOS}
            selecionado={produto}
            aoEscolher={(item: ItemBusca | null) =>
              setProduto(item ? { id: item.id, rotulo: rotuloDe(item) } : null)
            }
          />
        </Campo>
        {locais.length > 1 && (
          <Campo rotulo="Onde foi achado" dica="a prateleira em que você está contando">
            <select
              className="campo"
              value={local ?? ""}
              onChange={(e) => setLocal(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">escolha…</option>
              {locais.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.nome}
                </option>
              ))}
            </select>
          </Campo>
        )}
        <p className="text-[13px] text-suave">
          ⚠️ O produto <b>mora aqui</b>, ou só foi guardado no lugar errado? Se estava fora do
          lugar, devolva-o e conte onde ele mora: contado aqui, ele vira sobra aqui e falta lá.
        </p>
      </div>
    </Modal>
  );
}
