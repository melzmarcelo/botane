"use client";

import { useRef, useState } from "react";

import type { Conjunto, Mesa } from "@/lib/salao";

/**
 * A planta do salão: as mesas desenhadas onde estão.
 *
 * 🔑 **Segunda entrega do estudo `docs/salao-estudo.md` (07/10/2026).** Só havia
 * a tabela: para saber quais mesas encostam era preciso conhecer a casa de
 * cabeça, e quem cadastrava a junta errava o par. `pos_x`/`pos_y` existiam no
 * banco desde a 069 e ninguém usava.
 *
 * 🔑 **Arrastar é RASCUNHO; quem grava é o "Salvar planta".** A mesma regra do
 * painel da mesa: nada vale antes do botão, e o Desfazer devolve tudo ao lugar.
 * Um PUT a cada soltar do mouse seria o "grava ao sair do campo" de volta.
 *
 * ⚠️ **Mesa sem posição é arrumada em fileiras**, abaixo das já posicionadas — o
 * salão montado em lote aparece inteiro na primeira vez, em vez de trinta mesas
 * empilhadas no canto. O Salvar grava TODAS as deste salão, inclusive as
 * arrumadas: senão a fileira mudaria de lugar a cada mesa que alguém fixasse.
 *
 * ⚠️ **Clique abre, arrasto move** — o que separa os dois é a distância
 * (`FOLGA_DO_CLIQUE`), não o tempo: quem segura o dedo parado está escolhendo.
 * ⚠️ **Setas movem a mesa em foco** de um passo da grade: arrastar não pode ser o
 * único jeito (teclado, leitor de tela, mão que treme).
 * ⚠️ **`touch-action: none` só NA MESA**: o dedo na mesa arrasta, o dedo no
 * fundo rola a planta — no celular ela é mais larga que a tela.
 *
 * ⚠️ **É desenho, não regra**: a disponibilidade não lê formato nem posição. A
 * linha liga as mesas de cada CONJUNTO já cadastrado (migração 109).
 *
 * 🔑 **Marcar para um conjunto novo**: com `aoMarcar`, clicar numa mesa a marca
 * em vez de abrir — é o "+ conjunto" de `conjuntos.tsx`. ⚠️ Nesse modo a mesa não
 * se arrasta: marcar e mover no mesmo gesto faria um escorregão do dedo mudar a
 * planta sem ninguém querer.
 */

const GRADE = 30;
const LARGURA = 780;
const ALTURA_MINIMA = 420;
const FOLGA_DO_CLIQUE = 5;
/** O teto do banco (`ck_mesa_posicao`). */
const POSICAO_MAXIMA = 4000;

type Ponto = { x: number; y: number };

/** Largura e altura do desenho: cresce com os lugares, e o formato dá a proporção. */
export function tamanhoDaMesa(m: Pick<Mesa, "lugares" | "formato">): [number, number] {
  const base = 52 + Math.min(m.lugares, 10) * 4;
  return m.formato === "RETANGULAR" ? [base + 38, base - 6] : [base, base];
}

const naGrade = (n: number) => Math.round(n / GRADE) * GRADE;

export default function PlantaDoSalao({
  mesas,
  conjuntos,
  idAberta,
  salaoAtivo,
  podeEditar,
  ocupado,
  marcadas,
  aoMarcar,
  aoAbrir,
  aoSalvar,
}: {
  mesas: Mesa[];
  conjuntos: Conjunto[];
  /** Com `aoMarcar`, a planta está escolhendo mesas para um conjunto novo. */
  marcadas?: number[];
  aoMarcar?: (id: number) => void;
  idAberta: number | null;
  salaoAtivo: boolean;
  podeEditar: boolean;
  ocupado: boolean;
  aoAbrir: (id: number) => void;
  /** Devolve se gravou — só então o rascunho das posições é descartado. */
  aoSalvar: (posicoes: { id: number; pos_x: number; pos_y: number }[]) => Promise<boolean>;
}) {
  const [mexidas, setMexidas] = useState<Record<number, Ponto>>({});
  // O arrasto em curso: não é estado de tela, é conta entre dois eventos.
  const arrasto = useRef<{ id: number; dx: number; dy: number; x0: number; y0: number;
                           moveu: boolean } | null>(null);

  // Onde cada mesa aparece: o que foi mexido, o que está gravado, ou a fileira.
  const gravadas = mesas.filter((m) => m.pos_x !== null && m.pos_y !== null);
  const base = gravadas.length
    ? naGrade(Math.max(...gravadas.map((m) => (m.pos_y ?? 0) + tamanhoDaMesa(m)[1])) + GRADE * 2)
    : GRADE;
  const semLugar = mesas.filter((m) => m.pos_x === null || m.pos_y === null);
  const lugarDe = (m: Mesa): Ponto => {
    if (mexidas[m.id]) return mexidas[m.id];
    if (m.pos_x !== null && m.pos_y !== null) return { x: m.pos_x, y: m.pos_y };
    const i = semLugar.findIndex((x) => x.id === m.id);
    return { x: GRADE + (i % 5) * 150, y: base + Math.floor(i / 5) * 120 };
  };

  const lugares = new Map(mesas.map((m) => [m.id, lugarDe(m)]));
  const altura = Math.max(
    ALTURA_MINIMA,
    ...mesas.map((m) => (lugares.get(m.id)?.y ?? 0) + tamanhoDaMesa(m)[1] + GRADE * 2),
  );
  const mexido = Object.keys(mexidas).length > 0;

  function mover(m: Mesa, x: number, y: number) {
    const [w] = tamanhoDaMesa(m);
    const novo = {
      x: Math.min(Math.max(0, naGrade(x)), naGrade(LARGURA - w - GRADE / 2)),
      y: Math.min(Math.max(0, naGrade(y)), POSICAO_MAXIMA),
    };
    const atual = lugares.get(m.id);
    if (atual && atual.x === novo.x && atual.y === novo.y) return;
    setMexidas((antes) => ({ ...antes, [m.id]: novo }));
  }

  async function salvar() {
    const deu = await aoSalvar(
      mesas.map((m) => {
        const p = lugares.get(m.id) ?? { x: 0, y: 0 };
        return { id: m.id, pos_x: p.x, pos_y: p.y };
      }),
    );
    if (deu) setMexidas({});
  }

  // Os conjuntos já cadastrados: uma linha ligando as mesas DESTE salão, da
  // esquerda para a direita. (Mesa de outro salão não tem onde aparecer aqui.)
  const centro = (m: Mesa) => {
    const [p, [w, h]] = [lugares.get(m.id)!, tamanhoDaMesa(m)];
    return { x: p.x + w / 2, y: p.y + h / 2 };
  };
  const juntas = conjuntos.flatMap((c) => {
    const pontos = mesas
      .filter((m) => c.mesas.some((x) => x.id === m.id))
      .map(centro)
      .sort((a, b) => a.x - b.x || a.y - b.y);
    return pontos.slice(1).map((p, i) => ({
      chave: `${c.id}-${i}`, x1: pontos[i].x, y1: pontos[i].y, x2: p.x, y2: p.y,
    }));
  });

  const marcando = !!aoMarcar;
  const podeMover = podeEditar && !ocupado && !marcando;

  return (
    <div className="flex flex-col gap-2.5">
      <div className="overflow-auto rounded-xl border border-linha2 bg-superficie2"
           role="group" aria-label="planta do salão">
        <div
          className="relative"
          style={{
            width: LARGURA,
            height: altura,
            backgroundImage:
              "radial-gradient(circle, var(--color-linha2) 1px, transparent 1.5px)",
            backgroundSize: `${GRADE}px ${GRADE}px`,
            backgroundPosition: `${GRADE / 2}px ${GRADE / 2}px`,
          }}
        >
          <svg className="pointer-events-none absolute inset-0" width={LARGURA} height={altura}
               aria-hidden="true">
            {juntas.map((j) => (
              <line key={j.chave} x1={j.x1} y1={j.y1} x2={j.x2} y2={j.y2}
                    stroke="var(--color-erva)" strokeWidth={2} strokeDasharray="5 4" />
            ))}
          </svg>

          {mesas.map((m) => {
            const p = lugares.get(m.id)!;
            const [w, h] = tamanhoDaMesa(m);
            const ligada = m.ativo && salaoAtivo;
            const aberta = marcando ? (marcadas ?? []).includes(m.id) : idAberta === m.id;
            return (
              <button
                key={m.id}
                type="button"
                aria-label={`mesa ${m.nome} na planta`}
                aria-pressed={aberta}
                data-x={p.x}
                data-y={p.y}
                className={`absolute flex select-none flex-col items-center justify-center border-[1.5px] leading-tight ${
                  m.formato === "REDONDA" ? "rounded-full" : "rounded-[10px]"
                } ${aberta ? "border-erva bg-erva-claro text-erva" : "border-linha2 bg-superficie"} ${
                  ligada ? "" : "border-dashed text-suave"
                } ${podeMover ? "cursor-grab active:cursor-grabbing" : "cursor-pointer"} ${
                  mexidas[m.id] ? "shadow-md" : ""
                }`}
                style={{ left: p.x, top: p.y, width: w, height: h,
                         touchAction: podeMover ? "none" : undefined }}
                onPointerDown={(e) => {
                  if (!podeMover || e.button !== 0) return;
                  e.currentTarget.setPointerCapture(e.pointerId);
                  arrasto.current = { id: m.id, dx: e.clientX - p.x, dy: e.clientY - p.y,
                                      x0: e.clientX, y0: e.clientY, moveu: false };
                }}
                onPointerMove={(e) => {
                  const a = arrasto.current;
                  if (!a || a.id !== m.id) return;
                  if (!a.moveu && Math.hypot(e.clientX - a.x0, e.clientY - a.y0) < FOLGA_DO_CLIQUE) {
                    return;
                  }
                  a.moveu = true;
                  mover(m, e.clientX - a.dx, e.clientY - a.dy);
                }}
                onPointerUp={() => {
                  const a = arrasto.current;
                  arrasto.current = null;
                  // Soltou sem sair do lugar: foi um clique. (Sem permissão de
                  // editar não há arrasto, e o `onClick` abaixo é quem abre.)
                  if (a && !a.moveu) aoAbrir(m.id);
                }}
                onPointerCancel={() => { arrasto.current = null; }}
                onClick={() => {
                  if (aoMarcar) aoMarcar(m.id);
                  else if (!podeMover) aoAbrir(m.id);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    if (aoMarcar) aoMarcar(m.id);
                    else aoAbrir(m.id);
                    return;
                  }
                  const passo: Record<string, [number, number]> = {
                    ArrowLeft: [-GRADE, 0], ArrowRight: [GRADE, 0],
                    ArrowUp: [0, -GRADE], ArrowDown: [0, GRADE],
                  };
                  const d = passo[e.key];
                  if (!d || !podeMover) return;
                  e.preventDefault();
                  mover(m, p.x + d[0], p.y + d[1]);
                }}
              >
                <b className="mono text-[13.5px]">{m.nome}</b>
                <span className="mono text-[11px] opacity-80">
                  {m.lugares === m.capacidade_max ? m.lugares : `${m.lugares}–${m.capacidade_max}`}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[12.5px] text-suave">
          {marcando ? (
            "Clique nas mesas do conjunto novo. "
          ) : (
            <>
              {podeEditar ? "Arraste para posicionar (ou use as setas). " : ""}
              Clique numa mesa para abrir.{" "}
            </>
          )}
          A linha liga as mesas de um conjunto; tracejada é mesa desligada.
        </p>
        {podeEditar && (
          <span className="flex items-center gap-2">
            {mexido && <span className="text-[12.5px] text-alerta">posições não salvas</span>}
            <button type="button" className="btn btn-secundario" disabled={ocupado || !mexido}
                    onClick={() => setMexidas({})}>
              Desfazer
            </button>
            <button type="button" className="btn btn-primario" aria-busy={ocupado}
                    disabled={ocupado || !mexido} onClick={() => void salvar()}>
              Salvar planta
            </button>
          </span>
        )}
      </div>
    </div>
  );
}
