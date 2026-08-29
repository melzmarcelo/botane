"use client";

import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";

/**
 * Exportação para o PDV — o que daqui ainda não está no cardápio de lá.
 *
 * 🔑 **A aba "pendentes" é uma CONSULTA, não uma tabela.** O servidor compara o
 * que seria enviado agora com o que foi enviado da última vez, e pergunta ao
 * PDV o que já existe do outro lado. Uma fila mantida à mão precisaria ser
 * alimentada em todo lugar que salva um cadastro — e o próximo lugar, que vai
 * existir, nasceria sem ela.
 *
 * ⚠️ **`ADOTAR` é o caso mais comum na primeira vez, e é o que evita o
 * desastre.** Os 30 grupos do cardápio existem há anos e nunca souberam do
 * Botané; sem reconhecê-los, o primeiro envio criaria 29 duplicados. Adotar é
 * um update que só grava o nosso código lá — nome, cor e situação ficam como
 * estão.
 */

type Item = {
  tipo: string;
  id_registro: number;
  nome: string;
  acao: string;
  corpo: Record<string, unknown>;
  codigo_pdv: string | null;
  nome_no_pdv: string | null;
};

type Erro = {
  tipo: string;
  id_registro: number;
  nome: string;
  acao: string;
  erro: string;
  enviado: Record<string, unknown> | null;
  quando: string;
};

type Fila = { pendentes: Item[]; integrados: Item[]; erros: Erro[] };

type Aba = "pendentes" | "integrados" | "erros";

const COR_DA_ACAO: Record<string, "neutro" | "erva" | "alerta"> = {
  ADOTAR: "erva",
  CRIAR: "erva",
  ATUALIZAR: "neutro",
  DESATIVAR: "alerta",
};

const EXPLICA: Record<string, string> = {
  ADOTAR: "já existe no PDV com este nome — o envio só grava o vínculo, sem mexer no resto",
  CRIAR: "não existe no PDV — será cadastrado",
  ATUALIZAR: "existe e mudou aqui",
  DESATIVAR: "saiu da integração aqui — será desativado lá",
};

/**
 * ⚠️ A mesma ação quer dizer coisas diferentes nas duas abas: em **pendentes**
 * é o que VAI acontecer; em **integrados**, o que ACONTECEU. "desativar" e
 * "desativada" são o antes e o depois do mesmo clique.
 */
function estadoIntegrado(i: Item): { rotulo: string; explica: string } {
  if (i.acao !== "DESATIVAR") return { rotulo: "no cardápio", explica: "" };
  const ativoLa = (i.corpo as { ativo_no_pdv?: boolean }).ativo_no_pdv;
  if (i.tipo === "SETOR")
    return {
      rotulo: "fora da integração",
      explica:
        "saiu daqui, mas continua vinculado no PDV — a impressora não tem como ser " +
        "desativada pela API. Remarcar aqui o reconhece de novo, sem recriar.",
    };
  return {
    rotulo: ativoLa === false ? "desativada" : "fora da integração",
    explica:
      ativoLa === false
        ? "desativada no cardápio do PDV — não aparece mais para quem vende"
        : "saiu daqui e continua ativa no PDV",
  };
}

export default function PaginaExportacao() {
  const aviso = useAviso();
  const { eu } = useSessao();
  const [fila, setFila] = useState<Fila | null>(null);
  const [erroTela, setErroTela] = useState("");
  const [aba, setAba] = useState<Aba>("pendentes");
  const [enviando, setEnviando] = useState(false);
  const [confirmando, setConfirmando] = useState(false);

  const carregar = useCallback(async () => {
    setErroTela("");
    try {
      setFila(await api.get<Fila>("/pdv/envio/fila"));
    } catch (e) {
      // ⚠️ Erro de CARREGAMENTO fica inline: é ele que explica a tela vazia.
      setFila(null);
      setErroTela(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function enviar() {
    setEnviando(true);
    try {
      const r = await api.post<{ enviados: number; falhas: number; message: string }>(
        "/pdv/envio",
        {},
      );
      if (r.falhas) aviso.erro(r.message);
      else aviso.sucesso(r.message);
      await carregar();
      if (r.falhas) setAba("erros");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível enviar");
    } finally {
      setEnviando(false);
      setConfirmando(false);
    }
  }

  if (!eu?.enviar_ao_pdv) {
    return (
      <div className="flex flex-col gap-6">
        <header>
          <p className="rotulo">Cadastros</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight">Exportação para o PDV</h1>
        </header>
        <Aviso tipo="info">
          O envio ao PDV está desligado. Ligue em <b>Integrações ▸ PDV Legal</b>, em
          &ldquo;Enviar informações ao PDV&rdquo;.
        </Aviso>
      </div>
    );
  }

  const pendentes = fila?.pendentes ?? [];
  const desativacoes = pendentes.filter((p) => p.acao === "DESATIVAR").length;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="rotulo">Cadastros</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
            Exportação para o PDV
          </h1>
          <p className="mt-1 max-w-[68ch] text-suave">
            O que está marcado como integrado aqui e ainda não chegou ao cardápio do PDV.
            Nada sai sozinho — o envio é sempre disparado por alguém.
          </p>
        </div>
        {!!pendentes.length && (
          <button
            className="btn btn-primario"
            disabled={enviando}
            onClick={() => (desativacoes ? setConfirmando(true) : void enviar())}
          >
            {enviando ? "Enviando…" : `Enviar ${pendentes.length} pendente(s)`}
          </button>
        )}
      </header>

      {erroTela && <Aviso tipo="erro">{erroTela}</Aviso>}

      <nav className="flex gap-1 border-b border-linha">
        {(
          [
            ["pendentes", "Pendentes", pendentes.length],
            ["integrados", "Integrados", fila?.integrados.length ?? 0],
            ["erros", "Erros", fila?.erros.length ?? 0],
          ] as const
        ).map(([id, nome, n]) => (
          <button
            key={id}
            onClick={() => setAba(id)}
            className={`-mb-px border-b-2 px-3 py-2 text-[14.5px] ${
              aba === id
                ? "border-erva font-semibold text-erva"
                : "border-transparent text-suave hover:text-tinta"
            }`}
          >
            {nome} ({n})
          </button>
        ))}
      </nav>

      {!fila ? (
        <Carregando />
      ) : (
        <Cartao>
          {aba === "erros" ? (
            !fila.erros.length ? (
              <Vazio>Nenhum erro.</Vazio>
            ) : (
              <ul className="flex flex-col gap-px bg-linha">
                {fila.erros.map((e) => (
                  <li key={`${e.tipo}-${e.id_registro}`} className="bg-superficie py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{e.nome}</span>
                      <Etiqueta>{e.tipo.toLowerCase()}</Etiqueta>
                      <Etiqueta cor="alerta">{e.acao.toLowerCase()}</Etiqueta>
                    </div>
                    <p className="mt-1 text-[13.5px] text-erro">{e.erro}</p>
                    {/* ⚠️ O corpo enviado fica à vista: "erro 400" sozinho não
                        diz o que ajustar — com o que foi mandado ao lado, quem
                        olha vê que faltou o grupo ou que o nome já existe. */}
                    {e.enviado && (
                      <pre className="mono mt-1.5 overflow-x-auto rounded bg-superficie2 p-2 text-[12px] text-suave">
                        {JSON.stringify(e.enviado)}
                      </pre>
                    )}
                  </li>
                ))}
              </ul>
            )
          ) : (aba === "pendentes" ? pendentes : fila.integrados).length === 0 ? (
            <Vazio>
              {aba === "pendentes"
                ? "Nada pendente — o PDV está com tudo o que está marcado aqui."
                : "Nada integrado ainda."}
            </Vazio>
          ) : (
            <div className="overflow-x-auto">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>O quê</th>
                    <th>Nome</th>
                    <th>{aba === "pendentes" ? "Ação" : "Situação"}</th>
                    <th>No PDV</th>
                  </tr>
                </thead>
                <tbody>
                  {(aba === "pendentes" ? pendentes : fila.integrados).map((i) => (
                    <tr key={`${i.tipo}-${i.id_registro}`}>
                      <td className="text-[13px] text-suave">{i.tipo.toLowerCase()}</td>
                      <td className="font-medium">{i.nome}</td>
                      <td>
                        {aba === "pendentes" ? (
                          <>
                            <Etiqueta cor={COR_DA_ACAO[i.acao] ?? "neutro"}>
                              {i.acao.toLowerCase()}
                            </Etiqueta>
                            <span className="mt-0.5 block text-[12.5px] leading-snug text-suave">
                              {EXPLICA[i.acao]}
                            </span>
                          </>
                        ) : (
                          <>
                            <Etiqueta cor={i.acao === "DESATIVAR" ? "alerta" : "erva"}>
                              {estadoIntegrado(i).rotulo}
                            </Etiqueta>
                            {!!estadoIntegrado(i).explica && (
                              <span className="mt-0.5 block max-w-[52ch] text-[12.5px] leading-snug text-suave">
                                {estadoIntegrado(i).explica}
                              </span>
                            )}
                          </>
                        )}
                      </td>
                      <td className="mono text-[13px] text-suave">
                        {i.nome_no_pdv ? (
                          <>
                            {i.nome_no_pdv}
                            {i.codigo_pdv ? ` · ${i.codigo_pdv}` : ""}
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Cartao>
      )}

      {/* ⚠️ Desativar mexe no cardápio de quem está vendendo — pergunta antes,
          e diz o que a ação FAZ, não só "tem certeza". */}
      {confirmando && (
        <Confirmacao
          titulo="Enviar ao PDV"
          rotuloConfirmar="Enviar"
          ocupado={enviando}
          aoConfirmar={() => void enviar()}
          aoCancelar={() => setConfirmando(false)}
        >
          <p>
            São {pendentes.length} registro(s), e {desativacoes} deles{" "}
            <b>serão desativados no cardápio do PDV</b> — deixam de aparecer para quem
            vende. Os demais são cadastros ou vínculos.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
