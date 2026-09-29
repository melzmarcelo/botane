"use client";

import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Cartao, CampoMoeda, Etiqueta } from "@/components/ui";
import { moedaParaNumero, numeroParaMoeda } from "@/lib/numeros";
import { obterConfig, salvarConfig, type ConfigPedidos, type FormaPagamento } from "@/lib/pedidos";

/**
 * "Pedidos pelo site" — o cartão que liga o carrinho neste catálogo.
 *
 * 🔑 **Pedido do dono (28/09/2026):** *"criar esta opção ao criar um catálogo do tipo
 * Produtos"* — e a configuração é do CATÁLOGO, não da loja. Retirada/entrega, taxa, pedido
 * mínimo, encomenda com antecedência e o texto sobre o pagamento, que não passa pelo sistema.
 */
const PAGAMENTOS: { v: FormaPagamento; r: string }[] = [
  { v: "RETIRADA", r: "Na retirada" },
  { v: "ENTREGA", r: "Na entrega" },
  { v: "WHATSAPP", r: "Combinar pelo WhatsApp" },
];

export default function PedidosDoCatalogo({ idCatalogo, podeEditar }: { idCatalogo: number; podeEditar: boolean }) {
  const aviso = useAviso();
  const [cfg, setCfg] = useState<ConfigPedidos | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    obterConfig(idCatalogo).then(setCfg).catch(() => setCfg(null));
  }, [idCatalogo]);

  if (!cfg) return null;
  const mudar = <K extends keyof ConfigPedidos>(k: K, v: ConfigPedidos[K]) => setCfg({ ...cfg, [k]: v });

  async function salvar() {
    if (!cfg) return;
    setOcupado(true);
    try {
      const r = await salvarConfig(idCatalogo, cfg);
      setCfg(r);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Cartao
      titulo="Pedidos pelo site"
      descricao="O cliente monta o carrinho neste cardápio e envia o pedido; a casa confirma e lança no PDV."
      acao={<Etiqueta cor={cfg.aceita ? "erva" : "neutro"}>{cfg.aceita ? "aceitando pedidos" : "desligado"}</Etiqueta>}
    >
      <fieldset disabled={!podeEditar} className="flex flex-col gap-5">
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1" checked={cfg.aceita} onChange={(e) => mudar("aceita", e.target.checked)} />
          <span className="text-[14px]">
            Aceitar pedidos por este catálogo
            <span className="block text-[13px] text-suave">
              O pagamento não passa pelo sistema: o cliente escolhe como vai pagar e lê o texto abaixo.
            </span>
          </span>
        </label>

        {cfg.aceita && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <span className="rotulo-campo">Como o cliente recebe</span>
                <label className="flex items-center gap-2 text-[14px]">
                  <input type="checkbox" checked={cfg.retirada} onChange={(e) => mudar("retirada", e.target.checked)} />
                  Retirada na loja
                </label>
                <label className="flex items-center gap-2 text-[14px]">
                  <input type="checkbox" checked={cfg.entrega} onChange={(e) => mudar("entrega", e.target.checked)} />
                  Entrega
                </label>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Campo rotulo="Taxa de entrega" dica={cfg.entrega ? undefined : "só com entrega"}>
                  <CampoMoeda valor={numeroParaMoeda(cfg.taxa_entrega)}
                              aoMudar={(v) => mudar("taxa_entrega", moedaParaNumero(v) ?? 0)} />
                </Campo>
                <Campo rotulo="Pedido mínimo" dica="0 = sem mínimo">
                  <CampoMoeda valor={numeroParaMoeda(cfg.pedido_minimo)}
                              aoMudar={(v) => mudar("pedido_minimo", moedaParaNumero(v) ?? 0)} />
                </Campo>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Campo rotulo="Antecedência mínima (minutos)" dica="o tempo para o pedido ficar pronto">
                <input className="campo mono" type="number" min={0} value={cfg.antecedencia_min}
                       onChange={(e) => mudar("antecedencia_min", Math.max(0, Number(e.target.value) || 0))} />
              </Campo>
              <Campo rotulo="Encomenda até (dias à frente)" dica="0 = só para hoje">
                <input className="campo mono" type="number" min={0} max={60} value={cfg.antecedencia_max_dias}
                       onChange={(e) => mudar("antecedencia_max_dias", Math.max(0, Math.min(60, Number(e.target.value) || 0)))} />
              </Campo>
            </div>

            <div className="flex flex-col gap-2">
              <span className="rotulo-campo">Formas de pagamento que o cliente pode escolher</span>
              <div className="flex flex-wrap gap-4">
                {PAGAMENTOS.map((p) => (
                  <label key={p.v} className="flex items-center gap-2 text-[14px]">
                    <input type="checkbox" checked={cfg.pagamentos.includes(p.v)}
                           onChange={(e) => mudar("pagamentos", e.target.checked
                             ? [...cfg.pagamentos, p.v] : cfg.pagamentos.filter((x) => x !== p.v))} />
                    {p.r}
                  </label>
                ))}
              </div>
            </div>
            <Campo rotulo="Mensagem sobre o pagamento" opcional dica="o cliente lê antes de enviar o pedido">
              <textarea className="campo" rows={2} maxLength={500} value={cfg.texto_pagamento ?? ""}
                        placeholder="Ex.: O pagamento é feito na retirada ou na entrega, em dinheiro, cartão ou Pix."
                        onChange={(e) => mudar("texto_pagamento", e.target.value)} />
            </Campo>
          </>
        )}

        {podeEditar && (
          <div className="flex justify-end">
            <button className="btn btn-primario" aria-busy={ocupado} disabled={ocupado} onClick={() => void salvar()}>
              {ocupado ? "…" : "Salvar pedidos"}
            </button>
          </div>
        )}
      </fieldset>
    </Cartao>
  );
}
