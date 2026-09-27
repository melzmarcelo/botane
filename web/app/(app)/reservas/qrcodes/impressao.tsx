"use client";

import { useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Modal } from "@/components/ui";
import { baixarQr, type ImpressaoQr, type QrDaCasa } from "@/lib/qrcodes";

/**
 * A impressão de um QR code, qualquer que seja o tipo.
 *
 * 🔑 **Pedido do dono (24/09/2026):** *"escolher a quantidade que vamos imprimir e o tamanho
 * e se tem mais alguma informação, para ocupar bem o espaço do PDF."* Os três tamanhos
 * enchem a A4: grande (1 por folha, para o caixa ou a porta), médio (4, display de mesa) e
 * pequeno (12, adesivo). Nasceu na Fidelidade e veio para cá em 27/09, quando os QR de
 * cardápio e de reserva chegaram.
 */
const TAMANHOS: { v: ImpressaoQr["tamanho"]; r: string; d: string }[] = [
  { v: "G", r: "Grande", d: "1 por folha — caixa, porta" },
  { v: "M", r: "Médio", d: "4 por folha — display de mesa" },
  { v: "P", r: "Pequeno", d: "12 por folha — adesivo" },
];

export default function ImpressaoDoQr({ qr, aoFechar }: { qr: QrDaCasa; aoFechar: () => void }) {
  const aviso = useAviso();
  const noCaixa = qr.tipo === "fidelidade" && qr.metodo === "CODIGO_CAIXA";
  const [p, setP] = useState<ImpressaoQr>({
    quantidade: noCaixa ? 1 : 4,
    tamanho: noCaixa ? "G" : "M",
    titulo: qr.titulo,
    chamada: qr.chamada,
    extra: noCaixa ? "Leia o QR code e peça o código ao atendente" : "",
    numerar: qr.tipo === "cardapio" || (qr.tipo === "fidelidade" && !noCaixa),
    primeira_mesa: 1,
  });
  const [ocupado, setOcupado] = useState(false);
  const mudar = <K extends keyof ImpressaoQr>(k: K, v: ImpressaoQr[K]) => setP({ ...p, [k]: v });
  const porFolha = { G: 1, M: 4, P: 12 }[p.tamanho];

  async function baixar() {
    setOcupado(true);
    try {
      await baixarQr(qr, p);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gerar o PDF");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Modal
      titulo={`Imprimir — ${qr.nome}`}
      descricao={`Fica bem ${qr.onde}.`}
      aoFechar={aoFechar}
      largura="640px"
      rodape={
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[13px] text-suave">
            {Math.ceil(p.quantidade / porFolha)} folha(s) A4
          </span>
          <div className="flex gap-2">
            <button type="button" className="btn btn-secundario" onClick={aoFechar}>
              Fechar
            </button>
            <button type="button" className="btn btn-primario" onClick={() => void baixar()}
                    aria-busy={ocupado} disabled={ocupado}>
              {ocupado ? "Gerando…" : "Baixar PDF"}
            </button>
          </div>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="tamanho">
          {TAMANHOS.map((t) => (
            <button
              key={t.v}
              type="button"
              role="radio"
              aria-checked={p.tamanho === t.v}
              onClick={() => mudar("tamanho", t.v)}
              className={`rounded-[10px] border p-3 text-left ${
                p.tamanho === t.v
                  ? "border-[var(--color-erva)] bg-[var(--color-erva-claro)]"
                  : "border-[var(--color-linha)] hover:border-[var(--color-erva)]"
              }`}
            >
              <b className="block text-[14px]">{t.r}</b>
              <span className="text-[12.5px] text-suave">{t.d}</span>
            </button>
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-[140px_1fr]">
          <Campo rotulo="Quantidade">
            <input className="campo mono" type="number" min={1} max={200} value={p.quantidade}
                   onChange={(e) => mudar("quantidade", Math.max(1, Number(e.target.value)))} />
          </Campo>
          <Campo rotulo="Título">
            <input className="campo" maxLength={60} value={p.titulo}
                   onChange={(e) => mudar("titulo", e.target.value)} />
          </Campo>
        </div>
        <Campo rotulo="Chamada" dica="Aparece em destaque, logo abaixo do QR code.">
          <input className="campo" maxLength={120} value={p.chamada}
                 onChange={(e) => mudar("chamada", e.target.value)} />
        </Campo>
        <Campo rotulo="Informação adicional" opcional>
          <input className="campo" maxLength={200} value={p.extra}
                 placeholder="Ex.: válido de segunda a sexta"
                 onChange={(e) => mudar("extra", e.target.value)} />
        </Campo>
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex items-center gap-2 pb-2">
            <input type="checkbox" checked={p.numerar}
                   onChange={(e) => mudar("numerar", e.target.checked)} />
            <span className="text-[14px]">Numerar as mesas</span>
          </label>
          {p.numerar && (
            <Campo rotulo="Começar na mesa">
              <input className="campo mono w-[110px]" type="number" min={1} max={999}
                     value={p.primeira_mesa}
                     onChange={(e) => mudar("primeira_mesa", Math.max(1, Number(e.target.value)))} />
            </Campo>
          )}
        </div>
      </div>
    </Modal>
  );
}
