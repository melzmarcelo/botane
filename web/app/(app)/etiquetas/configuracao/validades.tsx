"use client";

import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BuscaCadastro from "@/components/busca-cadastro";
import { Campo, Cartao, Vazio } from "@/components/ui";
import { fonteProdutos } from "@/lib/busca-cadastro";
import {
  CONSERVACOES, EVENTOS, salvarValidades, validades, type Regra,
} from "@/lib/etiquetas";

/**
 * As regras de UM produto: cada linha é "depois de <evento>, <conservação>, dura N".
 *
 * ⚠️ **Um padrão por evento** — é a conservação que a bancada já encontra marcada. O
 * servidor garante (sem marcado, a primeira do evento vira o padrão).
 */
const PRODUTOS = fonteProdutos();

export default function ValidadesDoProduto({
  produto, aoProduto, podeEditar, aoSalvar,
}: {
  produto: { id: number; rotulo: string } | null;
  aoProduto: (p: { id: number; rotulo: string } | null) => void;
  podeEditar: boolean;
  aoSalvar: () => void;
}) {
  const aviso = useAviso();
  const [regras, setRegras] = useState<Regra[] | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    if (!produto) return setRegras(null);
    validades(produto.id).then(setRegras).catch(() => setRegras([]));
  }, [produto]);

  const mudar = (i: number, parte: Partial<Regra>) =>
    setRegras((rs) => (rs ?? []).map((r, j) => {
      if (j === i) return { ...r, ...parte };
      // Marcar um padrão desmarca os outros do mesmo evento.
      if (parte.padrao && r.evento === (rs ?? [])[i].evento) return { ...r, padrao: false };
      return r;
    }));

  function adicionar() {
    const usados = new Set((regras ?? []).map((r) => `${r.evento}/${r.conservacao}`));
    for (const e of EVENTOS) for (const c of CONSERVACOES) {
      if (!usados.has(`${e.v}/${c.v}`)) {
        const primeira = !(regras ?? []).some((r) => r.evento === e.v);
        setRegras([...(regras ?? []), { evento: e.v, conservacao: c.v, prazo: 3, unidade: "DIAS", padrao: primeira }]);
        return;
      }
    }
  }

  async function salvar() {
    if (!produto || !regras) return;
    setOcupado(true);
    try {
      const r = await salvarValidades(produto.id, regras);
      setRegras(r.regras);
      aviso.sucesso(r.message);
      aoSalvar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Cartao titulo="Validade por produto"
            descricao="Depois de produzir, abrir ou descongelar: quanto dura em cada conservação.">
      <div className="flex flex-col gap-4">
        <Campo rotulo="Produto">
          <BuscaCadastro fonte={PRODUTOS} selecionado={produto}
                         aoEscolher={(i) => aoProduto(i ? { id: i.id, rotulo: i.nome } : null)} />
        </Campo>
        {produto && regras && (regras.length === 0 ? (
          <Vazio>Sem regra: a produção usa a validade do cadastro do produto, e a abertura pede a data.</Vazio>
        ) : (
          <div className="grid-rolante">
            <table className="tabela">
              <thead>
                <tr><th>Evento</th><th>Conservação</th><th className="w-[90px]">Dura</th><th className="w-[110px]" /><th>Padrão</th><th /></tr>
              </thead>
              <tbody>
                {regras.map((r, i) => (
                  <tr key={i}>
                    <td>
                      <select className="campo" disabled={!podeEditar} value={r.evento}
                              onChange={(e) => mudar(i, { evento: e.target.value as Regra["evento"] })}>
                        {EVENTOS.map((x) => <option key={x.v} value={x.v}>{x.r}</option>)}
                      </select>
                    </td>
                    <td>
                      <select className="campo" disabled={!podeEditar} value={r.conservacao}
                              onChange={(e) => mudar(i, { conservacao: e.target.value as Regra["conservacao"] })}>
                        {CONSERVACOES.map((x) => <option key={x.v} value={x.v}>{x.r}</option>)}
                      </select>
                    </td>
                    <td>
                      <input className="campo mono" type="number" min={1} disabled={!podeEditar} value={r.prazo}
                             onChange={(e) => mudar(i, { prazo: Math.max(1, Number(e.target.value) || 1) })} />
                    </td>
                    <td>
                      <select className="campo" disabled={!podeEditar} value={r.unidade}
                              onChange={(e) => mudar(i, { unidade: e.target.value as Regra["unidade"] })}>
                        <option value="DIAS">dias</option>
                        <option value="HORAS">horas</option>
                      </select>
                    </td>
                    <td className="text-center">
                      <input type="radio" name={`padrao-${r.evento}`} disabled={!podeEditar}
                             checked={r.padrao} onChange={() => mudar(i, { padrao: true })}
                             aria-label="conservação padrão do evento" />
                    </td>
                    <td className="text-right">
                      {podeEditar && (
                        <button className="link-acao" onClick={() => setRegras(regras.filter((_, j) => j !== i))}>
                          remover
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
        {produto && regras && podeEditar && (
          <div className="flex justify-between gap-2">
            <button className="btn btn-secundario" onClick={adicionar}>+ Regra</button>
            <button className="btn btn-primario" disabled={ocupado} aria-busy={ocupado}
                    onClick={() => void salvar()}>
              {ocupado ? "…" : "Salvar validades"}
            </button>
          </div>
        )}
      </div>
    </Cartao>
  );
}
