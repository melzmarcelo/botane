"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * O caminho de volta — para onde a pessoa realmente veio.
 *
 * 🔑 **O pedido do dono (09/09/2026):** "caso eu acesse o consumo por pessoa em
 * Períodos de consumo e clicar no voltar da tela, ele volta para as Vendas".
 * Cada tela tinha um destino ESCRITO À MÃO — o `href` fixo era um palpite sobre
 * de onde a pessoa teria vindo, e o palpite errava sempre que havia mais de um
 * caminho até ali.
 *
 * ⚠️ **Voltar de verdade é `history.back()`, não navegar para um endereço.**
 * Navegar perde o estado da tela de origem: a lista reabriria na primeira
 * página, sem o filtro — que é exatamente a queixa que o resto desta mudança
 * foi feita para resolver. O histórico devolve a URL inteira, com filtro,
 * página e tamanho.
 *
 * ⚠️ **O `href` continua obrigatório, e não é decoração.** Ele é o destino de
 * quem chegou aqui SEM histórico: link colado, aba nova, atualizar a página com
 * F5. Sem ele, o voltar não teria para onde ir e sumiria justamente para quem
 * mais precisa dele. É também o que o navegador mostra na barra de status e o
 * que faz o "abrir em nova aba" funcionar.
 */
export default function Voltar({
  href,
  children,
  className = "",
}: {
  /** Para onde ir quando não há histórico desta sessão. */
  href: string;
  children: React.ReactNode;
  /** Classes de LAYOUT do lugar onde ele está (`self-start`, por exemplo). */
  className?: string;
}) {
  const router = useRouter();
  // ⚠️ Decidido num efeito, não no render: `history.length` só existe no
  // navegador, e ler no render devolveria valores diferentes dos dois lados e
  // quebraria a hidratação — a mesma lição da preferência de "por página".
  const [temHistorico, setTemHistorico] = useState(false);
  useEffect(() => {
    setTemHistorico(window.history.length > 1);
  }, []);

  return (
    <Link
      href={href}
      className={`link-voltar ${className}`.trim()}
      onClick={(e) => {
        // Ctrl/Cmd/meio: quem pede uma aba nova quer o ENDEREÇO, não o
        // histórico desta aba — deixar o navegador cuidar é o certo.
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        if (!temHistorico) return;
        e.preventDefault();
        router.back();
      }}
    >
      {children}
    </Link>
  );
}
