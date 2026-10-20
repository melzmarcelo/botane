"use client";

/**
 * Apagar a medição do Cardápio Vivo de um período (20/10/2026).
 *
 * 🔑 Pedido do dono: *"realizar a limpeza de dados de determinado período"* — os dias de teste
 * antes de abrir, ou um dia em que a medição saiu errada. Primeiro a conta do que existe no
 * período; só depois o apagar, com confirmação. ⚠️ Só a medição: anúncios, testes A/B, chamados
 * e pedidos ficam — os números deles voltam sem aqueles dias.
 */

import { useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Cartao, Confirmacao } from "@/components/ui";
import { CardapioVivoService, type MedicaoDoPeriodo } from "@/lib/cardapio-vivo";

export default function MedicaoDoPeriodo() {
  const aviso = useAviso();
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [pv, setPv] = useState<MedicaoDoPeriodo | null>(null);
  const [confirmando, setConfirmando] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  async function conferir() {
    try {
      setPv(await CardapioVivoService.medicao(de, ate));
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível conferir o período.");
    }
  }

  async function apagar() {
    setOcupado(true);
    try {
      const r = await CardapioVivoService.apagarMedicao(de, ate);
      aviso.sucesso(r.message);
      setConfirmando(false);
      setPv(await CardapioVivoService.medicao(de, ate));
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível apagar.");
    } finally {
      setOcupado(false);
    }
  }

  const data = (iso: string) => iso.split("-").reverse().join("/");
  return (
    <Cartao titulo="Apagar a medição de um período"
            descricao="Os dias de teste antes de abrir, ou um dia em que a medição saiu errada. Apaga o que o Cardápio Vivo mediu nesta loja — visitas, pratos vistos, anúncios e cartões vistos, e os resumos daqueles dias. Os anúncios, os testes A/B e os pedidos ficam.">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-[13px]"><span className="text-suave">De</span>
          <input type="date" id="medicao-de" className="campo mono" value={de}
                 onChange={(e) => { setDe(e.target.value); setPv(null); }} /></label>
        <label className="flex flex-col gap-1 text-[13px]"><span className="text-suave">Até</span>
          <input type="date" id="medicao-ate" className="campo mono" value={ate}
                 onChange={(e) => { setAte(e.target.value); setPv(null); }} /></label>
        <button type="button" id="medicao-conferir" className="btn btn-secundario" disabled={!de || !ate}
                onClick={() => void conferir()}>Ver o que existe</button>
      </div>
      {pv && (
        <div className="mt-4 text-[14px]" id="medicao-previa">
          {pv.vazio ? (
            <p className="text-suave">Nada medido de {data(pv.de)} a {data(pv.ate)}.</p>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <span>
                De {data(pv.de)} a {data(pv.ate)}: <b>{pv.eventos}</b> evento(s) de <b>{pv.sessoes}</b> visita(s)
                {pv.agregados_dia + pv.resumo_dia + pv.conteudo_dia > 0 && ", e os resumos daqueles dias"}.
              </span>
              <button type="button" id="medicao-apagar" className="btn btn-secundario text-erro"
                      onClick={() => setConfirmando(true)}>Apagar</button>
            </div>
          )}
        </div>
      )}
      {confirmando && pv && (
        <Confirmacao titulo={`Apagar a medição de ${data(pv.de)} a ${data(pv.ate)}?`} rotuloConfirmar="Apagar" perigo
                     ocupado={ocupado} aoConfirmar={() => void apagar()} aoCancelar={() => setConfirmando(false)}>
          <p>
            Saem {pv.eventos} evento(s) de {pv.sessoes} visita(s) e os resumos daqueles dias. Atenção × Vendas, os testes A/B e
            os relatórios dos anúncios passam a não contar esses dias. Isto não se desfaz.
          </p>
        </Confirmacao>
      )}
    </Cartao>
  );
}
