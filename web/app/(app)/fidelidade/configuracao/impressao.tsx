"use client";

import { useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Campo } from "@/components/ui";
import { baixarQrCodes, type FidelidadeConfig, type ImpressaoQr } from "@/lib/fidelidade";

/**
 * A impressão dos QR codes de check-in.
 *
 * 🔑 **Pedido do dono (24/09/2026):** *"a impressão do QR code, onde podemos escolher a
 * quantidade que vamos imprimir e o tamanho e se tem mais alguma informação, para
 * ocupar bem o espaço do PDF."* Os três tamanhos enchem a folha A4: grande (1 por
 * folha), médio (4) e pequeno (12). A numeração ("Mesa 7") é só impressa.
 */
const TAMANHOS: { v: ImpressaoQr["tamanho"]; r: string; d: string }[] = [
  { v: "G", r: "Grande", d: "1 por folha — caixa, porta" },
  { v: "M", r: "Médio", d: "4 por folha — display de mesa" },
  { v: "P", r: "Pequeno", d: "12 por folha — adesivo" },
];

export default function ImpressaoDosQrCodes({ cfg }: { cfg: FidelidadeConfig }) {
  const aviso = useAviso();
  const [p, setP] = useState<ImpressaoQr>({
    quantidade: 4,
    tamanho: "M",
    titulo: "Faça seu check-in",
    chamada: `A cada ${cfg.visitas} visitas: ${cfg.premio}`,
    extra: "",
    numerar: true,
    primeira_mesa: 1,
  });
  const [ocupado, setOcupado] = useState(false);
  const mudar = <K extends keyof ImpressaoQr>(k: K, v: ImpressaoQr[K]) => setP({ ...p, [k]: v });
  const porFolha = { G: 1, M: 4, P: 12 }[p.tamanho];

  async function baixar() {
    setOcupado(true);
    try {
      await baixarQrCodes(p);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gerar o PDF");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 border-t border-linha pt-4">
      <h3 className="text-[15px] font-semibold">Imprimir QR codes</h3>
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
        <Campo rotulo="Quantidade"
               dica={`${Math.ceil(p.quantidade / porFolha)} folha(s)`}>
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
               placeholder="Ex.: válido de segunda a sexta · mostre o código do prêmio no caixa"
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
        <button className="btn btn-primario ml-auto" onClick={() => void baixar()}
                aria-busy={ocupado} disabled={ocupado}>
          {ocupado ? "Gerando…" : "Baixar PDF"}
        </button>
      </div>
    </div>
  );
}
