"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

type Linha = {
  id: number;
  entidade: string;
  id_entidade: string | null;
  acao: string;
  antes: Record<string, unknown> | null;
  depois: Record<string, unknown> | null;
  em: string;
  usuario: string | null;
  email: string | null;
};

function resumo(d: Record<string, unknown> | null) {
  if (!d) return "—";
  const partes = Object.entries(d)
    .slice(0, 4)
    .map(([k, v]) => `${k}: ${v === null ? "—" : String(v)}`);
  return partes.join(" · ") || "—";
}

export default function PaginaAuditoria() {
  const [linhas, setLinhas] = useState<Linha[] | null>(null);
  const [aberta, setAberta] = useState<number | null>(null);
  const [erro, setErro] = useState("");
  const pag = usePaginacao("auditoria", { padrao: 50 });

  useEffect(() => {
    api
      .listar<Linha>(`/auditoria?${new URLSearchParams(pag.parametros)}`)
      .then((r) => {
        setLinhas(r.itens);
        pag.setTotal(r.total);
      })
      .catch((e) => setErro(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.offset, pag.porPagina]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!linhas) return <Carregando />;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Administração</p>
        <h1 className="mt-1 text-[30px] font-bold tracking-tight">Auditoria</h1>
        <p className="mt-1 max-w-[64ch] text-suave">
          Quem mudou o quê, quando, e o valor antes e depois. Senha e credencial nunca entram
          aqui — o registro é filtrado antes de gravar.
        </p>
      </header>

      <Cartao>
        {!linhas.length ? (
          <Vazio>Nada registrado ainda.</Vazio>
        ) : (
          <>
          {/* Celular: cada registro vira um cartão — tabela de 5 colunas não cabe. */}
          <ul className="flex flex-col gap-px bg-linha md:hidden">
            {linhas.map((l) => (
              <li key={l.id} className="bg-superficie py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Etiqueta cor={l.acao === "login" ? "neutro" : "erva"}>{l.acao}</Etiqueta>
                  <span className="mono text-[12.5px]">
                    {l.entidade}
                    {l.id_entidade ? ` #${l.id_entidade}` : ""}
                  </span>
                </div>
                <p className="mt-1.5 text-[14px]">
                  {l.usuario ?? "sistema"}
                  <span className="mono ml-2 text-[12.5px] text-suave">
                    {new Date(l.em).toLocaleString("pt-BR")}
                  </span>
                </p>
                <p className="mt-1 break-words text-[13px] text-suave">{resumo(l.depois)}</p>
              </li>
            ))}
          </ul>

          <div className="hidden overflow-x-auto md:block">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Quando</th>
                  <th>Quem</th>
                  <th>O quê</th>
                  <th>Ação</th>
                  <th>Depois</th>
                </tr>
              </thead>
              <tbody>
                {linhas.map((l) => (
                  <tr
                    key={l.id}
                    className="cursor-pointer align-top"
                    onClick={() => setAberta(aberta === l.id ? null : l.id)}
                  >
                    <td className="mono whitespace-nowrap text-[13px]">
                      {new Date(l.em).toLocaleString("pt-BR")}
                    </td>
                    <td className="whitespace-nowrap">{l.usuario ?? "sistema"}</td>
                    <td className="mono text-[13px]">
                      {l.entidade}
                      {l.id_entidade ? ` #${l.id_entidade}` : ""}
                    </td>
                    <td>
                      <Etiqueta cor={l.acao === "login" ? "neutro" : "erva"}>{l.acao}</Etiqueta>
                    </td>
                    <td className="max-w-[420px] text-[13px] text-suave">
                      {aberta === l.id ? (
                        <div className="flex flex-col gap-2">
                          <div>
                            <span className="rotulo">antes</span>
                            <pre className="mono mt-1 whitespace-pre-wrap break-words text-[12px]">
                              {JSON.stringify(l.antes, null, 2) ?? "—"}
                            </pre>
                          </div>
                          <div>
                            <span className="rotulo">depois</span>
                            <pre className="mono mt-1 whitespace-pre-wrap break-words text-[12px]">
                              {JSON.stringify(l.depois, null, 2) ?? "—"}
                            </pre>
                          </div>
                        </div>
                      ) : (
                        <span className="line-clamp-1">{resumo(l.depois)}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
        )}
        <Paginacao p={pag} rotulo="evento(s)" />
      </Cartao>
    </div>
  );
}
