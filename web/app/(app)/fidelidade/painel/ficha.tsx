"use client";

import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Confirmacao, Etiqueta, Modal } from "@/components/ui";
import {
  ajustarVencimento,
  darSelos,
  entregarPremio,
  fichaFidelidade,
  retirarSelos,
  type FichaFidelidade,
  type LancamentoDeSelos,
  type PremioDaFicha,
} from "@/lib/fidelidade";

/**
 * A ficha de um cliente no programa de fidelidade — tudo dele numa janela.
 *
 * 🔑 **Pedido do dono (27/09/2026):** *"verificar os selos, os resgates, a validade,
 * ajustar o vencimento, dar selos, visualizar tudo que diz respeito ao plano de
 * fidelidade em uma só tela."*
 * ⚠️ **Mexer é da gerência** (`fidelidade.configurar`): dar selo, tirar selo e esticar a
 * validade é dar benefício de graça. O caixa (`operar`) vê tudo e entrega o prêmio.
 */
const ORIGEM: Record<LancamentoDeSelos["origem"], string> = {
  QRCODE: "QR na mesa",
  CODIGO: "código do caixa",
  MANUAL: "dado à mão",
  VISITA: "visita",
};
const COR = { DISPONIVEL: "erva", USADO: "neutro", VENCIDO: "alerta" } as const;
const ROTULO = { DISPONIVEL: "disponível", USADO: "entregue", VENCIDO: "vencido" };

const dataBr = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—");
const hojeIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export default function FichaDoParticipante({
  idCliente,
  podeMexer,
  podeEntregar,
  aoFechar,
  aoMudar,
}: {
  idCliente: number;
  podeMexer: boolean;
  podeEntregar: boolean;
  aoFechar: () => void;
  aoMudar: () => void;
}) {
  const aviso = useAviso();
  const [f, setF] = useState<FichaFidelidade | null>(null);
  const [erro, setErro] = useState("");
  const [selos, setSelos] = useState(1);
  const [motivo, setMotivo] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [vencimento, setVencimento] = useState<{ p: PremioDaFicha; data: string } | null>(null);
  const [retirando, setRetirando] = useState<LancamentoDeSelos | null>(null);
  const [entregando, setEntregando] = useState<PremioDaFicha | null>(null);

  const carregar = useCallback(async () => {
    try {
      setF(await fichaFidelidade(idCliente));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar a ficha");
    }
  }, [idCliente]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function acao(fazer: () => Promise<{ message: string } | void>) {
    setOcupado(true);
    try {
      const r = await fazer();
      if (r && "message" in r) aviso.sucesso(r.message);
      await carregar();
      aoMudar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível");
    } finally {
      setOcupado(false);
    }
  }

  const c = f?.cartao;
  const cheios = Math.min(c?.no_cartao ?? 0, c?.visitas ?? 0);

  return (
    <Modal
      titulo={f ? f.cliente.nome : "Fidelidade"}
      descricao={f ? `Telefone ${f.cliente.telefone}` : undefined}
      aoFechar={aoFechar}
      largura="880px"
    >
      {erro ? (
        <Aviso tipo="erro">{erro}</Aviso>
      ) : !f || !c ? (
        <Carregando />
      ) : (
        <div className="flex flex-col gap-6">
          {/* ---- o cartão ---- */}
          <section className="flex flex-col gap-3">
            <h3 className="text-[15px] font-bold">Cartão atual</h3>
            <div className="flex flex-wrap gap-1.5" aria-label={`${c.no_cartao} de ${c.visitas} selos`}>
              {Array.from({ length: c.visitas }, (_, i) => (
                <span key={i}
                      className={`grid h-8 w-8 place-content-center rounded-full border-2 text-[12px] font-bold ${
                        i < cheios
                          ? "border-[var(--color-erva)] bg-[var(--color-erva)] text-white"
                          : "border-dashed border-[var(--color-linha)] text-suave"}`}>
                  {i < cheios ? "✓" : i + 1}
                </span>
              ))}
            </div>
            <p className="text-[14px]">
              <b className="mono">{c.no_cartao}</b> de {c.visitas} selos —{" "}
              {c.faltam ? `faltam ${c.faltam} para: ${c.premio}` : "cartão completo"}.
              <span className="block text-[12.5px] text-suave">
                Conta de {c.pontua}; o prêmio vale da visita seguinte, por {c.validade_dias} dias,
                de {c.consumo}.
              </span>
            </p>
            {podeMexer && (
              <div className="flex flex-wrap items-end gap-3 rounded-[10px] border border-[var(--color-linha)] p-3">
                <Campo rotulo="Dar selos">
                  <input className="campo mono w-[90px]" type="number" min={1} max={100}
                         value={selos} onChange={(e) => setSelos(Math.max(1, Number(e.target.value)))} />
                </Campo>
                <Campo rotulo="Motivo" className="min-w-[220px] flex-1">
                  <input className="campo" maxLength={200} value={motivo}
                         placeholder="Ex.: cortesia, visita não registrada no dia 20"
                         onChange={(e) => setMotivo(e.target.value)} />
                </Campo>
                <button className="btn btn-primario" aria-busy={ocupado}
                        disabled={ocupado || motivo.trim().length < 3}
                        onClick={() => void acao(async () => {
                          const r = await darSelos(idCliente, selos, motivo);
                          setMotivo("");
                          setSelos(1);
                          return r;
                        })}>
                  Lançar selos
                </button>
              </div>
            )}
          </section>

          {/* ---- os prêmios ---- */}
          <section className="flex flex-col gap-2">
            <h3 className="text-[15px] font-bold">Prêmios ({f.premios.length})</h3>
            {!f.premios.length ? (
              <p className="text-[13.5px] text-suave">Nenhum prêmio ainda.</p>
            ) : (
              <div className="grid-rolante">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Código</th>
                      <th>Prêmio</th>
                      <th className="num">Ganho</th>
                      <th className="num">Vale de</th>
                      <th className="num">Vence</th>
                      <th>Situação</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {f.premios.map((p) => (
                      <tr key={p.id} className={p.status === "DISPONIVEL" ? "" : "text-suave"}>
                        <td className="mono font-semibold">{p.codigo}</td>
                        <td>{p.premio}<span className="block text-[12px] text-suave">{p.consumo}</span></td>
                        <td className="num mono">{dataBr(p.emitido_em)}</td>
                        <td className="num mono">{dataBr(p.vale_de)}</td>
                        <td className="num mono">
                          {dataBr(p.vence_em)}
                          {p.vencimento_original && (
                            <span className="block text-[11.5px] text-suave">
                              era {dataBr(p.vencimento_original)}
                            </span>
                          )}
                        </td>
                        <td>
                          <Etiqueta cor={COR[p.status]}>{ROTULO[p.status]}</Etiqueta>
                          {p.usado_em && (
                            <span className="block text-[12px] text-suave">
                              {dataBr(p.usado_em)}{p.loja_uso ? ` · ${p.loja_uso}` : ""}
                              {p.entregue_por ? ` · ${p.entregue_por}` : ""}
                            </span>
                          )}
                        </td>
                        <td className="whitespace-nowrap">
                          <span className="flex flex-col items-end gap-1">
                            {podeEntregar && p.pode_hoje && (
                              <button className="link-acao" onClick={() => setEntregando(p)}>entregar</button>
                            )}
                            {podeMexer && p.status !== "USADO" && (
                              <button className="link-acao"
                                      onClick={() => setVencimento({ p, data: p.vence_em.slice(0, 10) })}>
                                ajustar vencimento
                              </button>
                            )}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* ---- os selos, lançamento a lançamento ---- */}
          <section className="flex flex-col gap-2">
            <h3 className="text-[15px] font-bold">Selos lançados ({f.visitas.length})</h3>
            {!f.visitas.length ? (
              <p className="text-[13.5px] text-suave">Nenhum selo ainda.</p>
            ) : (
              <div className="grid-rolante">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th className="num">Data</th>
                      <th className="num">Selos</th>
                      <th>Origem</th>
                      <th>Loja</th>
                      <th>Cartão</th>
                      {podeMexer && <th />}
                    </tr>
                  </thead>
                  <tbody>
                    {f.visitas.map((v) => (
                      <tr key={v.id}>
                        <td className="num mono">{dataBr(v.data)}</td>
                        <td className="num mono">{v.selos}</td>
                        <td>
                          {ORIGEM[v.origem]}
                          {v.parte > 0 && v.origem !== "MANUAL" && (
                            <span className="text-[12px] text-suave"> (sobra)</span>
                          )}
                          {v.motivo && <span className="block text-[12px] text-suave">{v.motivo}</span>}
                          {v.concedido_por && (
                            <span className="block text-[12px] text-suave">por {v.concedido_por}</span>
                          )}
                        </td>
                        <td className="text-[13px]">{v.loja ?? "—"}</td>
                        <td className="text-[13px]">
                          {v.premio_codigo ? <span className="mono">prêmio {v.premio_codigo}</span> : "atual"}
                        </td>
                        {podeMexer && (
                          <td>
                            {!v.id_premio && (
                              <button className="link-acao link-acao-erro" onClick={() => setRetirando(v)}>
                                retirar
                              </button>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {!!f.pedidos.length && (
            <section className="flex flex-col gap-2">
              <h3 className="text-[15px] font-bold">Pedidos de código no caixa</h3>
              <ul className="text-[13px]">
                {f.pedidos.map((p) => (
                  <li key={p.id} className="border-b border-[var(--color-linha)] py-1.5">
                    {dataBr(p.criada_em)} · {p.status.toLowerCase()} · {p.selos} selo(s)
                    {p.tentativas > 0 && ` · ${p.tentativas} tentativa(s) errada(s)`}
                    {p.loja && ` · ${p.loja}`}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}

      {vencimento && (
        <Confirmacao
          titulo={`Vencimento do prêmio ${vencimento.p.codigo}`}
          rotuloConfirmar="Gravar"
          ocupado={ocupado}
          aoCancelar={() => setVencimento(null)}
          aoConfirmar={() => {
            const alvo = vencimento;
            setVencimento(null);
            void acao(() => ajustarVencimento(alvo.p.id, alvo.data));
          }}
        >
          <Campo rotulo="Vence em" dica={`vale a partir de ${dataBr(vencimento.p.vale_de)}`}>
            <input className="campo mono" type="date" min={vencimento.p.vale_de.slice(0, 10)}
                   value={vencimento.data}
                   onChange={(e) => setVencimento({ ...vencimento, data: e.target.value || hojeIso() })} />
          </Campo>
          {vencimento.p.status === "VENCIDO" && (
            <p className="mt-2 text-[13px] text-suave">
              Este prêmio já venceu — uma data futura o faz valer de novo.
            </p>
          )}
        </Confirmacao>
      )}

      {retirando && (
        <Confirmacao
          titulo="Retirar estes selos?"
          perigo
          rotuloConfirmar="Sim, retirar"
          ocupado={ocupado}
          aoCancelar={() => setRetirando(null)}
          aoConfirmar={() => {
            const alvo = retirando;
            setRetirando(null);
            void acao(() => retirarSelos(alvo.id));
          }}
        >
          <p>
            <b>{retirando.selos} selo(s)</b> de {dataBr(retirando.data)} ({ORIGEM[retirando.origem]})
            saem do cartão. Use para desfazer um lançamento feito por engano.
          </p>
        </Confirmacao>
      )}

      {entregando && (
        <Confirmacao
          titulo="Entregar este prêmio?"
          rotuloConfirmar="Sim, entregar"
          ocupado={ocupado}
          aoCancelar={() => setEntregando(null)}
          aoConfirmar={() => {
            const alvo = entregando;
            setEntregando(null);
            void acao(() => entregarPremio(alvo.codigo));
          }}
        >
          <p>
            <b>{entregando.premio}</b> — código <span className="mono font-semibold">{entregando.codigo}</span>.
            Depois de entregue, o prêmio não vale de novo.
          </p>
        </Confirmacao>
      )}
    </Modal>
  );
}
