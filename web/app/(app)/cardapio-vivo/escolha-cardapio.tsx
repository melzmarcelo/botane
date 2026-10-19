"use client";

/**
 * Qual Cardápio Vivo medir (1.1.109): o principal vem marcado; os outros da loja (o do
 * catering, o da varanda…) aparecem para escolher. Com um só, nada aparece.
 * 🔑 Desde a 122 cada evento grava de qual Cardápio Vivo veio — é isso que permite separar.
 */

type Opcao = { id_catalogo: number; nome: string; principal: boolean };

export default function EscolhaCardapio({ opcoes, valor, aoMudar }: {
  opcoes: Opcao[]; valor: number | null; aoMudar: (id: number) => void;
}) {
  if (opcoes.length < 2) return null;
  return (
    <label className="flex flex-col gap-1"><span className="text-[12.5px] text-suave">Cardápio</span>
      <select id="escolha-cardapio" className="campo !w-auto" value={valor ?? ""}
              onChange={(e) => aoMudar(Number(e.target.value))}>
        {opcoes.map((o) => (
          <option key={o.id_catalogo} value={o.id_catalogo}>{o.nome}{o.principal ? " (principal)" : ""}</option>
        ))}
      </select></label>
  );
}
