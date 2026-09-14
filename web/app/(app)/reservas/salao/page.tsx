"use client";

import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Cartao, Etiqueta } from "@/components/ui";
import { api } from "@/lib/api";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { useSessao } from "@/lib/sessao";

/**
 * O salão da casa: salões, mesas e quantos lugares cada uma tem.
 *
 * 🔑 **Pedido do dono (14/09/2026):** *"para controle interno, ter o cadastro de
 * salões, cadastro de mesas, lugares por mesas."* E, depois de ver a primeira
 * versão: *"daria para melhorar a usabilidade… principalmente no cadastro de
 * mesas que pode se tornar bem extenso. Poderia ser separado por salão."*
 *
 * 🔑 **Um salão de cada vez, em abas.** A primeira versão empilhava um cartão
 * por salão: a página crescia com o total de mesas da CASA, e com três salões e
 * trinta mesas virava uma rolagem em que ninguém achava nada. Agora a página
 * tem o tamanho de um salão. ⚠️ A aba escolhida mora no ENDEREÇO, como o resto
 * do sistema: recarregar, voltar e guardar o link caem no mesmo salão.
 *
 * 🔑 **A edição do salão vem DENTRO da aba dele.** Antes havia uma tabela de
 * salões no topo e os cartões embaixo — duas respostas para "onde eu mexo neste
 * salão". Agora é uma só.
 *
 * 🔑 **`Lugares` e `máximo` são dois números de propósito.** Lugares é o
 * confortável; máximo é com a cadeira extra. A alocação usa o máximo, os
 * relatórios de ocupação usam os lugares — um campo só obrigaria a escolher
 * entre mentir para o cliente e recusar mesa que caberia.
 *
 * 🔑 **"Junta com" é a mesa vizinha que encosta nesta**, e é assim que um grupo
 * de 8 senta em duas mesas de 4 sem ninguém cadastrar uma "mesa 7+8" que não
 * existe no salão. ⚠️ Vale nos dois sentidos: escolher aqui grava dos dois
 * lados, e o servidor solta o par antigo para não deixar triângulo.
 *
 * ⚠️ **Desligar o salão tira as mesas dele da disponibilidade sem apagar
 * cadastro** — é a Varanda no inverno. Apagar levaria junto a resposta para
 * "onde aquela reserva de agosto sentou", e por isso salão com mesa não se
 * exclui.
 */

type Salao = {
  id: number;
  nome: string;
  ativo: boolean;
  ordem: number;
  mesas: number;
  lugares: number;
};
type Mesa = {
  id: number;
  id_salao: number;
  nome: string;
  lugares: number;
  capacidade_max: number;
  ativo: boolean;
  junta_com: number | null;
  junta_com_nome: string | null;
};
type Dados = {
  saloes: Salao[];
  mesas: Mesa[];
  mesas_ativas: number;
  lugares: number;
  capacidade_max: number;
  maior_grupo: number;
};

export default function SalaoDaCasa() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const [dados, setDados] = useState<Dados | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [novoSalao, setNovoSalao] = useState("");
  const [criandoSalao, setCriandoSalao] = useState(false);
  const [lote, setLote] = useState(false);
  // ⚠️ Sem atraso: aba é clique, não digitação. O debounce de 300 ms do padrão
  // existe para campo de busca, e aqui deixaria o endereço atrás do que se vê.
  const [abaUrl, setAbaUrl] = useEstadoNaUrl<string>("salao", "", { atraso: 0 });

  const carregar = useCallback(async () => {
    try {
      setDados(await api.get<Dados>("/reservas/salao"));
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar o salão");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function agir(acao: () => Promise<{ message: string }>) {
    setOcupado(true);
    try {
      const r = await acao();
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
      // ⚠️ Recarrega TAMBÉM no erro: a tela pode ter mostrado o valor novo num
      // campo que o servidor recusou, e deixá-lo ali faria a pessoa acreditar
      // que gravou.
      await carregar();
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;

  const podeEditar = pode("reservas.configurar");
  // ⚠️ Endereço apontando para salão que não existe mais (link antigo, salão
  // excluído) cai no primeiro em vez de numa tela vazia sem explicação.
  const aberto =
    dados.saloes.find((s) => String(s.id) === abaUrl) ?? dados.saloes[0] ?? null;
  const minhas = aberto ? dados.mesas.filter((m) => m.id_salao === aberto.id) : [];

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="titulo">Salão</h1>
        <p className="text-[14px] text-suave">
          Onde as pessoas sentam. É daqui que a disponibilidade vai dizer se cabe.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { n: dados.mesas_ativas, r: "mesas ativas" },
          { n: dados.lugares, r: "lugares confortáveis" },
          { n: dados.capacidade_max, r: "com a cadeira extra" },
          { n: dados.maior_grupo, r: "maior grupo que cabe" },
        ].map((t) => (
          <div key={t.r} className="cartao px-4 py-3">
            <b className="mono block text-[26px] leading-none">{t.n}</b>
            <span className="text-[12.5px] text-suave">{t.r}</span>
          </div>
        ))}
      </div>

      {/* ---- as abas: um salão de cada vez ---- */}
      <div className="flex flex-wrap items-center gap-2">
        {dados.saloes.map((s) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={aberto?.id === s.id}
            aria-label={`salão ${s.nome}`}
            className={`rounded-full border px-3.5 py-1.5 text-[13.5px] ${
              aberto?.id === s.id
                ? "border-erva bg-erva-claro font-medium text-erva"
                : "border-linha2 text-suave hover:border-erva"
            }`}
            onClick={() => setAbaUrl(String(s.id))}
          >
            {s.nome}
            <span className="mono ml-2 text-[11.5px] opacity-70">{s.mesas}</span>
            {!s.ativo && <span className="ml-2 text-[11px]">desligado</span>}
          </button>
        ))}

        {podeEditar &&
          (criandoSalao ? (
            <span className="flex items-center gap-2">
              <input
                className="campo"
                autoFocus
                placeholder="Nome do salão"
                aria-label="nome do novo salão"
                value={novoSalao}
                onChange={(e) => setNovoSalao(e.target.value)}
              />
              <button
                className="btn btn-secundario"
                disabled={ocupado || !novoSalao.trim()}
                onClick={() =>
                  void agir(async () => {
                    const r = await api.post<{ id: number; message: string }>(
                      "/reservas/saloes",
                      { nome: novoSalao.trim(), ordem: dados.saloes.length },
                    );
                    setNovoSalao("");
                    setCriandoSalao(false);
                    // Abre o salão recém-criado: é onde a pessoa vai trabalhar.
                    setAbaUrl(String(r.id));
                    return r;
                  })
                }
              >
                criar
              </button>
              <button className="link-acao" onClick={() => setCriandoSalao(false)}>
                cancelar
              </button>
            </span>
          ) : (
            <button
              type="button"
              className="rounded-full border border-dashed border-linha2 px-3.5 py-1.5 text-[13.5px] text-suave hover:border-erva"
              onClick={() => setCriandoSalao(true)}
            >
              + salão
            </button>
          ))}
      </div>

      {!aberto ? (
        <Aviso tipo="info">
          Nenhum salão cadastrado ainda. Crie o primeiro — Salão principal, Varanda — e
          depois acrescente as mesas dele.
        </Aviso>
      ) : (
        <Cartao
          titulo={aberto.nome}
          descricao="Lugares é o confortável; máximo é com a cadeira extra — a alocação usa o máximo."
          acao={
            podeEditar && (
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn btn-secundario"
                  disabled={ocupado}
                  onClick={() => setLote((v) => !v)}
                >
                  + várias mesas
                </button>
                <button
                  className="btn btn-secundario"
                  disabled={ocupado}
                  onClick={() =>
                    void agir(() =>
                      api.post("/reservas/mesas/em-lote", {
                        id_salao: aberto.id,
                        quantidade: 1,
                        lugares: 2,
                      }),
                    )
                  }
                >
                  + mesa
                </button>
              </div>
            )
          }
        >
          {/* ---- a linha do próprio salão ---- */}
          {podeEditar && (
            <div className="mb-4 flex flex-wrap items-end gap-4 border-b border-linha2 pb-4">
              <Campo rotulo="Nome do salão" className="min-w-[220px] flex-1">
                <input
                  className="campo"
                  aria-label={`nome do salão ${aberto.nome}`}
                  defaultValue={aberto.nome}
                  key={`nome-${aberto.id}`}
                  onBlur={(e) =>
                    e.target.value.trim() &&
                    e.target.value.trim() !== aberto.nome &&
                    void agir(() =>
                      api.put(`/reservas/saloes/${aberto.id}`, {
                        nome: e.target.value.trim(),
                      }),
                    )
                  }
                />
              </Campo>
              <label className="flex items-center gap-2 pb-2 text-[14px]">
                <input
                  type="checkbox"
                  aria-label={`salão ${aberto.nome} ativo`}
                  checked={aberto.ativo}
                  onChange={(e) =>
                    void agir(() =>
                      api.put(`/reservas/saloes/${aberto.id}`, { ativo: e.target.checked }),
                    )
                  }
                />
                Atende
              </label>
              <div className="pb-2">
                {/* ⚠️ Só o salão VAZIO oferece excluir. Com mesa, o caminho é
                    desligar — e o servidor recusa de qualquer jeito. */}
                {minhas.length === 0 ? (
                  <button
                    className="link-acao link-acao-erro"
                    aria-label={`excluir salão ${aberto.nome}`}
                    onClick={() =>
                      void agir(async () => {
                        const r = await api.delete<{ message: string }>(
                          `/reservas/saloes/${aberto.id}`,
                        );
                        setAbaUrl("");
                        return r;
                      })
                    }
                  >
                    excluir salão
                  </button>
                ) : (
                  <span className="text-[12.5px] text-suave">
                    tem mesas — desligue em vez de excluir
                  </span>
                )}
              </div>
            </div>
          )}

          {lote && podeEditar && (
            <FormularioDeLote
              idSalao={aberto.id}
              ocupado={ocupado}
              aoCriar={(corpo) =>
                void agir(async () => {
                  const r = await api.post<{ message: string }>(
                    "/reservas/mesas/em-lote",
                    corpo,
                  );
                  setLote(false);
                  return r;
                })
              }
              aoFechar={() => setLote(false)}
            />
          )}

          {!minhas.length ? (
            <p className="px-1 py-6 text-center text-[14px] text-suave">
              Nenhuma mesa neste salão ainda. Use <b>+ várias mesas</b> para montar o salão
              de uma vez.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="tabela">
                <thead>
                  <tr>
                    <th className="min-w-[110px]">Mesa</th>
                    <th className="num w-[110px]">Lugares</th>
                    <th className="num w-[110px]">Máximo</th>
                    <th className="min-w-[150px]">Junta com</th>
                    <th className="w-[80px]">Ativa</th>
                    {podeEditar && <th className="w-[90px]"></th>}
                  </tr>
                </thead>
                <tbody>
                  {minhas.map((m) => (
                    <tr key={m.id} className={m.ativo && aberto.ativo ? "" : "text-suave"}>
                      <td>
                        <input
                          className="campo"
                          disabled={!podeEditar}
                          aria-label={`nome da mesa ${m.nome}`}
                          defaultValue={m.nome}
                          key={`mesa-${m.id}-${m.nome}`}
                          onBlur={(e) =>
                            e.target.value.trim() !== m.nome &&
                            void agir(() =>
                              api.put(`/reservas/mesas/${m.id}`, {
                                nome: e.target.value.trim(),
                              }),
                            )
                          }
                        />
                      </td>
                      {(["lugares", "capacidade_max"] as const).map((campo) => (
                        <td key={campo}>
                          <input
                            className="campo mono text-right"
                            type="number"
                            min={1}
                            disabled={!podeEditar}
                            aria-label={`${
                              campo === "lugares" ? "lugares" : "máximo"
                            } da mesa ${m.nome}`}
                            defaultValue={m[campo]}
                            key={`${campo}-${m.id}-${m[campo]}`}
                            onBlur={(e) =>
                              Number(e.target.value) !== m[campo] &&
                              void agir(() =>
                                api.put(`/reservas/mesas/${m.id}`, {
                                  [campo]: Number(e.target.value),
                                }),
                              )
                            }
                          />
                        </td>
                      ))}
                      <td>
                        <select
                          className="campo"
                          disabled={!podeEditar}
                          aria-label={`mesa que junta com ${m.nome}`}
                          value={m.junta_com ?? ""}
                          onChange={(e) =>
                            void agir(() =>
                              api.put(`/reservas/mesas/${m.id}`, {
                                junta_com: e.target.value ? Number(e.target.value) : null,
                              }),
                            )
                          }
                        >
                          <option value="">—</option>
                          {/* ⚠️ A junta NÃO se limita ao salão: a mesa da porta
                              da varanda encosta na do canto do principal. O que
                              a lista exclui é a própria mesa, e nada mais — mas
                              o nome do salão viaja junto, senão "03" sozinho não
                              diz de onde é. */}
                          {dados.mesas
                            .filter((x) => x.id !== m.id)
                            .map((x) => (
                              <option key={x.id} value={x.id}>
                                {x.nome}
                                {x.id_salao !== m.id_salao
                                  ? ` · ${dados.saloes.find((s) => s.id === x.id_salao)?.nome ?? ""}`
                                  : ""}
                              </option>
                            ))}
                        </select>
                      </td>
                      <td>
                        <input
                          type="checkbox"
                          disabled={!podeEditar}
                          aria-label={`mesa ${m.nome} ativa`}
                          checked={m.ativo}
                          onChange={(e) =>
                            void agir(() =>
                              api.put(`/reservas/mesas/${m.id}`, { ativo: e.target.checked }),
                            )
                          }
                        />
                      </td>
                      {podeEditar && (
                        <td className="text-right">
                          <button
                            className="link-acao link-acao-erro"
                            aria-label={`excluir mesa ${m.nome}`}
                            onClick={() =>
                              void agir(() => api.delete(`/reservas/mesas/${m.id}`))
                            }
                          >
                            excluir
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-3 text-[13px] text-suave">
            ⚠️ A junta vale nos dois sentidos: escolher aqui grava dos dois lados, e o par
            anterior é solto sozinho.
          </p>
        </Cartao>
      )}

      <p className="text-[13px] text-suave">
        A regra de disponibilidade — dado dia, hora e número de pessoas, o que dá para
        marcar — vem a seguir. <Etiqueta>em construção</Etiqueta>
      </p>
    </div>
  );
}

/**
 * Montar o salão de uma vez.
 *
 * 🔑 **É o trabalho real do cadastro, e acontece uma vez só**: no dia em que a
 * casa entra no sistema. Clicar "+ mesa" doze vezes e renomear cada uma é
 * exatamente quando ninguém tem paciência — e cadastro mal feito no primeiro dia
 * é o que faz a disponibilidade responder errado no segundo.
 */
function FormularioDeLote({
  idSalao,
  ocupado,
  aoCriar,
  aoFechar,
}: {
  idSalao: number;
  ocupado: boolean;
  aoCriar: (corpo: Record<string, unknown>) => void;
  aoFechar: () => void;
}) {
  const [quantidade, setQuantidade] = useState(4);
  const [lugares, setLugares] = useState(4);
  const [maximo, setMaximo] = useState(4);
  const [prefixo, setPrefixo] = useState("");

  return (
    <div className="mb-4 rounded-xl border border-linha2 bg-fundo2 p-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Campo rotulo="Quantas mesas" dica="até 50 de uma vez">
          <input
            className="campo mono text-right"
            type="number"
            min={1}
            max={50}
            aria-label="quantas mesas criar"
            value={quantidade}
            onChange={(e) => setQuantidade(Number(e.target.value))}
          />
        </Campo>
        <Campo rotulo="Lugares em cada" dica="o confortável">
          <input
            className="campo mono text-right"
            type="number"
            min={1}
            aria-label="lugares de cada mesa do lote"
            value={lugares}
            onChange={(e) => {
              const n = Number(e.target.value);
              setLugares(n);
              // ⚠️ O máximo acompanha enquanto ninguém o separou: quem não tem
              // cadeira extra não devia precisar mexer em dois campos.
              if (maximo < n) setMaximo(n);
            }}
          />
        </Campo>
        <Campo rotulo="Máximo em cada" dica="com a cadeira extra">
          <input
            className="campo mono text-right"
            type="number"
            min={1}
            aria-label="máximo de cada mesa do lote"
            value={maximo}
            onChange={(e) => setMaximo(Number(e.target.value))}
          />
        </Campo>
        <Campo rotulo="Prefixo (opcional)" dica='"V" dá V01, V02…'>
          <input
            className="campo"
            maxLength={6}
            aria-label="prefixo do nome das mesas"
            value={prefixo}
            onChange={(e) => setPrefixo(e.target.value)}
          />
        </Campo>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          className="btn btn-primario"
          disabled={ocupado || quantidade < 1 || maximo < lugares}
          onClick={() =>
            aoCriar({
              id_salao: idSalao,
              quantidade,
              lugares,
              capacidade_max: maximo,
              prefixo: prefixo.trim(),
            })
          }
        >
          Criar {quantidade} mesa{quantidade === 1 ? "" : "s"}
        </button>
        <button className="link-acao" onClick={aoFechar}>
          cancelar
        </button>
        {/* ⚠️ O nome é único por LOJA: o lote pula o que já existe em vez de
            recusar, e é justo dizer isso antes de a pessoa clicar. */}
        <span className="text-[12.5px] text-suave">
          A numeração começa no primeiro nome livre — mesas que já existem são puladas.
        </span>
      </div>
    </div>
  );
}
