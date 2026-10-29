"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * As partes do Patrimônio como ABAS, igual ao painel do CMV (auditoria de 29/10/2026).
 * Conferência e Valor eram botões no meio de "Novo bem" e "Imprimir", e não pareciam o que são:
 * outra vista do mesmo módulo. Cada aba é uma página; esta faixa vai no topo das três.
 * ⚠️ Os ids (`patrimonio-conferencias`, `patrimonio-valor`) são os dos botões de antes — a
 * bateria do navegador clica neles.
 */
const ABAS = [
  { href: "/patrimonio", texto: "Bens", id: "patrimonio-bens" },
  { href: "/patrimonio/conferencias", texto: "Conferência", id: "patrimonio-conferencias" },
  { href: "/patrimonio/valor", texto: "Valor", id: "patrimonio-valor" },
] as const;

export default function AbasDoPatrimonio() {
  const caminho = usePathname();
  return (
    <nav className="flex flex-wrap gap-1 border-b border-linha" aria-label="Partes do patrimônio">
      {ABAS.map((a) => {
        const ativa = a.href === "/patrimonio" ? caminho === a.href : caminho.startsWith(a.href);
        return (
          <Link
            key={a.href}
            href={a.href}
            id={a.id}
            aria-current={ativa ? "page" : undefined}
            className={`-mb-px flex min-h-[44px] items-center border-b-2 px-3 py-2 text-[14.5px] no-underline ${
              ativa
                ? "border-erva font-semibold text-erva"
                : "border-transparent text-suave hover:text-tinta"
            }`}
          >
            {a.texto}
          </Link>
        );
      })}
    </nav>
  );
}
