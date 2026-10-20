"use client";

/**
 * Os textos de um anúncio no relatório (125, fase 3): a original e cada variação, e a vencedora.
 *
 * 🔑 A vencedora sai da TAXA DE TOQUE (visitas que tocaram ÷ que viram), comparada com a original
 * pelo mesmo teste dos A/B do cardápio (116). Nada muda sem "Aplicar": o texto escolhido passa a
 * ser o do anúncio e as variações saem — os números ficam no relatório.
 */

import { useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Cartao, Confirmacao } from "@/components/ui";
import { AnunciosService, porcento, type LinhaDaVariante, type VariantesDoRelatorio } from "@/lib/anuncios";
import { useSessao } from "@/lib/sessao";

const CONCLUSAO: Record<VariantesDoRelatorio["conclusao"], string> = {
  VARIACAO_VENCE: "Há uma vencedora: ela faz mais gente tocar do que a original.",
  ORIGINAL_VENCE: "A original faz mais gente tocar do que as variações.",
  AMOSTRA_PEQUENA: "Ainda pouca gente em algum dos textos para apontar vencedora.",
  SEM_DIFERENCA: "Sem diferença que se possa afirmar entre os textos.",
};

export default function TextosEmTeste({ idAnuncio, dados, aoAplicar }: {
  idAnuncio: number; dados: VariantesDoRelatorio; aoAplicar: () => void;
}) {
  const aviso = useAviso();
  const { pode } = useSessao();
  const [aplicando, setAplicando] = useState<LinhaDaVariante | null>(null);

  async function aplicar() {
    if (!aplicando) return;
    try {
      const r = await AnunciosService.aplicarVariante(idAnuncio, aplicando.id_variante);
      setAplicando(null);
      aviso.sucesso(r.message);
      aoAplicar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível aplicar.");
    }
  }

  return (
    <Cartao titulo="Os textos em teste" descricao={CONCLUSAO[dados.conclusao]}>
      <div className="overflow-x-auto">
        <table className="tabela w-full" id="relatorio-variantes">
          <thead><tr><th>Texto</th><th className="text-right">Pessoas que viram</th><th className="text-right">Tocaram</th>
            <th className="text-right">Taxa de toque</th><th className="nao-imprimir" /></tr></thead>
          <tbody>
            {dados.linhas.map((l) => (
              <tr key={l.id_variante ?? 0} data-variante-linha={l.id_variante ?? 0}>
                <td>
                  <span className="font-semibold">{l.rotulo}</span>
                  {dados.vencedora !== null && dados.vencedora === l.id_variante && <span className="ml-2 text-[12px] text-erva">vencedora</span>}
                  <span className="block text-[12.5px] text-suave">{l.existe ? (l.titulo || l.texto || "—") : "(já saiu do anúncio)"}</span>
                </td>
                <td className="mono text-right">{l.sessoes}</td>
                <td className="mono text-right">{l.tocaram}</td>
                <td className="mono text-right">{porcento(l.taxa)}</td>
                <td className="nao-imprimir text-right">
                  {dados.em_teste && l.existe && pode("catalogos.editar") && (
                    <button type="button" className="link-acao" onClick={() => setAplicando(l)}>
                      {l.id_variante === null ? "ficar com a original" : "aplicar"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[12.5px] text-suave">
        Cada visita vê sempre o mesmo texto. Vencedora só com {dados.minimo_por_braco} pessoas em cada texto e 95% de
        confiança. Os dias que vêm do resumo diário não separam por texto.
      </p>
      {aplicando && (
        <Confirmacao titulo={aplicando.id_variante === null ? "Ficar com a original?" : `Aplicar a ${aplicando.rotulo}?`}
                     rotuloConfirmar="Aplicar" aoConfirmar={() => void aplicar()} aoCancelar={() => setAplicando(null)}>
          <p>
            {aplicando.id_variante === null ? "O anúncio continua com o texto de hoje" : "O título, o texto e o botão dela passam a ser os do anúncio"},
            e todas as variações saem — o teste acaba. Os números continuam neste relatório.
          </p>
        </Confirmacao>
      )}
    </Cartao>
  );
}
