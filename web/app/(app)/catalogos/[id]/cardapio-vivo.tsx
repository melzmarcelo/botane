"use client";

/**
 * O que o Cardápio Vivo (113) acrescentou à página do catálogo: as marcas de cada item
 * (destaque, esgotado) e quando cada seção aparece (dias, horário, dia especial).
 *
 * ⚠️ Arquivo à parte: a página do catálogo já passa de 800 linhas.
 */

import { useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Etiqueta } from "@/components/ui";
import { CardapioVivoService } from "@/lib/cardapio-vivo";
import type { ItemDoCatalogo, Secao, TipoDeSecao } from "@/lib/catalogos";

const DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];

export function MarcasDoItem({ item, podeEditar, aoMudar }: {
  item: ItemDoCatalogo; podeEditar: boolean; aoMudar: () => Promise<void>;
}) {
  const aviso = useAviso();
  async function alternar(campo: "destaque" | "esgotado") {
    try {
      const r = await CardapioVivoService.marcarItem(item.id, { [campo]: !item[campo] });
      await aoMudar();
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível marcar.");
    }
  }
  return (
    <>
      {item.tem_video && <Etiqueta cor="erva">vídeo</Etiqueta>}
      {!item.tem_video && !item.foto_url && <Etiqueta cor="alerta">sem foto e sem vídeo</Etiqueta>}
      {podeEditar ? (
        <>
          <button type="button" className="link-acao text-[13px]" aria-pressed={item.destaque}
                  onClick={() => void alternar("destaque")}>
            {item.destaque ? "★ em destaque" : "☆ destaque"}
          </button>
          <button type="button" className={`link-acao text-[13px] ${item.esgotado ? "link-acao-erro" : ""}`}
                  aria-pressed={item.esgotado} onClick={() => void alternar("esgotado")}>
            {item.esgotado ? "esgotado ✓" : "esgotado"}
          </button>
        </>
      ) : (
        <>
          {item.destaque && <Etiqueta cor="erva">destaque</Etiqueta>}
          {item.esgotado && <Etiqueta cor="alerta">esgotado</Etiqueta>}
        </>
      )}
    </>
  );
}

function resumo(s: Secao): string {
  const partes: string[] = [];
  if (s.dias?.length) partes.push(s.dias.map((d) => DIAS[d - 1]).join(", "));
  if (s.hora_de && s.hora_ate) partes.push(`${s.hora_de.slice(0, 5)}–${s.hora_ate.slice(0, 5)}`);
  if (s.horario_especial && s.dias?.length) partes.push("e dias especiais");
  return partes.length ? partes.join(" · ") : "sempre";
}

export function ExibicaoDaSecao({ tipo, secao, podeEditar, aoMudar }: {
  tipo: TipoDeSecao; secao: Secao; podeEditar: boolean; aoMudar: () => Promise<void>;
}) {
  const aviso = useAviso();
  const [aberto, setAberto] = useState(false);
  const [dias, setDias] = useState<number[]>(secao.dias ?? []);
  const [de, setDe] = useState(secao.hora_de?.slice(0, 5) ?? "");
  const [ate, setAte] = useState(secao.hora_ate?.slice(0, 5) ?? "");
  const [especial, setEspecial] = useState(secao.horario_especial);

  async function gravar() {
    try {
      const r = await CardapioVivoService.exibicaoSecao(tipo, secao.id, {
        dias: dias.length ? dias : null, hora_de: de || null, hora_ate: ate || null, horario_especial: especial,
      });
      await aoMudar();
      setAberto(false);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar.");
    }
  }

  return (
    <div className="text-[13px]">
      <span className="text-suave">No Cardápio Vivo: </span>
      <span className="font-medium">{resumo(secao)}</span>
      {podeEditar && !aberto && (
        <button type="button" className="link-acao ml-2" onClick={() => setAberto(true)}>mudar</button>
      )}
      {aberto && (
        <div className="mt-2 flex flex-col gap-2 rounded-lg border border-linha p-3">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Dias da semana">
            {DIAS.map((nome, n) => {
              const d = n + 1;
              return (
                <label key={d} className="flex items-center gap-1">
                  <input type="checkbox" checked={dias.includes(d)}
                         onChange={(e) => setDias((x) => (e.target.checked ? [...x, d] : x.filter((y) => y !== d)))} />
                  {nome}
                </label>
              );
            })}
            <span className="text-suave">(nenhum marcado = todos)</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            das <input type="time" className="campo mono !w-auto" value={de} onChange={(e) => setDe(e.target.value)} />
            às <input type="time" className="campo mono !w-auto" value={ate} onChange={(e) => setAte(e.target.value)} />
            <span className="text-suave">(vazio = o dia todo; pode virar a meia-noite)</span>
          </div>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={especial} onChange={(e) => setEspecial(e.target.checked)} />
            Aparece também nos dias de horário especial (feriados marcados nas Reservas)
          </label>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-secundario" onClick={() => setAberto(false)}>Cancelar</button>
            <button type="button" className="btn btn-primario" onClick={() => void gravar()}>Gravar</button>
          </div>
        </div>
      )}
    </div>
  );
}
