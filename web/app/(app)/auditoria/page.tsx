"use client";

import { useRouter, useSearchParams } from "next/navigation";
import ExplicaTela from "@/components/explica-tela";
import BotaoExportar from "@/components/exportar";
import Alteracoes from "./alteracoes";
import ErrosDoSistema from "./erros";

/**
 * Auditoria: o que alguém mudou, e o que o sistema não conseguiu fazer.
 *
 * 🔑 **A aba de erros nasceu do incidente de 09 a 11/10/2026** (migração 112):
 * a busca das vendas do PDV falhou três dias, e a mensagem que fechou o
 * diagnóstico só existia na tela de Integrações. ⚠️ São abas, e não uma lista
 * só: misturar faria o histórico de alterações encher de ruído técnico — e o
 * erro sumir no meio dele.
 *
 * ⚠️ **A aba vive na URL** (`?aba=erros`), como em Integrações: é o endereço que
 * a frase do erro 500 manda abrir ("registro N em Auditoria ▸ Erros").
 */
const ABAS = [
  { id: "alteracoes", nome: "Alterações" },
  { id: "erros", nome: "Erros" },
] as const;

export default function PaginaAuditoria() {
  const router = useRouter();
  const busca = useSearchParams();
  const aba = busca.get("aba") === "erros" ? "erros" : "alteracoes";

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">Administração</p>
          <h1 className="mt-1 text-[30px] font-bold tracking-tight">Auditoria</h1>
          <ExplicaTela>
            Quem mudou o quê, quando, e o valor antes e depois. Senha e credencial nunca entram
            aqui — o registro é filtrado antes de gravar. Na aba Erros, o que o sistema tentou
            fazer e não conseguiu.
          </ExplicaTela>
        </div>
        {/* 🔑 O registro do período em planilha ou PDF (23/10/2026). */}
        <BotaoExportar relatorio="auditoria" rotulo="Imprimir auditoria" />
      </header>

      <nav className="flex flex-wrap gap-1 border-b border-linha">
        {ABAS.map((a) => (
          <button
            key={a.id}
            onClick={() => router.replace(`/auditoria?aba=${a.id}`)}
            className={`-mb-px border-b-2 px-3 py-2 text-[14.5px] ${
              aba === a.id
                ? "border-erva font-semibold text-erva"
                : "border-transparent text-suave hover:text-tinta"
            }`}
          >
            {a.nome}
          </button>
        ))}
      </nav>

      {aba === "alteracoes" ? <Alteracoes /> : <ErrosDoSistema />}
    </div>
  );
}
