"use client";

/**
 * As sugestões automáticas de destaque (Cardápio Vivo, fase 3): o sistema SUGERE, o gerente
 * APROVA (decisão do dono, 15/10/2026). Nada muda no cardápio sem o clique em "Aplicar".
 */

import { useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Cartao, Etiqueta, Vazio } from "@/components/ui";
import { TestesService, type SugestaoDestaque } from "@/lib/cardapio-vivo";

type Props = { de: string; ate: string; podeAplicar: boolean; aoAplicar: () => void };

export default function SugestoesDestaque({ de, ate, podeAplicar, aoAplicar }: Props) {
  const aviso = useAviso();
  const [lista, setLista] = useState<SugestaoDestaque[]>([]);
  const [marcadas, setMarcadas] = useState<Set<number>>(new Set());

  const carregar = () => TestesService.sugestoes(de, ate).then((l) => {
    setLista(l);
    setMarcadas(new Set());
  }).catch(() => setLista([]));
  useEffect(() => { void carregar(); }, [de, ate]); // eslint-disable-line react-hooks/exhaustive-deps

  async function aplicar() {
    try {
      const r = await TestesService.aplicarDestaques(
        lista.filter((s) => marcadas.has(s.id_item)).map((s) => ({ id_item: s.id_item, destaque: s.acao === "POR" })));
      aviso.sucesso(r.message);
      await carregar();
      aoAplicar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível aplicar.");
    }
  }

  return (
    <Cartao titulo="Sugestões de destaque"
            descricao="Pelo painel deste período e pelo objetivo de cada prato. Marque as que aprova — nada muda sem aplicar."
            acao={podeAplicar && lista.length > 0 ? (
              <button className="btn btn-primario" disabled={!marcadas.size} onClick={() => void aplicar()}>
                Aplicar {marcadas.size || ""}
              </button>) : undefined}>
      {lista.length === 0 ? <Vazio>Nenhuma sugestão de destaque para este período.</Vazio> : (
        <ul className="flex flex-col divide-y divide-linha text-[14px]">
          {lista.map((s) => (
            <li key={`${s.acao}${s.id_item}`} className="flex items-center gap-3 py-2">
              {podeAplicar && (
                <input type="checkbox" aria-label={`Aprovar ${s.nome}`} checked={marcadas.has(s.id_item)}
                       onChange={(e) => setMarcadas((m) => {
                         const n = new Set(m);
                         if (e.target.checked) n.add(s.id_item); else n.delete(s.id_item);
                         return n;
                       })} />
              )}
              <Etiqueta cor={s.acao === "POR" ? "erva" : "alerta"}>{s.acao === "POR" ? "pôr em destaque" : "tirar do destaque"}</Etiqueta>
              <span className="font-medium">{s.nome}</span>
              <span className="text-suave">— {s.motivo}</span>
            </li>
          ))}
        </ul>
      )}
    </Cartao>
  );
}
