"use client";

import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Modal } from "@/components/ui";
import { descartar, motivosDePerda, numero, type Etiqueta } from "@/lib/etiquetas";

/**
 * Descartar pela etiqueta — a janela que o painel e a tela do QR dividem.
 *
 * 🔑 **Descartar é perda no estoque, com o valor**: é isto que transforma "jogamos fora"
 * em número. ⚠️ "Só tirar das ativas" existe para quando a perda já foi lançada por
 * outro caminho — lançar de novo seria perder duas vezes o mesmo pote.
 */
export default function Descarte({
  etiqueta,
  aoFechar,
  aoConcluir,
}: {
  etiqueta: Etiqueta;
  aoFechar: () => void;
  aoConcluir: (e: Etiqueta) => void;
}) {
  const aviso = useAviso();
  const [motivos, setMotivos] = useState<{ id: number; nome: string }[]>([]);
  const [idMotivo, setIdMotivo] = useState<number | null>(null);
  const [motivo, setMotivo] = useState("");
  const [quantidade, setQuantidade] = useState(etiqueta.quantidade ? numero(etiqueta.quantidade) : "");
  const [lancar, setLancar] = useState(true);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    motivosDePerda()
      .then((m) => {
        setMotivos(m);
        const venc = m.find((x) => /venc|validade/i.test(x.nome));
        if (venc && etiqueta.situacao === "VENCIDA") setIdMotivo(venc.id);
      })
      .catch(() => setMotivos([]));
  }, [etiqueta.situacao]);

  async function confirmar() {
    setOcupado(true);
    try {
      const q = quantidade.trim() ? Number(quantidade.replace(/\./g, "").replace(",", ".")) : null;
      const r = await descartar(etiqueta.id, {
        quantidade: q, id_motivo_perda: idMotivo, motivo: motivo || undefined, lancar_perda: lancar,
      });
      aviso.sucesso(r.message);
      aoConcluir(r);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível descartar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Modal
      titulo={`Descartar ${etiqueta.codigo}`}
      descricao={`${etiqueta.produto}${etiqueta.local ? ` · ${etiqueta.local}` : ""}`}
      aoFechar={aoFechar}
      largura="520px"
      rodape={
        <div className="flex justify-end gap-2">
          <button className="btn btn-secundario" onClick={aoFechar}>Voltar</button>
          <button className="btn btn-perigo" disabled={ocupado} aria-busy={ocupado}
                  onClick={() => void confirmar()}>
            {ocupado ? "…" : "Descartar"}
          </button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1" checked={lancar} onChange={(e) => setLancar(e.target.checked)} />
          <span className="text-[14px]">
            Lançar a perda no estoque
            <span className="block text-[13px] text-suave">
              Desmarque só se a perda já foi lançada por outro caminho.
            </span>
          </span>
        </label>
        {lancar && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo rotulo={`Quantidade${etiqueta.um ? ` (${etiqueta.um})` : ""}`}>
              <input className="campo mono" inputMode="decimal" value={quantidade}
                     onChange={(e) => setQuantidade(e.target.value)} />
            </Campo>
            <Campo rotulo="Motivo da perda">
              <select className="campo" value={idMotivo ?? ""}
                      onChange={(e) => setIdMotivo(e.target.value ? Number(e.target.value) : null)}>
                <option value="">—</option>
                {motivos.map((m) => <option key={m.id} value={m.id}>{m.nome}</option>)}
              </select>
            </Campo>
          </div>
        )}
        <Campo rotulo="Observação" opcional>
          <input className="campo" maxLength={200} value={motivo} placeholder="ex.: passou do ponto"
                 onChange={(e) => setMotivo(e.target.value)} />
        </Campo>
      </div>
    </Modal>
  );
}
