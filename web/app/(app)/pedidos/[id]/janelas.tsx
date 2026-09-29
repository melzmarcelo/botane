"use client";

import { useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Modal } from "@/components/ui";
import { cancelar, lancadoNoPdv, pago, recusar, type PedidoCompleto } from "@/lib/pedidos";

/**
 * As janelas pequenas do pedido: motivo (recusar/cancelar), cupom do PDV e pagamento.
 * O painel usa as mesmas — duas versões da mesma pergunta divergiriam na primeira correção.
 */
type Props = { pedido: { id: number; numero: number; cupom_pdv?: string | null }; aoFechar: () => void; aoFeito: (p: PedidoCompleto) => void };

function useAcao(aoFeito: (p: PedidoCompleto) => void) {
  const aviso = useAviso();
  const [ocupado, setOcupado] = useState(false);
  async function rodar(fazer: () => Promise<PedidoCompleto & { message: string }>) {
    setOcupado(true);
    try {
      const r = await fazer();
      aviso.sucesso(r.message);
      aoFeito(r);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível");
    } finally {
      setOcupado(false);
    }
  }
  return { ocupado, rodar };
}

function Rodape({ aoFechar, ocupado, rotulo, desabilitado, aoConfirmar, perigo }: {
  aoFechar: () => void; ocupado: boolean; rotulo: string; desabilitado?: boolean;
  aoConfirmar: () => void; perigo?: boolean;
}) {
  return (
    <div className="flex justify-end gap-2">
      <button className="btn btn-secundario" onClick={aoFechar}>Voltar</button>
      <button className={`btn ${perigo ? "btn-perigo" : "btn-primario"}`} disabled={ocupado || desabilitado}
              aria-busy={ocupado} onClick={aoConfirmar}>{ocupado ? "…" : rotulo}</button>
    </div>
  );
}

export function JanelaDeMotivo({ pedido, tipo, aoFechar, aoFeito }: Props & { tipo: "recusar" | "cancelar" }) {
  const [motivo, setMotivo] = useState("");
  const { ocupado, rodar } = useAcao(aoFeito);
  const fazer = tipo === "recusar" ? recusar : cancelar;
  return (
    <Modal titulo={`${tipo === "recusar" ? "Recusar" : "Cancelar"} o pedido ${pedido.numero}`}
           descricao="O cliente vê o motivo em “Meus pedidos”." aoFechar={aoFechar} largura="480px"
           rodape={<Rodape aoFechar={aoFechar} ocupado={ocupado} perigo rotulo={tipo === "recusar" ? "Recusar" : "Cancelar pedido"}
                           desabilitado={motivo.trim().length < 3}
                           aoConfirmar={() => void rodar(() => fazer(pedido.id, motivo.trim()))} />}>
      <Campo rotulo="Motivo">
        <input className="campo" autoFocus maxLength={300} value={motivo} onChange={(e) => setMotivo(e.target.value)}
               placeholder="ex.: acabou a torta de hoje" />
      </Campo>
    </Modal>
  );
}

export function JanelaDeCupom({ pedido, aoFechar, aoFeito }: Props) {
  const [cupom, setCupom] = useState(pedido.cupom_pdv ?? "");
  const { ocupado, rodar } = useAcao(aoFeito);
  return (
    <Modal titulo={`Pedido ${pedido.numero} lançado no PDV`}
           descricao="O pedido não vira venda aqui: a venda é a do PDV, que chega pela busca de sempre. Com o número do cupom, o pedido a acha quando ela chegar."
           aoFechar={aoFechar} largura="480px"
           rodape={<Rodape aoFechar={aoFechar} ocupado={ocupado} rotulo="Marcar como lançado"
                           aoConfirmar={() => void rodar(() => lancadoNoPdv(pedido.id, cupom.trim()))} />}>
      <Campo rotulo="Número do cupom no PDV" opcional>
        <input className="campo mono" autoFocus maxLength={40} value={cupom} onChange={(e) => setCupom(e.target.value)} />
      </Campo>
    </Modal>
  );
}

export function JanelaDePagamento({ pedido, aoFechar, aoFeito }: Props) {
  const [como, setComo] = useState("PIX");
  const { ocupado, rodar } = useAcao(aoFeito);
  return (
    <Modal titulo={`Pagamento do pedido ${pedido.numero}`} descricao="O sistema não cobra — só registra que a casa recebeu."
           aoFechar={aoFechar} largura="420px"
           rodape={<Rodape aoFechar={aoFechar} ocupado={ocupado} rotulo="Registrar"
                           aoConfirmar={() => void rodar(() => pago(pedido.id, como))} />}>
      <Campo rotulo="Como pagou">
        <select className="campo" value={como} onChange={(e) => setComo(e.target.value)}>
          <option value="PIX">Pix</option>
          <option value="CARTAO">Cartão</option>
          <option value="DINHEIRO">Dinheiro</option>
          <option value="OUTRO">Outro</option>
        </select>
      </Campo>
    </Modal>
  );
}
