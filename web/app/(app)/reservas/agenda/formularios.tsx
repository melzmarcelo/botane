"use client";

import { useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Cartao } from "@/components/ui";
import { api } from "@/lib/api";
import type { Reserva } from "@/lib/reservas";
import EscolherHorario from "../escolher-horario";

/**
 * Os dois formulários da agenda — marcar e remarcar —, fora da página para ela
 * caber na regra dos ~300 linhas. Nada mudou neles na mudança para o calendário.
 */

/**
 * Marcar uma reserva: quantas pessoas → que horários aceitam → quem.
 *
 * 🔑 **A ordem é a regra.** "Esgotado" depende do tamanho do grupo, então o
 * número de pessoas vem primeiro; só depois dele o servidor sabe que horários
 * oferecer. Perguntar o horário antes obrigaria a tela a mostrar uma lista que
 * ela ainda não pode calcular.
 */
export function NovaReserva({
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
  const [hora, setHora] = useState("");
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [objetivo, setObjetivo] = useState("");
  const [observacao, setObservacao] = useState("");
  const [ocupado, setOcupado] = useState(false);

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

  return (
    <Cartao
      titulo="Nova reserva"
      descricao="Quantas pessoas primeiro — é isso que decide quais horários existem."
    >
      <div className="flex flex-col gap-4">
        <EscolherHorario
          dia={dia}
          pessoas={pessoas}
          aoMudarPessoas={(n) => {
            setPessoas(n);
            // ⚠️ Trocar o grupo INVALIDA o horario escolhido: a mesa que
            // servia para dois pode nao servir para seis, e manter o
            // horario aceso deixaria a tela prometendo o que ja nao vale.
            setHora("");
          }}
          hora={hora}
          aoMudarHora={setHora}
        />

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
            aria-busy={ocupado} disabled={ocupado || !hora || nome.trim().length < 2}
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

/**
 * Passar a reserva para outro dia, outra hora ou outro tamanho de grupo.
 *
 * 🔑 **É a ligação mais comum depois de marcar** (*"dá para passar para as
 * 13h?"*). Sem isto, a recepção teria de cancelar e recriar — perdendo o
 * histórico da reserva e o lugar de quem marcou primeiro.
 *
 * ⚠️ **A reserva não disputa mesa consigo mesma**: o `ignorar` tira ela da conta
 * de quem ocupa. Sem ele, passar das 12h para as 12h30 esbarraria na própria
 * permanência e a tela diria "sem mesa" apontando para a mesa que ela ocupa.
 *
 * ⚠️ **Só o que MUDA é enviado.** Quem adia meia hora não repete data nem número
 * de pessoas, e mandar tudo faria a auditoria registrar como alteração o que
 * ficou igual.
 */
export function Remarcar({
  reserva,
  diaAtual,
  aoFechar,
  aoRemarcar,
}: {
  reserva: Reserva;
  diaAtual: string;
  aoFechar: () => void;
  aoRemarcar: () => Promise<void>;
}) {
  const aviso = useAviso();
  const [dia, setDia] = useState(diaAtual);
  const [pessoas, setPessoas] = useState(reserva.pessoas);
  const [hora, setHora] = useState(reserva.hora);
  const [ocupado, setOcupado] = useState(false);

  const mudou = dia !== diaAtual || pessoas !== reserva.pessoas || hora !== reserva.hora;

  async function remarcar() {
    setOcupado(true);
    try {
      const corpo: Record<string, unknown> = {};
      if (dia !== diaAtual) corpo.data = dia;
      if (hora !== reserva.hora) corpo.hora = hora;
      if (pessoas !== reserva.pessoas) corpo.pessoas = pessoas;
      const r = await api.put<{ message: string }>(`/reservas/${reserva.id}`, corpo);
      aviso.sucesso(r.message);
      await aoRemarcar();
    } catch (e) {
      // ⚠️ Recusado, a reserva fica como estava — e o servidor diz isso na
      // mensagem. A tela não fecha: quem tentou ainda quer escolher outra hora.
      aviso.erro(e instanceof Error ? e.message : "Não foi possível remarcar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Cartao
      titulo={`Remarcar a reserva de ${reserva.nome}`}
      descricao={`Hoje: ${reserva.hora}, ${reserva.pessoas} pessoa${
        reserva.pessoas === 1 ? "" : "s"
      }${reserva.mesas ? `, mesa ${reserva.mesas}` : ""}.`}
    >
      <div className="flex flex-col gap-4">
        <Campo
          rotulo="Dia"
          dica="mudando o dia, ela sai desta agenda e aparece na do dia novo"
          className="max-w-[220px]"
        >
          <input
            className="campo mono"
            type="date"
            aria-label="novo dia da reserva"
            value={dia}
            onChange={(e) => {
              setDia(e.target.value || diaAtual);
              // ⚠️ Dia novo, horários novos: manter o horário aceso prometeria
              // uma vaga que ninguém consultou.
              setHora("");
            }}
          />
        </Campo>

        <EscolherHorario
          dia={dia}
          pessoas={pessoas}
          aoMudarPessoas={(n) => {
            setPessoas(n);
            setHora("");
          }}
          hora={hora}
          aoMudarHora={setHora}
          ignorar={reserva.id}
        />

        <div className="flex flex-wrap items-center gap-3">
          <button
            className="btn btn-primario"
            aria-busy={ocupado} disabled={ocupado || !hora || !mudou}
            onClick={() => void remarcar()}
          >
            {!hora
              ? "Escolha um horário"
              : mudou
                ? "Remarcar"
                : "Nada mudou ainda"}
          </button>
          <button className="link-acao" onClick={aoFechar}>
            cancelar
          </button>
          <span className="text-[12.5px] text-suave">
            A mesa é escolhida de novo pelo sistema — o horário novo pode não caber na mesa
            de agora.
          </span>
        </div>
      </div>
    </Cartao>
  );
}
