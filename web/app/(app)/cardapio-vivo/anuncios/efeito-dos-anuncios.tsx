"use client";

/**
 * O efeito dos anúncios (125, fase 2): o grupo de controle × as visitas expostas.
 *
 * 🔑 Pedido do dono (16/10/2026): "grupo de controle de 10% pode". É o que responde se os anúncios
 * atrapalham quem está escolhendo o prato: em cada grupo, quantas visitas se envolveram com o
 * cardápio e quantas adicionaram um prato. ⚠️ Exposta = PODIA ver anúncio — quem saiu antes do 5º
 * prato está no grupo sem ter visto.
 */

import { useCallback, useEffect, useState } from "react";
import { Cartao } from "@/components/ui";
import { AnunciosService, porcento, type Efeito } from "@/lib/anuncios";

const FRASE: Record<string, string> = {
  AMOSTRA_PEQUENA: "ainda pouca gente para concluir",
  SEM_DIFERENCA: "sem diferença que se possa afirmar",
  A_VENCE: "as visitas SEM anúncio fazem mais",
  B_VENCE: "as visitas COM anúncio fazem mais",
};

export default function EfeitoDosAnuncios() {
  const [e, setE] = useState<Efeito | null>(null);
  const [falhou, setFalhou] = useState(false);
  const carregar = useCallback(async () => {
    try {
      setE(await AnunciosService.efeito());
    } catch {
      setFalhou(true);
    }
  }, []);
  useEffect(() => { void carregar(); }, [carregar]);
  if (falhou) return null;
  if (!e) return null;
  const taxa = (n: number, d: number) => porcento(d ? n / d : null);
  const linha = (rotulo: string, g: Efeito["controle"]) => (
    <tr>
      <td>{rotulo}</td>
      <td className="mono text-right">{g.sessoes}</td>
      <td className="mono text-right">{taxa(g.engajadas, g.sessoes)}</td>
      <td className="mono text-right">{taxa(g.adicionaram, g.sessoes)}</td>
      <td className="mono text-right">{g.pratos_por_sessao !== null ? String(g.pratos_por_sessao).replace(".", ",") : "—"}</td>
    </tr>
  );
  return (
    <Cartao titulo="O efeito dos anúncios"
            descricao={`Últimos 30 dias. ${e.percentual ? `${e.percentual}% das visitas não veem anúncio nenhum (o grupo de controle)` : "O grupo de controle está desligado"}; comparar os dois grupos diz se os anúncios mudam o que as pessoas fazem no cardápio.`}>
      {e.controle.sessoes + e.expostas.sessoes === 0 ? (
        <p className="text-[13.5px] text-suave" id="efeito-vazio">Ainda nenhuma visita com anúncio para comparar.</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="tabela w-full" id="efeito-anuncios">
              <thead><tr><th>Visitas</th><th className="text-right">Quantas</th><th className="text-right">Se envolveram</th>
                <th className="text-right">Adicionaram prato</th><th className="text-right">Pratos vistos</th></tr></thead>
              <tbody>
                {linha("Sem anúncio (controle)", e.controle)}
                {linha("Com anúncio", e.expostas)}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[13px]">
            Adicionar prato: <b>{FRASE[e.adicao.conclusao]}</b>. Envolvimento: <b>{FRASE[e.engajamento.conclusao]}</b>.
            <span className="block text-[12.5px] text-suave">
              “Se envolveram” = viram 3 pratos ou mais, ou favoritaram, personalizaram ou adicionaram. Conclusão só com
              {` ${e.minimo_por_braco}`} visitas em cada grupo e 95% de confiança.
            </span>
          </p>
        </>
      )}
    </Cartao>
  );
}
