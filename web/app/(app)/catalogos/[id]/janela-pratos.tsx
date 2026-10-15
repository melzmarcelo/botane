"use client";

/**
 * Pôr VÁRIOS pratos numa seção de uma vez.
 *
 * 🔑 **Reforma de 15/10/2026.** A janela antiga punha um produto por clique, sem
 * marcar o que já tinha entrado — montar uma seção de quinze pratos era quinze
 * "pôr" com a lista parada, e a única pista do que já estava lá era o erro de
 * repetido. Agora se MARCA e se põe tudo junto; o que já está na seção aparece
 * travado, com "já está aqui".
 * ⚠️ Uma chamada por produto, na ordem marcada: a rota de vincular é a que
 * confere ativo, PDV e repetido (regra 4), e cada prato entra no FIM da lista.
 * Um que falhe não derruba os outros — a frase final conta os dois lados.
 */

import { useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Modal } from "@/components/ui";
import { urlArquivo } from "@/lib/api";
import * as cat from "@/lib/catalogos";

type Props = {
  idCategoria: number;
  idSubcategoria: number | null;
  onde: string;
  /** Os produtos que JÁ estão nesta lista — aparecem travados. */
  jaEstao: Set<number>;
  aoFechar: () => void;
  aoPor: () => Promise<void>;
};

export default function JanelaPratos({ idCategoria, idSubcategoria, onde, jaEstao, aoFechar, aoPor }: Props) {
  const aviso = useAviso();
  const [busca, setBusca] = useState("");
  const [achados, setAchados] = useState<cat.ProdutoDisponivel[]>([]);
  const [procurando, setProcurando] = useState(true);
  /** Na ordem em que foram marcados — é a ordem em que entram. */
  const [marcados, setMarcados] = useState<cat.ProdutoDisponivel[]>([]);
  const [pondo, setPondo] = useState(false);

  useEffect(() => {
    let valeu = true;
    setProcurando(true);
    // ⚠️ Espera antes de consultar: a resposta do "c" pode chegar depois da do
    // "café" e mandar na tela.
    const t = setTimeout(() => {
      cat.produtosDisponiveis(busca)
        .then((r) => valeu && setAchados(r))
        .catch(() => valeu && setAchados([]))
        .finally(() => valeu && setProcurando(false));
    }, 300);
    return () => {
      valeu = false;
      clearTimeout(t);
    };
  }, [busca]);

  const marcado = (id: number) => marcados.some((m) => m.id === id);
  const alternar = (p: cat.ProdutoDisponivel) =>
    setMarcados((x) => (x.some((m) => m.id === p.id) ? x.filter((m) => m.id !== p.id) : [...x, p]));

  async function por() {
    setPondo(true);
    const falhas: string[] = [];
    let foram = 0;
    for (const p of marcados) {
      try {
        await cat.vincularProduto(idCategoria, { id_produto: p.id, id_subcategoria: idSubcategoria });
        foram += 1;
      } catch (e) {
        falhas.push(`${p.nome}: ${e instanceof Error ? e.message : "falhou"}`);
      }
    }
    await aoPor();
    setPondo(false);
    if (falhas.length) {
      aviso.erro(`${foram} entraram; ${falhas.length} não: ${falhas.join(" · ")}`);
      setMarcados((x) => x.filter((m) => falhas.some((f) => f.startsWith(`${m.nome}:`))));
    } else {
      aviso.sucesso(foram === 1 ? "1 prato entrou no cardápio." : `${foram} pratos entraram no cardápio.`);
      aoFechar();
    }
  }

  return (
    <Modal
      titulo="Pôr pratos"
      descricao={`Entrando em ${onde}. Marque quantos quiser; eles entram no fim da lista.`}
      aoFechar={aoFechar}
      rodape={
        <div className="flex items-center justify-end gap-2">
          <button type="button" className="btn btn-secundario" onClick={aoFechar}>Cancelar</button>
          <button type="button" className="btn btn-primario" aria-busy={pondo}
                  disabled={pondo || marcados.length === 0} onClick={() => void por()}>
            {pondo ? "Pondo…" : marcados.length === 0 ? "Pôr pratos"
              : marcados.length === 1 ? "Pôr 1 prato" : `Pôr ${marcados.length} pratos`}
          </button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <Campo rotulo="Procurar" dica="Só produtos ativos e vendidos no PDV aparecem aqui.">
          <input id="busca-produto" className="campo" autoFocus placeholder="nome ou código"
                 value={busca} onChange={(e) => setBusca(e.target.value)} />
        </Campo>
        {procurando ? (
          <p className="text-[13.5px] text-suave">Procurando…</p>
        ) : achados.length === 0 ? (
          <p className="text-[13.5px] text-suave">
            Nenhum produto encontrado. ⚠️ O cardápio mostra só o que está no balcão: o produto
            precisa estar <b>ativo</b> e ir ao <b>PDV</b>.
          </p>
        ) : (
          <ul className="lista-rolante flex flex-col gap-px bg-linha text-[14.5px]">
            {achados.map((p) => {
              const esta = jaEstao.has(p.id);
              return (
                <li key={p.id} className="bg-superficie">
                  <label className={`flex items-center gap-3 py-2 ${esta ? "opacity-60" : "cursor-pointer"}`}>
                    <input type="checkbox" disabled={esta} checked={esta || marcado(p.id)}
                           onChange={() => alternar(p)} aria-label={p.nome} />
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded border border-linha bg-superficie2">
                      {p.foto_url && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={urlArquivo(p.foto_url) ?? undefined} alt="" className="h-full w-full object-cover" />
                      )}
                    </span>
                    <span className="min-w-0 flex-1 truncate">{p.nome}</span>
                    <span className="mono shrink-0 text-[12.5px] text-suave">
                      {esta ? "já está aqui" : p.codigo}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Modal>
  );
}
