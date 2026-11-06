"use client";

import { useState } from "react";

import {
  type Bloco, INDICADORES, type IdBloco, type IdIndicador, LARGURAS, type Largura, type LayoutInicio, NOMES,
} from "./layout";

/**
 * 🔑 O modo "Personalizar" do Início (pedido do dono, 06/11/2026). Cada quadro ganha uma moldura
 * com o puxador (arrastar), as setas (o mesmo sem mouse, e no celular), a largura e "Ocultar". Os
 * ocultos ficam numa bandeja para voltar. Nada grava antes de "Salvar".
 * ⚠️ Enquanto edita, o conteúdo do quadro NÃO responde a clique (`pointer-events-none`): cada número
 * do Início é um link, e arrastar um quadro não pode virar navegação.
 */

export function BarraDePersonalizar({
  layout, salvando, aoSalvar, aoCancelar, aoRestaurar, aoMostrar, disponiveis,
}: {
  layout: LayoutInicio;
  salvando: boolean;
  aoSalvar: () => void;
  aoCancelar: () => void;
  aoRestaurar: () => void;
  aoMostrar: (id: IdBloco) => void;
  /** Os quadros que têm dado para ESTA pessoa — o resto nem aparece na bandeja. */
  disponiveis: Set<IdBloco>;
}) {
  const ocultos = layout.blocos.filter((b) => b.oculto && disponiveis.has(b.id));
  return (
    <div data-personalizar className="sticky top-2 z-20 rounded-xl border border-erva bg-superficie p-4 shadow-lg">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-bold">Personalizar a tela inicial</p>
          <p className="text-[13px] text-suave">
            Arraste os quadros pelo puxador ou use as setas; escolha a largura e oculte o que não usa.
            Vale só para você, em qualquer aparelho.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn btn-terciario" onClick={aoRestaurar} disabled={salvando}>
            Restaurar o padrão
          </button>
          <button type="button" className="btn btn-secundario" onClick={aoCancelar} disabled={salvando}>
            Cancelar
          </button>
          <button type="button" id="inicio-salvar-layout" className="btn btn-primario" onClick={aoSalvar}
                  disabled={salvando} aria-busy={salvando}>
            {salvando ? "Salvando…" : "Salvar"}
          </button>
        </div>
      </div>
      {ocultos.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-linha pt-3" data-ocultos>
          <span className="text-[13px] text-suave">Ocultos:</span>
          {ocultos.map((b) => (
            <button key={b.id} type="button" data-mostrar={b.id}
                    className="rounded-full border border-linha2 px-3 py-1 text-[13px] hover:border-erva hover:text-erva"
                    onClick={() => aoMostrar(b.id)}>
              + {NOMES[b.id]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function MolduraDoBloco({
  bloco, primeiro, ultimo, arrastando, aoMover, aoLargura, aoOcultar, aoArrastar, aoSoltar,
  indicadores, aoIndicadores, children,
}: {
  bloco: Bloco;
  primeiro: boolean;
  ultimo: boolean;
  arrastando: IdBloco | null;
  aoMover: (passo: -1 | 1) => void;
  aoLargura: (l: Largura) => void;
  aoOcultar: () => void;
  aoArrastar: (id: IdBloco | null) => void;
  aoSoltar: (sobre: IdBloco) => void;
  /** Só no quadro "hoje": os indicadores da faixa. */
  indicadores?: { disponiveis: IdIndicador[]; ocultos: IdIndicador[] };
  aoIndicadores?: (ocultos: IdIndicador[]) => void;
  children: React.ReactNode;
}) {
  const [sobre, setSobre] = useState(false);
  return (
    <div
      data-moldura={bloco.id}
      onDragOver={(e) => {
        if (!arrastando || arrastando === bloco.id) return;
        e.preventDefault();
        setSobre(true);
      }}
      onDragLeave={() => setSobre(false)}
      onDrop={(e) => {
        e.preventDefault();
        setSobre(false);
        aoSoltar(bloco.id);
      }}
      className={`rounded-xl border-2 border-dashed p-2 transition-colors ${
        sobre ? "border-erva bg-erva-claro" : arrastando === bloco.id ? "border-linha2 opacity-50" : "border-linha2"}`}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2 px-1">
        <span
          draggable
          onDragStart={(e) => {
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/plain", bloco.id);
            aoArrastar(bloco.id);
          }}
          onDragEnd={() => aoArrastar(null)}
          className="cursor-grab select-none rounded px-1 text-[18px] leading-none text-suave active:cursor-grabbing"
          title="arraste para mudar de lugar"
          aria-hidden
        >⠿</span>
        <span className="mr-auto text-[13.5px] font-semibold">{NOMES[bloco.id]}</span>
        <button type="button" className="link-acao px-1 text-[15px]" aria-label={`subir ${NOMES[bloco.id]}`}
                data-mover="-1" disabled={primeiro} onClick={() => aoMover(-1)}>←</button>
        <button type="button" className="link-acao px-1 text-[15px]" aria-label={`descer ${NOMES[bloco.id]}`}
                data-mover="1" disabled={ultimo} onClick={() => aoMover(1)}>→</button>
        <span className="inline-flex overflow-hidden rounded-md border border-linha2" role="group" aria-label="largura">
          {LARGURAS.map((l) => (
            <button key={l.valor} type="button" data-largura={l.valor} aria-pressed={bloco.largura === l.valor}
                    className={`px-2 py-0.5 text-[12.5px] ${bloco.largura === l.valor ? "bg-erva text-white" : "hover:bg-superficie2"}`}
                    onClick={() => aoLargura(l.valor)}>{l.nome}</button>
          ))}
        </span>
        <button type="button" className="link-acao text-[13px]" data-ocultar={bloco.id} onClick={aoOcultar}>
          Ocultar
        </button>
      </div>
      {indicadores && aoIndicadores && (
        <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 px-1 text-[13px]" data-indicadores>
          {INDICADORES.filter((i) => indicadores.disponiveis.includes(i.id)).map((i) => (
            <label key={i.id} className="inline-flex items-center gap-1.5">
              <input type="checkbox" className="h-4 w-4 accent-erva" data-indicador={i.id}
                     checked={!indicadores.ocultos.includes(i.id)}
                     onChange={(e) => aoIndicadores(e.target.checked
                       ? indicadores.ocultos.filter((x) => x !== i.id)
                       : [...indicadores.ocultos, i.id])} />
              {i.nome}
            </label>
          ))}
        </div>
      )}
      <div className="pointer-events-none select-none">{children}</div>
    </div>
  );
}
