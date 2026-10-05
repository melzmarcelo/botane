"use client";

import { NOME_SISTEMA, useMarca } from "@/lib/marca";

/**
 * O cabeçalho das telas de FORA do sistema (entrar, esqueci e redefinir a
 * senha): a logo e o nome da casa, do cadastro da empresa.
 *
 * ⚠️ **A altura é reservada antes de a marca chegar** (`min-h`): num navegador
 * que nunca abriu o sistema o nome leva um instante, e sem a reserva o
 * formulário pularia para baixo com o cursor já no campo de e-mail.
 */
export default function MarcaDeEntrada({ grande = false }: { grande?: boolean }) {
  const marca = useMarca();

  if (!grande) return <p className="rotulo min-h-[1em]">{marca?.nome ?? ""}</p>;

  return (
    <div>
      <div className="flex min-h-[64px] items-center gap-3.5">
        {marca?.logo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={marca.logo} alt="" className="h-16 w-16 shrink-0 rounded-xl object-contain" />
        ) : null}
        <h1 className="min-w-0 break-words text-[34px] font-extrabold leading-[1.02] tracking-[-0.03em]">
          {marca?.nome ?? ""}
        </h1>
      </div>
      {/* O que é a porta: o sistema inteiro, e não um módulo dele. */}
      <p className="rotulo mt-3">{NOME_SISTEMA}</p>
    </div>
  );
}
