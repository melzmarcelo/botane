"use client";

/**
 * A barra de abas da ficha do bem — o mesmo desenho da ficha do produto
 * (`role="tablist"`, 44px de alvo, fio de 2px no ativo).
 * 🔑 **Bem novo só tem Dados do bem, Garantia e Preventiva**: manutenção e custo apontam
 * para um bem que ainda não existe.
 */
export type Aba = "dados" | "garantia" | "preventiva" | "manutencoes" | "custos" | "anexos";

export const ABAS: [Aba, string][] = [
  ["dados", "Dados do bem"], ["garantia", "Garantia"], ["preventiva", "Preventiva"],
  ["manutencoes", "Manutenções"], ["custos", "Custos"], ["anexos", "Fotos e documentos"],
];
/** As abas cujo conteúdo o Salvar grava. */
export const DO_FORMULARIO: Aba[] = ["dados", "garantia", "preventiva"];

export const ehAba = (v: string | null): v is Aba => ABAS.some(([a]) => a === v);

export default function AbasDaFicha({ aba, novo, aoTrocar, contagens = {} }: {
  aba: Aba; novo: boolean; aoTrocar: (a: Aba) => void; contagens?: Partial<Record<Aba, number>>;
}) {
  const abas = novo ? ABAS.filter(([a]) => DO_FORMULARIO.includes(a)) : ABAS;
  return (
    <div className="flex flex-wrap gap-2 border-b border-linha" role="tablist" aria-label="ficha do bem">
      {abas.map(([chave, texto]) => (
        <button key={chave} type="button" role="tab" id={`aba-${chave}`} aria-selected={aba === chave}
                onClick={() => aoTrocar(chave)}
                className={`-mb-px min-h-[44px] border-b-2 px-4 py-2.5 text-[14.5px] font-semibold ${
                  aba === chave ? "border-erva text-tinta" : "border-transparent text-suave hover:text-tinta"}`}>
          {texto}
          {!!contagens[chave] && (
            <span className="contador-grade ml-2 align-middle">{contagens[chave]}</span>
          )}
        </button>
      ))}
    </div>
  );
}
