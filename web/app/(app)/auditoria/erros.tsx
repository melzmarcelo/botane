"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

/**
 * Os erros que o sistema guardou (migração 112).
 *
 * 🔑 **Nasceu do incidente de 09 a 11/10/2026**: a busca das vendas do PDV
 * falhou três dias, e a mensagem que fechou o diagnóstico só existia na tela de
 * Integrações — foi colada por quem a viu. Aqui fica todo erro 500 da API e toda
 * falha inesperada dos agendadores, com o traceback.
 *
 * ⚠️ **O número na frente é o mesmo que a tela mostra no erro** ("registro N em
 * Auditoria ▸ Erros"): é o que a pessoa repete ao pedir ajuda.
 */

type Erro = {
  id: number;
  quando: string;
  origem: string;
  metodo: string | null;
  rota: string | null;
  tipo: string;
  mensagem: string;
  detalhe: string | null;
  versao: string | null;
  usuario: string | null;
};

const ORIGENS: Record<string, string> = {
  api: "sistema",
  agenda_pdv: "busca do PDV",
  agenda_omie: "busca do Omie",
  whatsapp: "WhatsApp",
};

export default function ErrosDoSistema() {
  const [linhas, setLinhas] = useState<Erro[] | null>(null);
  const [origem, setOrigem] = useState("");
  const [aberto, setAberto] = useState<number | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    setLinhas(null);
    const q = new URLSearchParams({ limite: "100" });
    if (origem) q.set("origem", origem);
    api
      .get<Erro[]>(`/erros?${q}`)
      .then(setLinhas)
      .catch((e) => setErro(e.message));
  }, [origem]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;

  return (
    <Cartao>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <label className="text-[14px] text-suave" htmlFor="origem-erro">
          De onde
        </label>
        <select
          id="origem-erro"
          className="campo w-auto"
          value={origem}
          onChange={(e) => setOrigem(e.target.value)}
        >
          <option value="">todos</option>
          {Object.entries(ORIGENS).map(([valor, nome]) => (
            <option key={valor} value={valor}>
              {nome}
            </option>
          ))}
        </select>
      </div>

      {!linhas ? (
        <Carregando />
      ) : !linhas.length ? (
        <Vazio>Nenhum erro registrado{origem ? " desta origem" : ""}.</Vazio>
      ) : (
        <ul className="flex flex-col gap-px bg-linha">
          {linhas.map((l) => (
            <li key={l.id} className="bg-superficie py-3">
              <button
                type="button"
                className="w-full text-left"
                aria-expanded={aberto === l.id}
                onClick={() => setAberto(aberto === l.id ? null : l.id)}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="mono text-[12.5px] text-suave">#{l.id}</span>
                  <Etiqueta cor="alerta">{ORIGENS[l.origem] ?? l.origem}</Etiqueta>
                  <span className="mono text-[12.5px] text-suave">
                    {new Date(l.quando).toLocaleString("pt-BR")}
                    {l.versao ? ` · ${l.versao}` : ""}
                  </span>
                </div>
                <p className="mt-1.5 break-words text-[14px]">
                  <span className="mono text-[13px]">{l.tipo}</span>: {l.mensagem}
                </p>
                {l.rota && (
                  <p className="mono mt-1 break-all text-[12.5px] text-suave">
                    {l.metodo} {l.rota}
                    {l.usuario ? ` · ${l.usuario}` : ""}
                  </p>
                )}
              </button>
              {aberto === l.id && l.detalhe && (
                <pre className="mono mt-2 max-h-[420px] overflow-auto whitespace-pre-wrap break-words rounded border border-linha p-3 text-[12px]">
                  {l.detalhe}
                </pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </Cartao>
  );
}
