"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useSessao } from "@/lib/sessao";

/**
 * As telas do dia a dia, a um toque — só no celular.
 *
 * 🔑 **Pedido do dono (14/09/2026):** *"deixando a funcionalidade mais simples
 * no dia a dia… tanto para computador quanto para celular."* No telefone, toda
 * navegação passava pela gaveta: tocar no ☰, esperar a animação, achar o grupo,
 * abrir o grupo, tocar no item. Cinco gestos para trocar de tela, vinte vezes
 * por dia. **Menu que exige abrir gaveta é menu que não se usa** — e o efeito
 * disso não é reclamação, é a pessoa parar de conferir o estoque no salão.
 *
 * ⚠️ **Só no celular** (`lg:hidden`). No computador a lateral está sempre à
 * vista e já resolve; duas navegações na mesma tela seriam duas respostas para
 * "onde eu clico".
 *
 * ⚠️ **Quatro itens, e não seis.** O polegar alcança quatro alvos confortáveis
 * numa largura de telefone; com seis, cada um fica abaixo dos 44px que a norma
 * recomenda e o erro de toque vira regra. O que não cabe aqui continua na
 * gaveta — ela não sai de cena, só deixa de ser o único caminho.
 *
 * ⚠️ **Respeita permissão, como o menu lateral.** Quem não pode ver Compras não
 * ganha um atalho para tomar 403 — e o item some em vez de aparecer inerte.
 */

type Destino = { href: string; nome: string; icone: string; chave?: string[] };

// ⚠️ A ORDEM é a do dia, não a do organograma: Início abre a manhã, Estoque é o
// que mais se consulta no salão, Compras é o que chega pela porta, e Reservas só
// existe para quem ligou o módulo.
const DESTINOS: Destino[] = [
  { href: "/", nome: "Início", icone: "◈" },
  { href: "/estoque", nome: "Estoque", icone: "▤", chave: ["estoque.saldos"] },
  { href: "/compras", nome: "Compras", icone: "❏", chave: ["compras.notas"] },
];

const RESERVAS: Destino = {
  href: "/reservas/agenda",
  nome: "Reservas",
  icone: "☷",
  chave: ["reservas.ver", "reservas.editar"],
};

export default function BarraNavegacao() {
  const caminho = usePathname();
  const { pode, eu } = useSessao();

  // 🔑 Reservas só entra com o módulo ligado NESTA loja — a mesma condição do
  // menu lateral, lida do mesmo lugar (`/auth/me`).
  const destinos = [...DESTINOS, ...(eu?.reservas_ligado ? [RESERVAS] : [])].filter(
    (d) => !d.chave || d.chave.some(pode),
  );
  if (destinos.length < 2) return null;

  return (
    <nav
      id="barra-navegacao"
      aria-label="Telas do dia a dia"
      // ⚠️ `bottom-8`: fica ACIMA do rodapé da versão, que tem 32px e continua
      // existindo. O rodapé diz o que está NO AR, e é o que separa "a correção
      // não funcionou" de "a correção não foi publicada" — não se troca isso
      // por um atalho.
      // ⚠️ `pb-[env(safe-area-inset-bottom)]`: no iPhone com barra de gestos, o
      // último pixel da tela não é tocável, e sem isto o item do meio fica
      // parcialmente embaixo dela.
      className="fixed inset-x-0 bottom-8 z-30 grid border-t border-linha2 bg-superficie/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-sm lg:hidden"
      style={{ gridTemplateColumns: `repeat(${destinos.length}, minmax(0, 1fr))` }}
    >
      {destinos.map((d) => {
        // ⚠️ O Início só está ativo na raiz EXATA: com `startsWith`, ele ficaria
        // aceso em toda tela do sistema, e um indicador que nunca apaga não
        // indica nada.
        const ativo = d.href === "/" ? caminho === "/" : caminho.startsWith(d.href);
        return (
          <Link
            key={d.href}
            href={d.href}
            aria-current={ativo ? "page" : undefined}
            // 48px de alvo, acima dos 44 que a WCAG 2.5.5 recomenda para o dedo.
            className={`flex min-h-[48px] flex-col items-center justify-center gap-0.5 py-1.5 no-underline transition-colors ${
              ativo ? "text-erva" : "text-suave"
            }`}
          >
            <span aria-hidden className="text-[17px] leading-none">
              {d.icone}
            </span>
            <span className="text-[10.5px] font-medium leading-none">{d.nome}</span>
          </Link>
        );
      })}
    </nav>
  );
}
