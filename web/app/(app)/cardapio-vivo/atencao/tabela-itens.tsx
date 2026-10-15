"use client";

/**
 * Os pratos do Cardápio Vivo, um por linha: atenção, conversão, venda, margem e o que
 * fazer — na ORDEM da prioridade (o objetivo de negócio pesa, ver `cardapio_atencao.py`).
 * ⚠️ O nome do prato leva ao cadastro; destaque e ordem se mudam no catálogo.
 */

import Link from "next/link";
import { Cartao, Etiqueta, Vazio } from "@/components/ui";
import type { ItemAtencao } from "@/lib/cardapio-vivo";
import { pct, segundos } from "./indicadores";

const QUADRANTE: Record<string, string> = {
  ALTA_ATENCAO_ALTA_VENDA: "muita atenção · muita venda",
  ALTA_ATENCAO_BAIXA_VENDA: "muita atenção · pouca venda",
  BAIXA_ATENCAO_ALTA_VENDA: "pouca atenção · muita venda",
  BAIXA_ATENCAO_BAIXA_VENDA: "pouca atenção · pouca venda",
};
const NIVEL: Record<string, string> = { ALTA: "alta", MEDIA: "média", BAIXA: "baixa" };

export default function TabelaItens({ itens, idCatalogo }: { itens: ItemAtencao[]; idCatalogo: number | null }) {
  return (
    <Cartao titulo="Pratos" descricao="Ordenados pela prioridade da sugestão. Só as sessões engajadas contam.">
      {itens.length === 0 ? <Vazio>Nenhum prato no cardápio apontado.</Vazio> : (
        <div className="overflow-x-auto">
          <table className="tabela text-[13.5px]">
            <thead>
              <tr>
                <th>Prato</th><th>Sugestão</th>
                <th className="text-right" title="Visualizações">Vistas</th>
                <th className="text-right">Atenção estimada média</th>
                <th className="text-right">Adição</th><th className="text-right">Desistência</th>
                <th className="text-right">Quase pediu</th><th className="text-right">♥</th>
                <th className="text-right" title="Deslizes para trás">↩</th>
                <th className="text-right">Vendas (PDV)</th><th className="text-right">Margem</th>
              </tr>
            </thead>
            <tbody>
              {itens.map((i) => (
                <tr key={i.id_produto}>
                  <td>
                    <Link href={`/produtos/${i.id_produto}`} className="link-registro">{i.nome}</Link>
                    <span className="block text-[12px] text-suave">
                      {i.secao}{i.objetivo_rotulo ? ` · ${i.objetivo_rotulo}` : ""}{i.destaque ? " · em destaque" : ""}
                      {i.tem_video ? " · vídeo" : ""}
                    </span>
                  </td>
                  <td className="min-w-[13rem]">
                    {i.sugestao_rotulo ? <Etiqueta cor={i.sugestao === "SAIR" ? "alerta" : "erva"}>{i.sugestao_rotulo}</Etiqueta>
                      : <span className="text-suave">—</span>}
                    <span className="block text-[12px] text-suave">{QUADRANTE[i.quadrante] ?? ""}</span>
                  </td>
                  <td className="mono text-right">{i.visualizacoes}</td>
                  <td className="mono text-right">{segundos(i.atencao_media_ms)}</td>
                  <td className="mono text-right">{pct(i.taxa_adicao)}</td>
                  <td className="mono text-right">{pct(i.desistencia)}</td>
                  <td className="mono text-right">{i.quase_pediu}</td>
                  <td className="mono text-right">{i.favoritos}</td>
                  <td className="mono text-right">{i.deslizes_tras}</td>
                  <td className="mono text-right">{i.vendas_qtd.toLocaleString("pt-BR")}</td>
                  <td className="text-right">
                    <span className="mono">{i.margem_pct === null ? "—" : `${i.margem_pct.toFixed(1).replace(".", ",")}%`}</span>
                    <span className="block text-[12px] text-suave" title={i.margem_manual ? "Ajustado à mão no catálogo" : "Calculado pela margem-alvo da Precificação"}>
                      {i.margem_nivel ? `${NIVEL[i.margem_nivel]}${i.margem_manual ? " (à mão)" : ""}` : "sem meta"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {idCatalogo && (
        <p className="mt-3 text-[13px] text-suave">
          Para destacar, mudar a ordem ou o objetivo de um prato: <Link href={`/catalogos/${idCatalogo}`} className="link-acao">abrir o catálogo</Link>.
        </p>
      )}
    </Cartao>
  );
}
