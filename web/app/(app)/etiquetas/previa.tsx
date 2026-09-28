"use client";

import { Cartao } from "@/components/ui";
import {
  dataHora, rotuloConservacao, rotuloEvento, type Conservacao, type Evento, type Sugestao,
} from "@/lib/etiquetas";

/**
 * Como a etiqueta vai sair — a pessoa confere a validade ANTES de gastar papel.
 *
 * ⚠️ A prévia repete as regras do servidor (manual > regra > cadastro, e o teto do
 * fabricante) só para MOSTRAR; quem grava é o servidor.
 */
export default function Previa({
  sug, evento, conservacao, venceManual, fabricante, responsavel, lote,
}: {
  sug: Sugestao | null;
  evento: Evento;
  conservacao: Conservacao | null;
  venceManual: string;
  fabricante: string;
  responsavel: string;
  lote: string | null;
}) {
  let vence = venceManual ? new Date(venceManual).toISOString() : sug?.vence_em ?? null;
  let deOnde = venceManual ? "informada" : sug?.origem === "cadastro"
    ? "validade do cadastro" : sug?.origem === "regra" ? "regra do produto" : null;
  if (fabricante) {
    const teto = new Date(`${fabricante}T23:59:00`).toISOString();
    if (!vence || teto < vence) {
      vence = teto;
      deOnde = "limitada pelo fabricante";
    }
  }

  return (
    <Cartao titulo="Prévia">
      {!sug ? (
        <p className="text-[13px] text-suave">Escolha o produto para ver a etiqueta.</p>
      ) : (
        <div className="rounded-[8px] border-2 border-dashed border-[var(--color-linha)] p-3">
          <b className="block text-[15px] uppercase leading-tight">{sug.produto.nome}</b>
          <p className="mt-1 text-[12px] uppercase text-suave">
            {rotuloEvento(evento)} agora · {conservacao ? rotuloConservacao(conservacao) : "—"}
          </p>
          <p className="mt-2 text-[11px] uppercase text-suave">Validade</p>
          <b className={`mono block text-[22px] leading-none ${vence ? "" : "text-[var(--color-alerta)]"}`}>
            {vence ? dataHora(vence) : "informe"}
          </b>
          {deOnde && <p className="mt-1 text-[11px] text-suave">{deOnde}</p>}
          <p className="mt-2 text-[12px]">Resp.: {responsavel}</p>
          {lote && <p className="text-[12px]">Lote: {lote}</p>}
          {sug.alergenos && <p className="mt-1 text-[12px] font-semibold">Alérgenos: {sug.alergenos}</p>}
        </div>
      )}
    </Cartao>
  );
}
