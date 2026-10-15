"use client";

/**
 * "Chamar o garçom" e "Pedir a conta" (fase 2, 115): um alerta no painel de pedidos, ligado
 * à mesa. Só aparece com a opção ligada na loja E numa mesa (quem decide é o servidor).
 *
 * 🔑 Apertar de novo não abre outro chamado — o servidor devolve o que está aberto, e a
 * frase diz que o garçom já foi avisado.
 */

import { useState } from "react";
import { MesaService } from "@/lib/cardapio-vivo";
import type { Textos } from "./textos";

type Props = { token: string; sessao: () => string; t: Textos; aoChamar: (tipo: "GARCOM" | "CONTA") => void };

export default function Chamados({ token, sessao, t, aoChamar }: Props) {
  const [aberto, setAberto] = useState(false);
  const [recado, setRecado] = useState<string | null>(null);

  async function chamar(tipo: "GARCOM" | "CONTA") {
    setAberto(false);
    aoChamar(tipo);
    const r = await MesaService.chamar(token, tipo, sessao());
    setRecado(r.ok ? r.dados.message : r.erro);
    setTimeout(() => setRecado(null), 4000);
  }

  return (
    <div className="relative">
      <button type="button" onClick={() => setAberto((v) => !v)} aria-expanded={aberto}
              className="rounded-full bg-white/15 px-3 py-1 text-xs backdrop-blur">
        🔔 {t.chamar}
      </button>
      {aberto && (
        <div className="absolute right-0 top-9 z-50 flex w-48 flex-col overflow-hidden rounded-2xl bg-[var(--cv-fundo)] text-sm text-[var(--cv-tinta)] shadow-2xl"
             role="menu">
          <button type="button" role="menuitem" className="px-4 py-3 text-left font-medium"
                  onClick={() => void chamar("GARCOM")}>{t.chamarGarcom}</button>
          <button type="button" role="menuitem" className="border-t border-current/10 px-4 py-3 text-left font-medium"
                  onClick={() => void chamar("CONTA")}>{t.pedirConta}</button>
        </div>
      )}
      {recado && (
        <p role="status" className="fixed inset-x-6 bottom-6 z-50 rounded-2xl bg-[var(--cv-principal)] px-4 py-3 text-center text-sm font-semibold text-white shadow-2xl">
          {recado}
        </p>
      )}
    </div>
  );
}
