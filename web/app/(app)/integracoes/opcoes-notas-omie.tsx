"use client";

/**
 * As duas opções de notas do Omie: "somente recebidas" e "lançar notas recebidas".
 *
 * 🔑 Pedido do dono (23/10/2026). "Recebida" é a marca `cRecebido` do Omie, não o
 * número da etapa. ⚠️ Mora num arquivo à parte porque `omie.tsx` já passa de 790
 * linhas; o estado continua no formulário de lá, que salva tudo junto.
 */
export default function OpcoesNotasOmie({
  soRecebidas,
  lancarRecebidas,
  lancarDesde,
  aguardandoDesde,
  desabilitado,
  aoMudar,
}: {
  soRecebidas: boolean;
  lancarRecebidas: boolean;
  /** Desde quando o lançamento automático vale (o que veio do servidor). */
  lancarDesde: string | null;
  /** A nota mais antiga que esperava recebimento na última busca. */
  aguardandoDesde: string | null;
  desabilitado: boolean;
  aoMudar: (campo: "so_recebidas" | "lancar_recebidas", valor: boolean) => void;
}) {
  return (
    <section id="opcoes-notas-omie" className="rounded border border-linha bg-fundo p-4">
      <p className="rotulo">Notas recebidas</p>
      <p className="mt-1 max-w-[70ch] text-[13px] leading-snug prosa text-suave">
        No Omie a nota passa por etapas — faturada pelo fornecedor, recebida, conferida. Estas
        opções olham a marca de <b>recebida</b> de cada nota.
      </p>

      <label className="mt-3 flex items-start gap-2">
        <input
          type="checkbox"
          className="mt-1 h-4 w-4 accent-erva"
          disabled={desabilitado}
          checked={soRecebidas}
          onChange={(e) => aoMudar("so_recebidas", e.target.checked)}
        />
        <span className="text-[14px]">
          <b>Somente recebidas</b>
          <span className="block text-[13px] leading-snug text-suave">
            A busca só traz a nota que já foi recebida no Omie. A que ainda não foi fica para a
            próxima busca — o sistema lembra dela e volta a procurar até 60 dias para trás.
            {/* ⚠️ Dito aqui: quem liga espera ver a fila esvaziar, e ela não esvazia. */}
            {" "}As notas que já estão aqui continuam na fila.
          </span>
          {soRecebidas && aguardandoDesde && (
            <span className="block text-[13px] text-suave">
              Esperando recebimento desde{" "}
              {aguardandoDesde.slice(0, 10).split("-").reverse().join("/")}.
            </span>
          )}
        </span>
      </label>

      <label className="mt-3 flex items-start gap-2">
        <input
          type="checkbox"
          className="mt-1 h-4 w-4 accent-erva"
          disabled={desabilitado}
          checked={lancarRecebidas}
          onChange={(e) => aoMudar("lancar_recebidas", e.target.checked)}
        />
        <span className="text-[14px]">
          <b>Lançar notas recebidas</b>
          <span className="block text-[13px] leading-snug text-suave">
            A nota recebida no Omie entra no estoque na própria busca, sem clicar em lançar —
            desde que esteja pronta: todo item com produto, produto com unidade e período aberto.
            A que pede conferência de conversão, ou tem item pendente, fica na fila como hoje.
            Quem salva esta tela assina os lançamentos.
          </span>
          {/* 🔑 As conciliadas que já esperavam NÃO entram: ligar a opção não pode
              despejar o atraso no razão (append-only) sem ninguém olhar. */}
          <span className="block text-[13px] leading-snug text-alerta">
            Vale para as notas que chegarem depois de ligar. As que já estão esperando continuam
            no “Lançar as conciliadas”, com a prévia.
          </span>
          {lancarRecebidas && lancarDesde && (
            <span className="block text-[13px] text-suave">
              Ligado em {new Date(lancarDesde).toLocaleString("pt-BR")}.
            </span>
          )}
        </span>
      </label>
    </section>
  );
}
