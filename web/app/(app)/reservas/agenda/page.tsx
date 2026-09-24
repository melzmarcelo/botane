"use client";

import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Cartao, Confirmacao, Etiqueta } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { agendaDoDia, mudarStatus, type Agenda, type Reserva } from "@/lib/reservas";
import { useSessao } from "@/lib/sessao";
import ExplicaTela from "@/components/explica-tela";

import CalendarioDoMes, { maiuscula, mesDe } from "./calendario";
import DetalheDaReserva from "./detalhe";
import { NovaReserva, Remarcar } from "./formularios";
import LinhaDoTempo from "./linha-do-tempo";
import { ADIANTE, COR, ROTULO, podeRemarcar } from "./status";

/**
 * A agenda — o mês no calendário, o dia por horário, e cada reserva.
 *
 * 🔑 **Pedido do dono (24/09/2026):** *"na agenda de reservas, ter uma visão de
 * calendário, onde o usuário pode ter uma visão geral do que está reservado, e aí
 * clicar no dia, dá uma visão mais macro daquele dia, e aí pode visualizar a
 * reserva."* Três níveis: `visao=mes` (o calendário), `visao=dia` com a linha
 * do tempo (ou a lista, que era a tela de antes), e o detalhe da reserva.
 * ⚠️ **Tudo no ENDEREÇO** (`useEstadoNaUrl`): o F5 e o voltar do navegador
 * devolvem a pessoa ao mês e ao dia em que ela estava.
 *
 * 🔑 **Quem decide se cabe é o SERVIDOR**, sempre. A lista de horários vem de
 * `/reservas/disponibilidade`, que roda a mesma regra que a gravação vai rodar.
 *
 * ⚠️ **A reserva não se apaga: muda de status.** Cancelada é um fato, e sumir
 * com a linha levaria junto a resposta para "por que a mesa ficou vazia naquele
 * sábado".
 */

/** A data de HOJE no relógio de quem usa. ⚠️ Era `toISOString()`, que é UTC: das
 *  21h à meia-noite a agenda abria no dia seguinte. */
const hoje = () => {
  const d = new Date();
  return `${mesDe(d)}-${String(d.getDate()).padStart(2, "0")}`;
};

export default function AgendaDoDia() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const [visao, setVisao] = useEstadoNaUrl<string>("visao", "mes", { atraso: 0 });
  const [mes, setMes] = useEstadoNaUrl<string>("mes", mesDe(new Date()), { atraso: 0 });
  const [dia, setDia] = useEstadoNaUrl<string>("dia", hoje(), { atraso: 0 });
  const [modo, setModo] = useEstadoNaUrl<string>("modo", "tempo", { atraso: 0 });
  const [agenda, setAgenda] = useState<Agenda | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [marcando, setMarcando] = useState(false);
  /** A reserva aberta no detalhe — pelo ID, para sobreviver ao recarregar. */
  const [aberta, setAberta] = useState<number | null>(null);

  const carregar = useCallback(async () => {
    if (visao !== "dia") return;
    try {
      setAgenda(await agendaDoDia(dia));
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar a agenda");
    }
  }, [dia, visao]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  /** O que ainda precisa de confirmação antes de acontecer.
   *
   * ⚠️ **Nunca `window.confirm`.** É a caixa do NAVEGADOR: fonte de sistema,
   * botão em inglês e nenhuma chance de explicar o que a ação faz. */
  const [confirmar, setConfirmar] = useState<
    { r: Reserva; para: string; rotulo: string } | null
  >(null);
  /** A reserva que está sendo passada para outro dia, hora ou tamanho. */
  const [remarcando, setRemarcando] = useState<Reserva | null>(null);

  async function mudar(r: Reserva, para: string, rotulo: string) {
    // 🔑 Só o que não se desfaz pergunta. "Chegou" e "encerrar" são passos
    // normais do atendimento: pedir confirmação neles ensinaria a clicar em
    // "sim" sem ler, e aí a pergunta que importa também passaria batida.
    if ((para === "CANCELADA" || para === "NAO_COMPARECEU") && !confirmar) {
      setConfirmar({ r, para, rotulo });
      return;
    }
    setConfirmar(null);
    setOcupado(true);
    try {
      const resposta = await mudarStatus(r.id, para);
      aviso.sucesso(resposta.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível mudar o status");
      await carregar();
    } finally {
      setOcupado(false);
    }
  }

  const abrirDia = (d: string) => {
    setDia(d);
    setMes(d.slice(0, 7));
    setVisao("dia");
  };

  // ------------------------------------------------------------------ o mês
  if (visao !== "dia") {
    return (
      <div className="flex flex-col gap-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="titulo">Agenda</h1>
            <ExplicaTela>
              O mês de relance: quantas reservas e pessoas em cada dia, e o que ainda aguarda
              confirmação. Clique num dia para ver os horários.
            </ExplicaTela>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn btn-secundario" onClick={() => setMes(mesDe(new Date()))}>
              este mês
            </button>
            <button className="btn btn-primario" onClick={() => abrirDia(hoje())}>
              Abrir hoje
            </button>
          </div>
        </div>
        <CalendarioDoMes mes={mes} hoje={hoje()} aoMudarMes={setMes} aoEscolherDia={abrirDia} />
      </div>
    );
  }

  // ------------------------------------------------------------------- o dia
  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!agenda) return <Carregando />;

  const podeEditar = pode("reservas.editar");
  const reservaAberta = agenda.reservas.find((r) => r.id === aberta) ?? null;
  const nomeDoDia = maiuscula(new Date(`${dia}T12:00`).toLocaleDateString("pt-BR", {
    weekday: "long", day: "2-digit", month: "long",
  }));

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          {/* 🔑 A volta ao calendário cai no MÊS deste dia, não no de hoje. */}
          <button
            type="button"
            className="link-acao mb-1 text-[13px]"
            onClick={() => {
              setMes(dia.slice(0, 7));
              setVisao("mes");
            }}
          >
            ‹ calendário
          </button>
          <h1 className="titulo">{nomeDoDia}</h1>
          <ExplicaTela>
            Quem vem, quando, e em que mesa. A casa decide a mesa — o cliente reserva lugar.
          </ExplicaTela>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <Campo rotulo="Dia">
            <input
              className="campo mono"
              type="date"
              aria-label="dia da agenda"
              value={dia}
              onChange={(e) => setDia(e.target.value || hoje())}
            />
          </Campo>
          <button className="btn btn-secundario" onClick={() => setDia(hoje())}>
            hoje
          </button>
          {podeEditar && agenda.aberta && !agenda.bloqueio && (
            <button className="btn btn-primario" onClick={() => setMarcando((v) => !v)}>
              Nova reserva
            </button>
          )}
        </div>
      </div>

      {agenda.bloqueio && (
        <Aviso tipo="erro">
          A casa não recebe neste dia: <b>{agenda.bloqueio}</b>. As reservas já marcadas
          continuam abaixo — é por elas que a casa sabe para quem ligar.
        </Aviso>
      )}
      {!agenda.aberta && !agenda.bloqueio && (
        <Aviso tipo="info">
          A casa não atende neste dia da semana. Isso se muda em Portal de Clientes → Configuração.
        </Aviso>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          { n: agenda.ativas, r: "reservas ativas" },
          { n: agenda.esperados, r: "pessoas esperadas" },
          { n: agenda.lugares, r: "lugares no salão" },
        ].map((t) => (
          <div key={t.r} className="cartao px-4 py-3">
            <b className="mono block text-[26px] leading-none">{t.n}</b>
            <span className="text-[12.5px] text-suave">{t.r}</span>
          </div>
        ))}
      </div>

      {marcando && podeEditar && (
        <NovaReserva
          dia={dia}
          aoFechar={() => setMarcando(false)}
          aoMarcar={async () => {
            setMarcando(false);
            await carregar();
          }}
        />
      )}

      {remarcando && (
        <Remarcar
          reserva={remarcando}
          diaAtual={dia}
          aoFechar={() => setRemarcando(null)}
          aoRemarcar={async () => {
            setRemarcando(null);
            await carregar();
          }}
        />
      )}

      {reservaAberta && !confirmar && !remarcando && (
        <DetalheDaReserva
          reserva={reservaAberta}
          dia={dia}
          podeEditar={podeEditar}
          ocupado={ocupado}
          aoMudar={(r, para, rotulo) => void mudar(r, para, rotulo)}
          aoRemarcar={(r) => {
            setAberta(null);
            setRemarcando(r);
          }}
          aoFechar={() => setAberta(null)}
        />
      )}

      {confirmar && (
        <Confirmacao
          titulo={
            confirmar.para === "CANCELADA" ? "Cancelar esta reserva?" : "Marcar como não veio?"
          }
          perigo
          rotuloConfirmar={confirmar.para === "CANCELADA" ? "Sim, cancelar" : "Sim, não veio"}
          ocupado={ocupado}
          aoConfirmar={() => void mudar(confirmar.r, confirmar.para, confirmar.rotulo)}
          aoCancelar={() => setConfirmar(null)}
        >
          <p>
            <b>{confirmar.r.nome}</b>, {confirmar.r.pessoas} pessoa
            {confirmar.r.pessoas === 1 ? "" : "s"} às {confirmar.r.hora}
            {confirmar.r.mesas ? ` na mesa ${confirmar.r.mesas}` : ""}.
          </p>
          {/* ⚠️ A reserva NÃO some: ela muda de status. Dizer isso aqui evita a
              hesitação de quem teme apagar o histórico do dia. */}
          <p className="mt-2 text-suave">
            A mesa volta a ficar livre na hora, e a reserva continua na agenda com a nova
            situação — ela não é apagada.
          </p>
        </Confirmacao>
      )}

      <Cartao
        titulo={`Reservas de ${dia.split("-").reverse().join("/")}`}
        acao={
          // 🔑 **A linha do tempo é o padrão; a lista continua a um clique.** A
          // lista é a tela de antes, com as ações na linha — quem já trabalhava
          // nela não perde nada.
          <div className="flex gap-1" role="tablist" aria-label="como ver o dia">
            {[
              { v: "tempo", r: "Linha do tempo" },
              { v: "lista", r: "Lista" },
            ].map((o) => (
              <button
                key={o.v}
                type="button"
                role="tab"
                aria-selected={modo === o.v}
                className={`btn ${modo === o.v ? "btn-primario" : "btn-secundario"} px-3 py-1 text-[13px]`}
                onClick={() => setModo(o.v)}
              >
                {o.r}
              </button>
            ))}
          </div>
        }
      >
        {modo === "tempo" ? (
          <LinhaDoTempo agenda={agenda} aoAbrir={(r) => setAberta(r.id)} />
        ) : !agenda.reservas.length ? (
          <p className="px-1 py-8 text-center text-[15px] text-suave">
            Nenhuma reserva neste dia.
          </p>
        ) : (
          <div className="grid-rolante">
            <table className="tabela">
              <thead>
                <tr>
                  <th className="num w-[80px]">Hora</th>
                  {/* 🔑 A hora de saída sai da PERMANÊNCIA, e é o que diz quando a
                      mesa volta. Sem ela, a recepção não tem como responder "dá
                      para encaixar às 13h?" sem abrir outra tela. */}
                  <th className="num w-[80px]">Sai</th>
                  <th className="min-w-[200px]">Quem</th>
                  <th className="num w-[80px]">Pess.</th>
                  <th className="w-[110px]">Mesa</th>
                  <th className="w-[130px]">Situação</th>
                  {podeEditar && <th className="min-w-[180px]"></th>}
                </tr>
              </thead>
              <tbody>
                {agenda.reservas.map((r) => {
                  const solta = r.status === "CANCELADA" || r.status === "NAO_COMPARECEU";
                  return (
                    <tr key={r.id} className={solta ? "text-suave" : ""}>
                      <td className="num mono">{r.hora}</td>
                      <td className="num mono text-suave">{r.sai_por_volta ?? "—"}</td>
                      <td>
                        <span className="font-medium">{r.nome}</span>
                        {r.telefone && (
                          <span className="mono block text-[12px] text-suave">
                            {r.telefone}
                          </span>
                        )}
                        {(r.objetivo || r.observacao_cliente || r.observacao_interna) && (
                          <span className="block text-[12.5px] text-suave">
                            {[r.objetivo, r.observacao_cliente, r.observacao_interna]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        )}
                        {r.origem === "SITE" && (
                          <span className="mt-0.5 block">
                            <Etiqueta>pelo site</Etiqueta>
                          </span>
                        )}
                      </td>
                      <td className="num mono">{r.pessoas}</td>
                      <td className="mono">{r.mesas || "—"}</td>
                      <td>
                        <Etiqueta cor={COR[r.status]}>{ROTULO[r.status] ?? r.status}</Etiqueta>
                      </td>
                      {podeEditar && (
                        <td>
                          <span className="flex flex-wrap gap-3">
                            {/* 🔑 **Remarcar não é mudança de status**, por isso
                                fica fora do `ADIANTE`: a reserva continua a
                                mesma, só muda de lugar na agenda. ⚠️ Só para
                                quem ainda não sentou — quem já CHEGOU está na
                                mesa, e mudar o horário dele não descreve nada
                                que aconteça no salão. */}
                            {podeRemarcar(r.status) && (
                              <button
                                className="link-acao"
                                aria-busy={ocupado} disabled={ocupado}
                                onClick={() => setRemarcando(r)}
                              >
                                remarcar
                              </button>
                            )}
                            {(ADIANTE[r.status] ?? []).map((a) => (
                              <button
                                key={a.para}
                                className={`link-acao ${a.perigo ? "link-acao-erro" : ""}`}
                                aria-busy={ocupado} disabled={ocupado}
                                onClick={() => void mudar(r, a.para, a.rotulo)}
                              >
                                {a.rotulo}
                              </button>
                            ))}
                          </span>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>
    </div>
  );
}
