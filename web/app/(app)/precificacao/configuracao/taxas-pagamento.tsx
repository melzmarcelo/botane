"use client";

import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Cartao } from "@/components/ui";
import { gravarTaxas, taxasPagamento, type TaxasPagamento } from "@/lib/caixa";
import { pct, textoParaNumero } from "@/lib/numeros";

/**
 * A taxa de cada forma de pagamento (migração 161, etapa 4 das finalizadoras, 24/11/2026).
 *
 * 🔑 Não substitui a linha de cartão acima (que incide no preço): mostra a **taxa média REAL**,
 * pelo peso de cada forma nas vendas dos últimos 90 dias — o número que aquela linha deveria
 * usar — e alimenta o custo estimado do cartão no painel de vendas.
 * ⚠️ Campo vazio é "não sei a taxa", diferente de zero.
 */
export default function TaxasPagamentoCartao({ podeEditar }: { podeEditar: boolean }) {
  const aviso = useAviso();
  const [dados, setDados] = useState<TaxasPagamento | null>(null);
  const [valores, setValores] = useState<Record<string, string>>({});
  const [ocupado, setOcupado] = useState(false);

  const preencher = (d: TaxasPagamento) => {
    setDados(d);
    setValores(Object.fromEntries(d.linhas.map((l) => [l.grupo,
      l.taxa_pct === null ? "" : String(l.taxa_pct).replace(".", ",")])));
  };

  useEffect(() => {
    taxasPagamento().then(preencher).catch(() => setDados(null));
  }, []);

  async function salvar() {
    setOcupado(true);
    try {
      const r = await gravarTaxas(Object.entries(valores).map(([grupo, v]) => ({
        grupo, taxa_pct: v.trim() ? textoParaNumero(v) : null })));
      preencher(r);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar as taxas");
    } finally {
      setOcupado(false);
    }
  }

  if (!dados) return null;
  return (
    <Cartao titulo="Taxa de cada forma de pagamento"
            descricao="Quanto a maquininha (ou o banco) cobra em cada forma. Com o peso de cada uma nas vendas do PDV, dá a taxa média que a casa paga de verdade.">
      <div id="taxas-pagamento" className="grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
        {dados.linhas.map((l) => (
          <label key={l.grupo} className="flex items-center gap-2 text-[14px]">
            <span className="min-w-[7.5rem]">
              {l.rotulo}
              {l.peso_pct !== null && <span className="block text-[12px] text-suave">{pct(l.peso_pct)} das vendas</span>}
            </span>
            <input className="campo w-24 text-right" inputMode="decimal" data-taxa={l.grupo}
                   disabled={!podeEditar} placeholder="—" value={valores[l.grupo] ?? ""}
                   onChange={(e) => setValores((v) => ({ ...v, [l.grupo]: e.target.value }))} />
            <span className="text-suave">%</span>
          </label>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <p className="text-[13.5px]" id="taxa-media-real">
          {dados.taxa_media_real === null
            ? <span className="text-suave">Sem vendas com forma de pagamento nos últimos {dados.dias_do_mix} dias.</span>
            : !dados.configuradas
              ? <span className="text-suave">Preencha as taxas para ver a média real.</span>
              : <>Taxa média real dos últimos {dados.dias_do_mix} dias: <b>{pct(dados.taxa_media_real, 2)}</b> da
                  venda. É o percentual que a linha de cartão acima deveria ter.</>}
        </p>
        {podeEditar && (
          <button type="button" className="btn btn-primario ml-auto" id="taxas-salvar"
                  disabled={ocupado} onClick={() => void salvar()}>
            Salvar taxas
          </button>
        )}
      </div>
    </Cartao>
  );
}
