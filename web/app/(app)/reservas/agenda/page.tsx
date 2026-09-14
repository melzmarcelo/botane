"use client";

import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Cartao, Confirmacao, Etiqueta } from "@/components/ui";
import { api } from "@/lib/api";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { useSessao } from "@/lib/sessao";

/**
 * A agenda do dia — a tela que a recepção olha o tempo todo.
 *
 * 🔑 **Quem decide se cabe é o SERVIDOR**, sempre. A lista de horários vem de
 * `/reservas/disponibilidade`, que roda a mesma regra que a gravação vai rodar.
 * Uma segunda versão da regra aqui divergiria no primeiro degrau novo, e a tela
 * passaria a oferecer horários que a gravação recusa.
 *
 * 🔑 **O número de pessoas vem ANTES do horário, e a ordem é a regra.**
 * "Esgotado" depende do tamanho do grupo: no mesmo sábado às 12h pode não haver
 * mesa para 6 e haver para 2. Perguntar o horário primeiro obrigaria a tela a
 * mostrar uma lista que ela ainda não sabe calcular.
 *
 * ⚠️ **A reserva não se apaga: muda de status.** Cancelada é um fato, e sumir
 * com a linha levaria junto a resposta para "por que a mesa ficou vazia naquele
 * sábado".
 */

type Horario = { hora: string; livre: boolean; mesas_livres: number; sai_por_volta: string };
type Disponibilidade = {
  data: string;
  pessoas: number;
  abre?: string;
  fecha?: string;
  ultima_reserva?: string;
  teto_online?: number;
  maior_grupo?: number;
  horarios: Horario[];
  motivo: string | null;
};
type Reserva = {
  id: number;
  hora: string;
  sai_por_volta: string | null;
  pessoas: number;
  status: string;
  origem: string;
  nome: string;
  telefone: string | null;
  objetivo: string | null;
  observacao_cliente: string | null;
  observacao_interna: string | null;
  mesas: string;
};
type Agenda = {
  data: string;
  reservas: Reserva[];
  esperados: number;
  ativas: number;
  aberta: boolean;
  bloqueio: string | null;
  lugares: number;
};

/** O que cada status permite fazer em seguida — espelha `TRANSICOES` no servidor.
 *  ⚠️ Quem DECIDE é o servidor: isto só escolhe que botões mostrar. Oferecer um
 *  caminho que ele recusa seria pior que não oferecer nenhum. */
const ADIANTE: Record<string, { para: string; rotulo: string; perigo?: boolean }[]> = {
  PENDENTE: [
    { para: "CONFIRMADA", rotulo: "confirmar" },
    { para: "CANCELADA", rotulo: "cancelar", perigo: true },
  ],
  CONFIRMADA: [
    { para: "CHEGOU", rotulo: "chegou" },
    { para: "NAO_COMPARECEU", rotulo: "não veio", perigo: true },
    { para: "CANCELADA", rotulo: "cancelar", perigo: true },
  ],
  CHEGOU: [{ para: "ENCERRADA", rotulo: "encerrar" }],
  ENCERRADA: [],
  CANCELADA: [],
  NAO_COMPARECEU: [],
};

const ROTULO: Record<string, string> = {
  PENDENTE: "aguardando", CONFIRMADA: "confirmada", CHEGOU: "chegou",
  ENCERRADA: "encerrada", CANCELADA: "cancelada", NAO_COMPARECEU: "não veio",
};
const COR: Record<string, "neutro" | "erva" | "alerta"> = {
  PENDENTE: "alerta", CONFIRMADA: "erva", CHEGOU: "erva",
  ENCERRADA: "neutro", CANCELADA: "neutro", NAO_COMPARECEU: "alerta",
};

const hoje = () => new Date().toISOString().slice(0, 10);

export default function AgendaDoDia() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const [dia, setDia] = useEstadoNaUrl<string>("dia", hoje(), { atraso: 0 });
  const [agenda, setAgenda] = useState<Agenda | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [marcando, setMarcando] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setAgenda(await api.get<Agenda>(`/reservas/agenda?data=${dia}`));
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar a agenda");
    }
  }, [dia]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  /** O que ainda precisa de confirmação antes de acontecer.
   *
   * ⚠️ **Nunca `window.confirm`.** É a caixa do NAVEGADOR: fonte de sistema,
   * botão em inglês e nenhuma chance de explicar o que a ação faz. Numa tela que
   * existe para dar confiança sobre a agenda da casa, a confirmação é parte do
   * produto — e o componente `Confirmacao` está aqui justamente para isso. */
  const [confirmar, setConfirmar] = useState<
    { r: Reserva; para: string; rotulo: string } | null
  >(null);

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
      const resposta = await api.put<{ message: string }>(`/reservas/${r.id}/status`, {
        status: para,
      });
      aviso.sucesso(resposta.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível mudar o status");
      await carregar();
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!agenda) return <Carregando />;

  const podeEditar = pode("reservas.editar");

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="titulo">Agenda do dia</h1>
          <p className="text-[14px] text-suave">
            Quem vem, quando, e em que mesa. A casa decide a mesa — o cliente reserva lugar.
          </p>
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
          A casa não atende neste dia da semana. Isso se muda em Reservas → Configurações.
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

      <Cartao titulo={`Reservas de ${dia.split("-").reverse().join("/")}`}>
        {!agenda.reservas.length ? (
          <p className="px-1 py-8 text-center text-[15px] text-suave">
            Nenhuma reserva neste dia.
          </p>
        ) : (
          <div className="overflow-x-auto">
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
                            {(ADIANTE[r.status] ?? []).map((a) => (
                              <button
                                key={a.para}
                                className={`link-acao ${a.perigo ? "link-acao-erro" : ""}`}
                                disabled={ocupado}
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

/**
 * Marcar uma reserva: quantas pessoas → que horários aceitam → quem.
 *
 * 🔑 **A ordem é a regra.** "Esgotado" depende do tamanho do grupo, então o
 * número de pessoas vem primeiro; só depois dele o servidor sabe que horários
 * oferecer. Perguntar o horário antes obrigaria a tela a mostrar uma lista que
 * ela ainda não pode calcular.
 */
function NovaReserva({
  dia,
  aoFechar,
  aoMarcar,
}: {
  dia: string;
  aoFechar: () => void;
  aoMarcar: () => Promise<void>;
}) {
  const aviso = useAviso();
  const [pessoas, setPessoas] = useState(2);
  const [disp, setDisp] = useState<Disponibilidade | null>(null);
  const [hora, setHora] = useState("");
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [objetivo, setObjetivo] = useState("");
  const [observacao, setObservacao] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    let vivo = true;
    setDisp(null);
    setHora("");
    api
      .get<Disponibilidade>(`/reservas/disponibilidade?data=${dia}&pessoas=${pessoas}`)
      .then((d) => vivo && setDisp(d))
      .catch(() => vivo && setDisp(null));
    return () => {
      vivo = false;
    };
  }, [dia, pessoas]);

  async function marcar() {
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>("/reservas", {
        data: dia,
        hora,
        pessoas,
        nome: nome.trim(),
        telefone: telefone.trim() || null,
        objetivo: objetivo.trim() || null,
        observacao_cliente: observacao.trim() || null,
        origem: "BALCAO",
      });
      aviso.sucesso(r.message);
      await aoMarcar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível marcar");
    } finally {
      setOcupado(false);
    }
  }

  const grupos = Array.from({ length: 12 }, (_v, i) => i + 1);

  return (
    <Cartao
      titulo="Nova reserva"
      descricao="Quantas pessoas primeiro — é isso que decide quais horários existem."
    >
      <div className="flex flex-col gap-4">
        <div>
          <span className="rot text-[13px] font-medium">Pessoas</span>
          <div className="mt-1.5 flex flex-wrap gap-2">
            {grupos.map((n) => (
              <button
                key={n}
                type="button"
                aria-label={`${n} pessoas`}
                aria-pressed={pessoas === n}
                className={`mono rounded-full border px-3.5 py-1.5 text-[13.5px] ${
                  pessoas === n
                    ? "border-erva bg-erva-claro text-erva"
                    : "border-linha2 text-suave hover:border-erva"
                }`}
                onClick={() => setPessoas(n)}
              >
                {n}
              </button>
            ))}
          </div>
          {/* 🔑 O teto do site tem de caber no salão — se o maior grupo que a
              casa acomoda for menor que o pedido, a resposta vazia abaixo se
              explica sozinha em vez de parecer defeito. */}
          {disp?.maior_grupo !== undefined && pessoas > disp.maior_grupo && (
            <p className="mt-2 text-[13px] text-alerta">
              A maior mesa (ou junta) da casa acomoda {disp.maior_grupo}. Para um grupo
              maior, junte mesas na mão e marque duas reservas — ou acrescente a junta no
              cadastro do Salão.
            </p>
          )}
        </div>

        <div>
          <span className="rot text-[13px] font-medium">Horário</span>
          {!disp ? (
            <Carregando>Vendo o que cabe…</Carregando>
          ) : !disp.horarios.length ? (
            <Aviso tipo="info">{disp.motivo ?? "Sem horários neste dia."}</Aviso>
          ) : (
            <>
              <div className="mt-1.5 grid grid-cols-3 gap-2 sm:grid-cols-6">
                {disp.horarios.map((h) => (
                  <button
                    key={h.hora}
                    type="button"
                    disabled={!h.livre}
                    aria-label={`horário ${h.hora}`}
                    aria-pressed={hora === h.hora}
                    title={h.livre ? `Sai por volta das ${h.sai_por_volta}` : "Sem mesa"}
                    className={`mono rounded-lg border px-2 py-2 text-[14px] ${
                      hora === h.hora
                        ? "border-erva bg-erva-claro text-erva"
                        : h.livre
                          ? "border-linha2 hover:border-erva"
                          : "border-linha2 text-suave line-through opacity-60"
                    }`}
                    onClick={() => setHora(h.hora)}
                  >
                    {h.hora}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-[12.5px] text-suave">
                Atende das {disp.abre} às {disp.fecha}; a última reserva é{" "}
                {disp.ultima_reserva} — a diferença é o tempo de quem senta por último.
                {hora &&
                  ` Escolhido ${hora}: a mesa vaga por volta das ${
                    disp.horarios.find((h) => h.hora === hora)?.sai_por_volta ?? "—"
                  }.`}
              </p>
            </>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Campo rotulo="Nome de quem reserva">
            <input
              className="campo"
              aria-label="nome de quem reserva"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
            />
          </Campo>
          <Campo rotulo="Telefone" dica="é por ele que a casa avisa">
            <input
              className="campo mono"
              aria-label="telefone de quem reserva"
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
            />
          </Campo>
          <Campo rotulo="Objetivo" dica="almoço, comemoração…">
            <input
              className="campo"
              aria-label="objetivo da reserva"
              value={objetivo}
              onChange={(e) => setObjetivo(e.target.value)}
            />
          </Campo>
          <Campo rotulo="Precisa de algo especial?" dica="aniversário, cadeirinha…">
            <input
              className="campo"
              aria-label="observação da reserva"
              value={observacao}
              onChange={(e) => setObservacao(e.target.value)}
            />
          </Campo>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            className="btn btn-primario"
            disabled={ocupado || !hora || nome.trim().length < 2}
            onClick={() => void marcar()}
          >
            {hora ? `Marcar às ${hora}` : "Escolha um horário"}
          </button>
          <button className="link-acao" onClick={aoFechar}>
            cancelar
          </button>
          {/* ⚠️ A tela NÃO escolhe a mesa: quem aloca é o servidor, e dizer isso
              evita a pergunta "por que não posso escolher?" na primeira semana. */}
          <span className="text-[12.5px] text-suave">
            A mesa é escolhida pelo sistema — a menor que serve, e só junta mesas quando
            não houver uma inteira.
          </span>
        </div>
      </div>
    </Cartao>
  );
}
