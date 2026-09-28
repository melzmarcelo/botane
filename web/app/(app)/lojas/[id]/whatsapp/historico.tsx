"use client";

import { useCallback, useEffect, useState } from "react";

import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { mensagensWhatsapp, type MensagemWhatsapp } from "@/lib/whatsapp";

/**
 * O histórico das mensagens: para quem, qual aviso, quando e o que aconteceu.
 *
 * 🔑 É a resposta para "ele disse que não recebeu": falhou (e por quê), entregue, lida,
 * respondida. ⚠️ `prefixoUrl`: a aba divide o endereço com o resto da tela da loja.
 */
const COR: Record<MensagemWhatsapp["status"], "erva" | "alerta" | "neutro"> = {
  FILA: "neutro", ENVIADA: "neutro", ENTREGUE: "erva", LIDA: "erva", RESPONDIDA: "erva",
  FALHOU: "alerta", SIMULADA: "neutro", CANCELADA: "neutro",
};
const ROTULO: Record<MensagemWhatsapp["status"], string> = {
  FILA: "na fila", ENVIADA: "enviada", ENTREGUE: "entregue", LIDA: "lida",
  RESPONDIDA: "respondida", FALHOU: "falhou", SIMULADA: "simulada", CANCELADA: "cancelada",
};
const quando = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";

export default function HistoricoDoWhatsapp({ idLoja, versao }: { idLoja: number; versao: number }) {
  const [lista, setLista] = useState<MensagemWhatsapp[] | null>(null);
  const [status, setStatus] = useState("");
  const [erro, setErro] = useState("");
  const pag = usePaginacao("whatsapp-historico", { filtros: [status], prefixoUrl: "wa" });

  const carregar = useCallback(async () => {
    if (!pag.pronto) return;
    try {
      const r = await mensagensWhatsapp(idLoja, pag.parametros, status);
      setLista(r.itens);
      pag.setTotal(r.total);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar o histórico");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.pronto, idLoja, status, pag.offset, pag.porPagina, versao]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  return (
    <Cartao
      titulo="Histórico de mensagens"
      acao={
        <select className="campo text-[13px]" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">todas</option>
          {Object.entries(ROTULO).map(([v, r]) => <option key={v} value={v}>{r}</option>)}
        </select>
      }
    >
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!lista ? (
        <Carregando />
      ) : !lista.length ? (
        <Vazio>Nenhuma mensagem ainda.</Vazio>
      ) : (
        <div className="grid-rolante">
          <table className="tabela">
            <thead>
              <tr>
                <th className="w-[110px]">Quando</th>
                <th>Para</th>
                <th>Aviso</th>
                <th className="w-[120px]">Situação</th>
              </tr>
            </thead>
            <tbody>
              {lista.map((m) => (
                <tr key={m.id}>
                  <td className="mono text-[12.5px]">
                    {quando(m.enviada_em ?? m.agendada_para)}
                    {m.status === "FILA" && <span className="block text-suave">agendada</span>}
                  </td>
                  <td>
                    {m.nome ?? "—"}
                    <span className="mono block text-[12px] text-suave">+{m.telefone}</span>
                  </td>
                  <td>
                    {m.aviso}
                    {m.texto && <span className="block max-w-[420px] text-[12px] text-suave">{m.texto}</span>}
                  </td>
                  <td>
                    <Etiqueta cor={COR[m.status]}>{ROTULO[m.status]}</Etiqueta>
                    {m.resposta && (
                      <span className="block text-[12px] text-suave">
                        {m.resposta === "CONFIRMAR" ? "✓ confirmou" : "cancelou"}
                      </span>
                    )}
                    {m.erro && <span className="block text-[12px] text-[var(--color-erro)]">{m.erro}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Paginacao p={pag} rotulo="mensagem(ns)" />
    </Cartao>
  );
}
