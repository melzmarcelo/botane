"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Local } from "@/lib/cadastros";
import { Aviso, Cartao } from "@/components/ui";
import { qtd } from "@/lib/numeros";

/**
 * Para onde esta receita vai — e quanto ela rende em cada destino.
 *
 * 🔑 **Pedido do dono (12/09/2026):** *"a mesma ficha pode ter processos
 * diferentes. Vamos fazer a massa de pizza e estocar para servir como insumo
 * para pizza, mas podemos ter produção de massa de pizza que vai para a vitrine.
 * Dentro da ficha podemos ter os locais e informar rendimentos e porções por
 * local, e ao programar a produção seleciona qual local será produzido"*. E o
 * rendimento muda de verdade: a da vitrine vai ao forno e perde água.
 *
 * ⚠️ **É OVERRIDE, não substituição.** Sem destino nenhum aqui, vale o
 * rendimento da ficha — que é o caso de quase toda receita. É isso que faz o
 * recurso não mexer em nenhuma produção existente.
 *
 * ⚠️ **O rendimento DIVIDE o consumo** (`lotes = quantidade ÷ rendimento`), e o
 * cartão diz isso em voz alta: produzir 10 para um destino que rende 8 consome
 * uma receita e um quarto. Quem não souber disso vai achar que gastou um lote.
 */
type Destino = {
  id_local: number;
  local?: string;
  rendimento_qtd: string;
  porcoes: string;
  porcao_qtd: string;
  observacao: string;
};

export default function DestinosDaFicha({
  idFicha,
  rendimentoDaFicha,
  um,
  editavel,
  aoGravar,
}: {
  idFicha: number;
  rendimentoDaFicha: number;
  um: string | null;
  editavel: boolean;
  /** Para a página recarregar a ficha: o cartão grava por conta própria. */
  aoGravar?: () => void;
}) {
  const aviso = useAviso();
  const [locais, setLocais] = useState<Local[]>([]);
  const [linhas, setLinhas] = useState<Destino[] | null>(null);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get<Local[]>("/locais"),
      api.get<{ locais?: Destino[] }>(`/fichas/${idFicha}`),
    ])
      .then(([ls, f]) => {
        setLocais(ls);
        setLinhas(
          (f.locais ?? []).map((d) => ({
            id_local: d.id_local,
            local: d.local,
            rendimento_qtd: String(d.rendimento_qtd ?? ""),
            porcoes: d.porcoes === null || d.porcoes === undefined ? "" : String(d.porcoes),
            porcao_qtd:
              d.porcao_qtd === null || d.porcao_qtd === undefined ? "" : String(d.porcao_qtd),
            observacao: d.observacao ?? "",
          })),
        );
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
  }, [idFicha]);

  const num = (t: string) => {
    const n = Number((t || "").replace(",", "."));
    return Number.isFinite(n) && n > 0 ? n : null;
  };

  async function salvar() {
    setSalvando(true);
    setErro("");
    try {
      const itens = (linhas ?? [])
        .filter((l) => l.id_local && num(l.rendimento_qtd))
        .map((l) => ({
          id_local: Number(l.id_local),
          rendimento_qtd: num(l.rendimento_qtd),
          porcoes: num(l.porcoes),
          porcao_qtd: num(l.porcao_qtd),
          observacao: l.observacao || null,
        }));
      const r = await api.put<{ message: string }>(`/fichas/${idFicha}/locais`, { itens });
      aviso.sucesso(r.message);
      aoGravar?.();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível gravar");
    } finally {
      setSalvando(false);
    }
  }

  function mudar(i: number, campo: keyof Destino, valor: string) {
    setLinhas((l) => (l ?? []).map((x, j) => (j === i ? { ...x, [campo]: valor } : x)));
  }

  if (!linhas) return null;
  const usados = new Set(linhas.map((l) => Number(l.id_local)));

  return (
    <Cartao
      titulo="Destinos e rendimento"
      descricao={
        `Sem destino aqui, a receita rende ${qtd(rendimentoDaFicha)} ${um ?? ""} em qualquer ` +
        `prateleira. Acrescente um destino quando o processo muda o rendimento — a massa que ` +
        `vai ao forno para a vitrine não rende o mesmo que a que vai crua para a câmara.`
      }
      acao={
        editavel && (
          <button
            type="button"
            className="btn btn-primario"
            onClick={salvar}
            disabled={salvando}
          >
            {salvando ? "Gravando…" : "Gravar destinos"}
          </button>
        )
      }
    >
      {erro && (
        <div className="mb-4">
          <Aviso tipo="erro">{erro}</Aviso>
        </div>
      )}

      {linhas.length === 0 ? (
        <p className="text-[14px] text-suave">
          Nenhum destino com rendimento próprio: vale o da ficha.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="tabela">
            <thead>
              <tr>
                <th className="min-w-[170px]">Prateleira</th>
                <th className="num w-[130px] min-w-[130px]">Rende ({um ?? "un."})</th>
                <th className="num w-[110px] min-w-[110px]">Porções</th>
                <th className="num w-[130px] min-w-[130px]">Cada porção</th>
                <th className="min-w-[150px]">Observação</th>
                {editavel && <th className="w-[80px]"></th>}
              </tr>
            </thead>
            <tbody>
              {linhas.map((l, i) => (
                <tr key={i}>
                  <td>
                    <select
                      className="campo"
                      disabled={!editavel}
                      aria-label={`prateleira do destino ${i + 1}`}
                      value={l.id_local || ""}
                      onChange={(e) => mudar(i, "id_local", e.target.value)}
                    >
                      <option value="">—</option>
                      {locais
                        .filter((x) => x.ativo && (!usados.has(x.id) || x.id === Number(l.id_local)))
                        .map((x) => (
                          <option key={x.id} value={x.id}>
                            {x.nome}
                          </option>
                        ))}
                    </select>
                  </td>
                  <td>
                    <input
                      className="campo mono text-right"
                      inputMode="decimal"
                      disabled={!editavel}
                      aria-label={`rendimento do destino ${i + 1}`}
                      value={l.rendimento_qtd}
                      onChange={(e) => mudar(i, "rendimento_qtd", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="campo mono text-right"
                      inputMode="decimal"
                      disabled={!editavel}
                      aria-label={`porções do destino ${i + 1}`}
                      value={l.porcoes}
                      onChange={(e) => mudar(i, "porcoes", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="campo mono text-right"
                      inputMode="decimal"
                      disabled={!editavel}
                      aria-label={`tamanho da porção do destino ${i + 1}`}
                      value={l.porcao_qtd}
                      onChange={(e) => mudar(i, "porcao_qtd", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="campo"
                      disabled={!editavel}
                      placeholder="assada, porcionada…"
                      value={l.observacao}
                      onChange={(e) => mudar(i, "observacao", e.target.value)}
                    />
                  </td>
                  {editavel && (
                    <td className="text-right">
                      <button
                        type="button"
                        className="link-acao link-acao-erro"
                        aria-label={`remover destino ${i + 1}`}
                        onClick={() => setLinhas(linhas.filter((_x, j) => j !== i))}
                      >
                        remover
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editavel && (
        <div className="mt-3">
          <button
            type="button"
            className="btn btn-secundario"
            onClick={() =>
              setLinhas([
                ...linhas,
                {
                  id_local: 0,
                  rendimento_qtd: String(rendimentoDaFicha),
                  porcoes: "",
                  porcao_qtd: "",
                  observacao: "",
                },
              ])
            }
          >
            + destino
          </button>
        </div>
      )}

      <p className="mt-4 text-[13px] leading-snug text-suave">
        ⚠️ O rendimento <b>divide o consumo</b>: produzir 10 para um destino que rende 8 gasta
        uma receita e um quarto. Ao programar a produção você escolhe a prateleira, e a tela diz
        qual rendimento está valendo.
      </p>
    </Cartao>
  );
}
