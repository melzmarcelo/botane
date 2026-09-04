"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useSessao } from "@/lib/sessao";

/**
 * A barra do topo — a marca à esquerda, quem entrou à direita.
 *
 * 🔑 **O nome de quem entrou vira o controle.** Antes ele era texto no pé do
 * menu lateral, junto de dois botões: no celular, onde a gaveta é fechada por
 * padrão, isso queria dizer que sair do sistema exigia abrir o menu, rolar até
 * o fim e só então achar o botão. Sair, trocar de senha e conferir o próprio
 * cadastro são as ações que se procuram no CANTO SUPERIOR DIREITO — é a
 * convenção de todo sistema que a pessoa já usa, e convenção contrariada custa
 * uma busca inteira pela tela.
 */
export default function BarraSuperior({
  marca,
  aoAbrirMenu,
}: {
  marca: React.ReactNode;
  aoAbrirMenu: () => void;
}) {
  const { eu, sair } = useSessao();
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);

  // Fecha ao clicar fora e no Esc: menu que só fecha pelo próprio botão é menu
  // que fica preso na tela quando a pessoa desiste dele.
  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => {
      if (caixa.current && !caixa.current.contains(e.target as Node)) setAberto(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setAberto(false);
    document.addEventListener("mousedown", fora);
    window.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fora);
      window.removeEventListener("keydown", esc);
    };
  }, [aberto]);

  if (!eu) return null;

  const iniciais = (eu.nome || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");

  const item =
    "block w-full rounded px-3 py-2 text-left text-[14px] text-tinta no-underline hover:bg-superficie2";

  return (
    <header
      id="barra-superior"
      className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-linha bg-superficie/95 px-4 backdrop-blur-sm sm:px-6"
    >
      <button
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded border border-linha2 bg-superficie lg:hidden"
        onClick={aoAbrirMenu}
        aria-label="Abrir menu"
      >
        <span className="flex flex-col gap-[3px]">
          <span className="block h-[2px] w-4 bg-tinta" />
          <span className="block h-[2px] w-4 bg-tinta" />
          <span className="block h-[2px] w-4 bg-tinta" />
        </span>
      </button>

      <div className="min-w-0 flex-1">{marca}</div>

      <div className="relative shrink-0" ref={caixa}>
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={aberto}
          onClick={() => setAberto((a) => !a)}
          className="flex items-center gap-2 rounded-full border border-linha2 py-1 pl-1 pr-2.5 hover:bg-superficie2 sm:pr-3"
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-erva-claro text-[12px] font-bold text-erva">
            {iniciais || "?"}
          </span>
          {/* O nome some no celular: 32 caracteres ao lado do avatar empurram a
              marca para fora. O avatar continua sendo o alvo. */}
          <span className="hidden max-w-[180px] truncate text-[14px] font-medium sm:block">
            {eu.nome}
          </span>
          <svg viewBox="0 0 10 6" aria-hidden className="h-[6px] w-[10px] shrink-0 text-suave">
            <path
              d="M1 1l4 4 4-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>

        {aberto && (
          <div
            role="menu"
            id="menu-usuario"
            className="cartao absolute right-0 z-50 mt-1.5 w-[236px] p-1.5 shadow-[0_10px_30px_rgba(0,0,0,.14)]"
          >
            {/* Quem sou eu, dito uma vez: no celular o nome não cabe no botão. */}
            <div className="border-b border-linha px-3 pb-2 pt-1.5">
              <p className="truncate text-[14px] font-semibold">{eu.nome}</p>
              <p className="truncate text-[12.5px] text-suave">
                {eu.papeis.join(", ") || "sem papel"}
              </p>
            </div>
            <div className="pt-1.5">
              <Link href="/alertas" className={item} onClick={() => setAberto(false)}>
                Alertas
              </Link>
              {/* ⚠️ **A Ajuda vive AQUI, e não no menu lateral.** O manual é de
                  QUEM está usando — como o alerta e o perfil —, e não é assunto
                  do sistema como estoque ou compras. E é o único item sem
                  permissão nenhuma: quem tem menos acesso é justamente quem
                  mais precisa dele. */}
              <Link href="/ajuda" className={item} onClick={() => setAberto(false)}>
                Ajuda
              </Link>
              {/* 🔑 **Meu consumo vive aqui pelo mesmo motivo que a Ajuda**
                  (04/09/2026, pedido do dono: "isto pode estar dentro do menu
                  do usuario"). É do QUEM está usando, não assunto do sistema —
                  e, como a Ajuda, não exige permissão nenhuma: ninguém precisa
                  de autorização para ver a própria dívida. */}
              <Link href="/meu-consumo" className={item} onClick={() => setAberto(false)}>
                Meu consumo
              </Link>
              <Link href="/perfil" className={item} onClick={() => setAberto(false)}>
                Perfil
              </Link>
              <Link href="/trocar-senha" className={item} onClick={() => setAberto(false)}>
                Alterar senha
              </Link>
              {/* ⚠️ Sair se anuncia ANTES do clique: vermelho no hover, como
                  `.link-acao-erro`. É a única ação daqui que interrompe o
                  trabalho de quem clicou. */}
              <button
                type="button"
                className={`${item} hover:bg-superficie2 hover:text-erro`}
                onClick={() => {
                  setAberto(false);
                  void sair();
                }}
              >
                Sair
              </button>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
