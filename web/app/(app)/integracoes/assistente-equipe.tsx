"use client";

import { Campo } from "@/components/ui";
import type { ConfigAssistente, GravarConfigAssistente, TipoAvisoEquipe } from "@/lib/assistente";

/**
 * Os avisos à EQUIPE (etapa 6, migração 164): reserva nova e pedido novo pelo site, com os botões
 * Confirmar e Recusar no WhatsApp de quem cuida.
 *
 * 🔑 Pedido do dono (25/11/2026): *"avisar a loja que tem uma nova reserva, e este confirma … pelo
 * sistema ou pelo próprio WhatsApp"*. Recebe quem escolher no Perfil e tiver a permissão de agir
 * naquela loja; o toque age com a permissão dessa pessoa. Ligar aqui não manda nada sozinho.
 * ⚠️ Mensagem que o sistema inicia é MODELO aprovado pela Meta: a tela traz o texto pronto.
 */
const CAMPOS: Record<TipoAvisoEquipe, { ligado: "equipe_reserva_ligado" | "equipe_pedido_ligado";
  modelo: "equipe_reserva_modelo" | "equipe_pedido_modelo"; quando: string }> = {
  reserva: { ligado: "equipe_reserva_ligado", modelo: "equipe_reserva_modelo",
             quando: "Quando o cliente reserva pelo site e a reserva fica aguardando a casa." },
  pedido: { ligado: "equipe_pedido_ligado", modelo: "equipe_pedido_modelo",
            quando: "Quando chega um pedido do site (retirada ou entrega)." },
};

export default function EquipeDoAssistente({
  cfg,
  form,
  mudar,
}: {
  cfg: ConfigAssistente;
  form: GravarConfigAssistente;
  mudar: <K extends keyof GravarConfigAssistente>(k: K, v: GravarConfigAssistente[K]) => void;
}) {
  const copiar = (t: string) => void navigator.clipboard?.writeText(t);
  const tipos: TipoAvisoEquipe[] = ["reserva", "pedido"];
  const algum = form.equipe_reserva_ligado || form.equipe_pedido_ligado;

  return (
    <div className="flex flex-col gap-3 border-t border-linha pt-4" id="equipe-assistente">
      <p className="text-[14px] font-semibold">Avisos à equipe</p>
      {tipos.map((t) => {
        const c = CAMPOS[t];
        const casa = cfg.equipe[t];
        return (
          <div key={t} className="flex flex-col gap-2" data-aviso={t}>
            <label className="flex items-start gap-3">
              <input type="checkbox" className="mt-1" checked={form[c.ligado]} aria-label={`ligar ${casa.titulo}`}
                     onChange={(e) => mudar(c.ligado, e.target.checked)} />
              <span className="text-[14px]">
                {casa.titulo}
                <span className="block text-[13px] text-suave">
                  {c.quando} Vai a quem escolheu receber no Perfil e pode agir na loja, com os botões
                  “{cfg.equipe.botoes.join("” e “")}”.
                </span>
              </span>
            </label>
            {form[c.ligado] && (
              <div className="ml-7 flex flex-col gap-2">
                <Campo rotulo="Nome do modelo na Meta" dica={`Em branco: ${casa.modelo}.`}>
                  <input className="campo mono" aria-label={`nome do modelo ${t}`} placeholder={casa.modelo}
                         value={form[c.modelo]} onChange={(e) => mudar(c.modelo, e.target.value)} />
                </Campo>
                <div className="rounded-[10px] bg-[var(--color-superficie2)] p-3 text-[13px]">
                  <p className="mb-1 font-semibold">Cadastre na Meta (categoria Utilidade):</p>
                  <p className="mono break-words">{casa.texto_do_modelo}{" "}
                    <button type="button" className="link-acao" onClick={() => copiar(casa.texto_do_modelo)}>copiar</button>
                  </p>
                  <p className="mt-1">
                    Botões de resposta rápida, nesta ordem: {cfg.equipe.botoes.map((b) => `“${b}”`).join(" e ")}.
                  </p>
                </div>
              </div>
            )}
          </div>
        );
      })}
      {algum && (
        <Campo rotulo="Idioma dos modelos" dica="Em branco: pt_BR.">
          <input className="campo mono max-w-[200px]" aria-label="idioma dos avisos à equipe" placeholder="pt_BR"
                 value={form.equipe_idioma} onChange={(e) => mudar("equipe_idioma", e.target.value)} />
        </Campo>
      )}
    </div>
  );
}
