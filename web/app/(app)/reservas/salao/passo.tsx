"use client";

/** Um número que se muda de um em um — sem campo para digitar errado. */
export default function Passo({
  rotulo,
  valor,
  minimo,
  maximo,
  desabilitado,
  aoMudar,
}: {
  rotulo: string;
  valor: number;
  minimo: number;
  maximo: number;
  desabilitado: boolean;
  aoMudar: (n: number) => void;
}) {
  return (
    <div className="flex items-center overflow-hidden rounded-[9px] border border-linha2">
      <button type="button" className="h-9 w-9 bg-superficie2 text-[17px] disabled:opacity-40"
              aria-label={`menos ${rotulo}`} disabled={desabilitado || valor <= minimo}
              onClick={() => aoMudar(valor - 1)}>
        −
      </button>
      <output className="mono min-w-[34px] flex-1 text-center" aria-label={rotulo}>{valor}</output>
      <button type="button" className="h-9 w-9 bg-superficie2 text-[17px] disabled:opacity-40"
              aria-label={`mais ${rotulo}`} disabled={desabilitado || valor >= maximo}
              onClick={() => aoMudar(valor + 1)}>
        +
      </button>
    </div>
  );
}
