"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Etiqueta, Vazio } from "@/components/ui";
import { UnidadeMedida } from "@/lib/cadastros";

/**
 * As unidades que chegaram nas notas e o sistema não sabe ler.
 *
 * 🔑 **Decisão do dono (09/09/2026):** *"conforme as unidades vão chegando pelas
 * notas podemos ir vinculando ou cadastrando"*. A alternativa era importar de
 * uma vez as 603 unidades do cadastro do Omie — global, compartilhado, com `%`,
 * `01` e `18x4x4` no meio. E mesmo restrito ao que os produtos da casa usam
 * sobram 57 siglas para uns doze conceitos: `PC`, `UNID`, `UND`, `UN1`,
 * `1 UNID`, `UM` e `1` são todas "unidade".
 *
 * ⚠️ **O silêncio que isto conserta.** Item de nota com unidade desconhecida
 * não parava o lançamento — a conversão não achava caminho e a quantidade
 * entrava **1:1**. Dez BJ de um produto contado em KG viravam dez quilos no
 * razão, e o custo unitário saía dividido por dez, sem nada avisar.
 *
 * ⚠️ **A fila mostra EXEMPLOS.** "PC" sozinho não diz se é peça, pacote ou
 * peso; ver que ele veio em "COPO DESCARTAVEL 200ML" resolve a dúvida sem sair
 * da tela.
 */

type Pendente = {
  apelido: string;
  itens: number;
  notas: number;
  ultima_vez: string | null;
  exemplos: string[] | null;
};

type Apelido = {
  apelido: string;
  sigla: string;
  unidade: string;
  quem: string | null;
};

export default function UnidadesDeFora({
  ums,
  podeEditar,
}: {
  ums: UnidadeMedida[];
  podeEditar: boolean;
}) {
  const aviso = useAviso();
  const [pendentes, setPendentes] = useState<Pendente[] | null>(null);
  const [apelidos, setApelidos] = useState<Apelido[]>([]);
  const [escolha, setEscolha] = useState<Record<string, string>>({});
  const [ocupado, setOcupado] = useState("");
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    try {
      const r = await api.get<{ pendentes: Pendente[]; apelidos: Apelido[] }>(
        "/unidades-medida/apelidos");
      setPendentes(r.pendentes);
      setApelidos(r.apelidos);
      setErro("");
    } catch (e) {
      // Erro de CARREGAMENTO é mensagem no cartão, não aviso flutuante: o aviso
      // some, e quem abriu a tela ficaria com um bloco vazio sem explicação.
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
      setPendentes([]);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function vincular(apelido: string) {
    const sigla = escolha[apelido];
    if (!sigla) return;
    setOcupado(apelido);
    try {
      const r = await api.post<{ message: string }>("/unidades-medida/apelidos",
        { apelido, sigla });
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível vincular");
    } finally {
      setOcupado("");
    }
  }

  async function remover(apelido: string) {
    setOcupado(apelido);
    try {
      await api.delete(`/unidades-medida/apelidos/${encodeURIComponent(apelido)}`);
      aviso.sucesso(`${apelido} voltou para a fila.`);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível remover");
    } finally {
      setOcupado("");
    }
  }

  if (!pendentes) return <Carregando />;

  return (
    <div className="flex flex-col gap-5">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {/* 🔑 A explicação vem ANTES da lista: sem ela, "BJ · 1 item" não diz a
          ninguém por que aquilo está ali nem o que acontece se ficar. */}
      <p className="max-w-[75ch] text-[13px] leading-snug text-suave">
        O fornecedor escreve a unidade do jeito dele — <b>UNID</b>, <b>CX.</b>, <b>PT</b> — e o
        que não casa com o cadastro daqui entra na nota <b>sem conversão</b>: a quantidade é
        usada como está. Diga o que cada uma significa e a próxima nota entra convertida.
      </p>

      {!pendentes.length ? (
        <Vazio>Nenhuma unidade desconhecida veio nas notas.</Vazio>
      ) : (
        <div className="overflow-x-auto">
          <table className="tabela">
            <thead>
              <tr>
                <th>Veio como</th>
                <th>Onde apareceu</th>
                <th>Passa a valer como</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {pendentes.map((p) => (
                <tr key={p.apelido}>
                  <td>
                    <span className="mono font-semibold">{p.apelido}</span>
                    <span className="block text-[12.5px] text-suave">
                      {p.itens} item(ns) em {p.notas} nota(s)
                    </span>
                  </td>
                  {/* ⚠️ O exemplo é a informação que DECIDE: "BJ" em
                      "CHAMPIGNON FATIADO" é bandeja, e isso não se descobre
                      pela sigla. */}
                  <td className="text-[13px] text-suave">
                    {(p.exemplos ?? []).join(" · ") || "—"}
                  </td>
                  <td>
                    <select
                      className="campo w-[190px] py-1"
                      aria-label={`Unidade para ${p.apelido}`}
                      disabled={!podeEditar}
                      value={escolha[p.apelido] ?? ""}
                      onChange={(e) =>
                        setEscolha({ ...escolha, [p.apelido]: e.target.value })
                      }
                    >
                      <option value="">— escolha —</option>
                      {ums.filter((u) => u.ativo).map((u) => (
                        <option key={u.sigla} value={u.sigla}>
                          {u.sigla} — {u.nome}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-secundario px-2.5 py-1"
                      disabled={!podeEditar || !escolha[p.apelido] || ocupado === p.apelido}
                      onClick={() => void vincular(p.apelido)}
                    >
                      {ocupado === p.apelido ? "…" : "Vincular"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* ⚠️ A unidade que NÃO existe aqui (metro, por exemplo) não se
              resolve por tradução: ela se cadastra acima, e aí aparece no
              seletor. Dizer isso evita a tradução forçada para "a mais
              parecida", que é como o custo para de fluir. */}
          <p className="mt-3 max-w-[70ch] text-[13px] text-suave">
            Não achou a unidade certa na lista? Cadastre-a em <b>Unidades de medida</b>, acima —
            traduzir para a mais parecida faz a conta sair errada em silêncio.
          </p>
        </div>
      )}

      {!!apelidos.length && (
        <div>
          <p className="rotulo mb-2">Já traduzidas</p>
          <div className="flex flex-wrap gap-2">
            {apelidos.map((a) => (
              <span
                key={a.apelido}
                className="inline-flex items-center gap-2 rounded border border-linha px-2.5 py-1 text-[13px]"
              >
                <span className="mono">{a.apelido}</span>
                <span className="text-suave">vale como</span>
                <Etiqueta cor="erva">{a.sigla}</Etiqueta>
                {podeEditar && (
                  <button
                    type="button"
                    className="text-[12.5px] text-suave underline"
                    disabled={ocupado === a.apelido}
                    onClick={() => void remover(a.apelido)}
                  >
                    desfazer
                  </button>
                )}
              </span>
            ))}
          </div>
          {/* 🔑 O que já entrou NÃO se corrige por aqui: o razão é append-only. */}
          <p className="mt-2 max-w-[70ch] text-[13px] text-suave">
            A tradução vale para as <b>próximas</b> notas. O que já foi lançado se corrige por
            estorno — o razão não se reescreve.
          </p>
        </div>
      )}
    </div>
  );
}
