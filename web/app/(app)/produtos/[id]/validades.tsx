"use client";

import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao } from "@/components/ui";
import {
  CONSERVACOES, EVENTOS, salvarValidades, validades, type Regra,
} from "@/lib/etiquetas";

/**
 * Quanto este produto dura depois de produzido, aberto ou descongelado.
 *
 * 🔑 **Pedido do dono (06/10/2026):** *"a configuração da validade dos produtos
 * está nas configurações em etiquetas. Hoje já temos os dias de validade no
 * cadastro de produto. Podemos transferir esta configuração para o cadastro de
 * produto, aí deixamos tudo centralizado no produto."* As regras moravam em
 * Etiquetas → Configuração, com um campo de busca para escolher o produto —
 * enquanto o "Validade (dias)" do mesmo produto morava aqui. Duas telas para a
 * mesma pergunta.
 *
 * 🔑 **O campo "Validade (dias)" continua sendo o número simples**, e é ele que
 * vale para a PRODUÇÃO quando não há regra — por isso o cartão o mostra e diz a
 * ordem. As regras são para o que um número só não diz: o mesmo molho dura 3 dias
 * refrigerado e 60 congelado; o creme de leite, 3 dias depois de aberto.
 *
 * ⚠️ **Tem Salvar próprio**, separado do Salvar do produto: as regras são outra
 * tabela, gravada por outra rota. Salvar o cadastro não as toca, e salvar as
 * regras não exige passar pela validação do formulário inteiro.
 *
 * ⚠️ **Um padrão por evento** — é a conservação que a bancada já encontra
 * marcada ao imprimir a etiqueta. O servidor garante (sem marcado, a primeira do
 * evento vira o padrão).
 *
 * ⚠️ **O campo "Dura" pode ficar VAZIO enquanto se digita** (06/10/2026, relato do
 * dono: *"ao apagar para informar outro valor, vira 1 e não deixa apagar"*). A
 * primeira versão forçava o mínimo a cada tecla: apagar o 3 virava 1 na hora, e
 * para escrever 15 era preciso selecionar o texto. Agora o vazio é aceito na
 * digitação, o campo seleciona tudo ao receber o foco, e quem cobra o prazo é o
 * Salvar — que não liga enquanto houver linha sem número.
 */
export default function ValidadesDoProduto({
  idProduto,
  validadeDias,
  podeEditar,
}: {
  idProduto: number;
  /** O "Validade (dias)" do formulário, como está na tela agora. */
  validadeDias: string;
  podeEditar: boolean;
}) {
  const aviso = useAviso();
  const [regras, setRegras] = useState<Regra[] | null>(null);
  const [gravadas, setGravadas] = useState("[]");
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    validades(idProduto)
      .then((r) => {
        setRegras(r);
        setGravadas(JSON.stringify(r));
      })
      // Sem permissão de ver etiquetas o cartão não tem o que mostrar — e diz.
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar as validades"));
  }, [idProduto]);

  const mexido = regras !== null && JSON.stringify(regras) !== gravadas;
  // Prazo vazio vale zero aqui dentro; nenhuma linha assim vai ao servidor.
  const semPrazo = (regras ?? []).some((r) => !(r.prazo >= 1));

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
        setRegras([...(regras ?? []),
          { evento: e.v, conservacao: c.v, prazo: 3, unidade: "DIAS", padrao: primeira }]);
        return;
      }
    }
  }

  async function salvar() {
    if (!regras) return;
    setOcupado(true);
    try {
      const r = await salvarValidades(idProduto, regras);
      setRegras(r.regras);
      setGravadas(JSON.stringify(r.regras));
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar as validades");
    } finally {
      setOcupado(false);
    }
  }

  const temRegraDeProducao = (regras ?? []).some((r) => r.evento === "PRODUCAO");

  return (
    <Cartao
      titulo="Validade por situação"
      descricao="Depois de produzir, abrir ou descongelar: quanto dura em cada conservação. É o que a etiqueta usa."
    >
      {erro ? (
        <Aviso tipo="info">{erro}</Aviso>
      ) : !regras ? (
        <Carregando />
      ) : (
        <div className="flex flex-col gap-4">
          {/* A ordem de quem responde, dita onde a pessoa está decidindo. */}
          <p className="text-[13.5px] leading-snug text-suave">
            {temRegraDeProducao ? (
              <>Na produção vale a regra abaixo; o campo <b>Validade (dias)</b> fica como reserva.</>
            ) : validadeDias ? (
              <>
                Sem regra de produção, a etiqueta e o lote usam os <b>{validadeDias} dia(s)</b> do
                campo <b>Validade (dias)</b>, acima.
              </>
            ) : (
              <>
                Sem regra e sem <b>Validade (dias)</b>, a etiqueta pede a data na hora de
                imprimir.
              </>
            )}{" "}
            Abertura e descongelamento só têm prazo com regra.
          </p>

          {regras.length > 0 && (
            <div className="grid-rolante">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Depois de</th>
                    <th>Conservação</th>
                    <th className="w-[120px]">Dura</th>
                    <th className="w-[110px]" />
                    <th>Padrão</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {regras.map((r, i) => (
                    <tr key={i}>
                      <td>
                        <select className="campo" disabled={!podeEditar} value={r.evento}
                                aria-label="evento da regra"
                                onChange={(e) => mudar(i, { evento: e.target.value as Regra["evento"] })}>
                          {EVENTOS.map((x) => <option key={x.v} value={x.v}>{x.r}</option>)}
                        </select>
                      </td>
                      <td>
                        <select className="campo" disabled={!podeEditar} value={r.conservacao}
                                aria-label="conservação da regra"
                                onChange={(e) =>
                                  mudar(i, { conservacao: e.target.value as Regra["conservacao"] })}>
                          {CONSERVACOES.map((x) => <option key={x.v} value={x.v}>{x.r}</option>)}
                        </select>
                      </td>
                      <td>
                        {/* ⚠️ Texto com teclado numérico, não `type="number"`: assim o
                            campo aceita ficar vazio no meio da digitação e não ganha
                            setinhas. Só dígitos, até quatro. */}
                        <input className="campo mono min-w-[84px] text-right" inputMode="numeric"
                               maxLength={4} disabled={!podeEditar}
                               aria-label="prazo da regra"
                               aria-invalid={!(r.prazo >= 1)}
                               value={r.prazo >= 1 ? String(r.prazo) : ""}
                               onFocus={(e) => e.currentTarget.select()}
                               onChange={(e) =>
                                 mudar(i, { prazo: Number(e.target.value.replace(/\D/g, "").slice(0, 4)) || 0 })} />
                      </td>
                      <td>
                        <select className="campo" disabled={!podeEditar} value={r.unidade}
                                aria-label="unidade do prazo"
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
                          <button type="button" className="link-acao"
                                  onClick={() => setRegras(regras.filter((_, j) => j !== i))}>
                            remover
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {podeEditar && (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <button type="button" className="btn btn-secundario" onClick={adicionar}>
                + Regra
              </button>
              <span className="flex items-center gap-3">
                {semPrazo ? (
                  <span className="text-[12.5px] text-erro">informe quanto dura em cada linha</span>
                ) : (
                  mexido && <span className="text-[12.5px] text-alerta">alterações não salvas</span>
                )}
                <button type="button" className="btn btn-primario"
                        disabled={ocupado || !mexido || semPrazo}
                        aria-busy={ocupado} onClick={() => void salvar()}>
                  {ocupado ? "…" : "Salvar validades"}
                </button>
              </span>
            </div>
          )}
        </div>
      )}
    </Cartao>
  );
}
