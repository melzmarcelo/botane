"use client";

/**
 * O mapa mesa × hora: quantas sessões abriram o cardápio em cada mesa, em cada hora.
 * 🔑 Uma cor só (a erva da casa), do claro ao escuro: é magnitude, não identidade. O número
 * vai escrito na célula, e o `title` repete mesa, hora e contagem para quem passa o mouse.
 */

import { Cartao, Vazio } from "@/components/ui";
import type { PainelAtencao } from "@/lib/cardapio-vivo";

export default function Mapa({ mapa }: { mapa: PainelAtencao["mapa"] }) {
  if (!mapa.length) return <Cartao titulo="Mesa × hora"><Vazio>Nenhuma sessão de mesa no recorte.</Vazio></Cartao>;
  const horas = [...new Set(mapa.map((m) => m.hora))].sort((a, b) => a - b);
  const mesas = [...new Map(mapa.map((m) => [`${m.salao}|${m.mesa}`, m])).values()];
  const maior = Math.max(...mapa.map((m) => m.sessoes));
  const valor = (salao: string, mesa: string, hora: number) =>
    mapa.find((m) => m.salao === salao && m.mesa === mesa && m.hora === hora)?.sessoes ?? 0;

  return (
    <Cartao titulo="Mesa × hora" descricao="Sessões que abriram o cardápio. Mais escuro = mais sessões.">
      <div className="overflow-x-auto">
        <table className="text-[12.5px]" aria-label="Sessões por mesa e hora">
          <thead>
            <tr>
              <th className="pr-3 text-left font-medium text-suave">Mesa</th>
              {horas.map((h) => <th key={h} className="mono w-10 font-medium text-suave">{String(h).padStart(2, "0")}h</th>)}
            </tr>
          </thead>
          <tbody>
            {mesas.map((m) => (
              <tr key={`${m.salao}|${m.mesa}`}>
                <td className="whitespace-nowrap pr-3">{m.mesa} <span className="text-suave">· {m.salao}</span></td>
                {horas.map((h) => {
                  const n = valor(m.salao, m.mesa, h);
                  const forca = n ? 0.15 + 0.85 * (n / maior) : 0;
                  return (
                    <td key={h} className="p-[1px]">
                      <div title={`Mesa ${m.mesa} · ${h}h: ${n} sessão(ões)`}
                           className="mono flex h-8 w-10 items-center justify-center rounded-[4px]"
                           style={{ background: n ? `color-mix(in srgb, var(--color-erva) ${Math.round(forca * 100)}%, transparent)` : "var(--color-superficie2)",
                                    color: forca > 0.55 ? "var(--color-superficie)" : "var(--color-tinta)" }}>
                        {n || ""}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Cartao>
  );
}
