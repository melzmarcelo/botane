"use client";

import { Campo } from "@/components/ui";
import type { ConfigAssistente, GravarConfigAssistente } from "@/lib/assistente";

/**
 * O "bom dia" do assistente: a mensagem da manhã com a contagem das pendências (etapa 5, migração 155).
 *
 * ⚠️ Mensagem que o sistema INICIA é sempre um modelo aprovado pela Meta — por isso a tela traz o
 * texto pronto para a casa cadastrar (categoria Utilidade), com os dois botões de resposta rápida.
 * Cada pessoa ainda escolhe receber, no Perfil: ligar aqui não manda nada a ninguém sozinho.
 */
const DIAS = [
  { n: 1, r: "Seg" }, { n: 2, r: "Ter" }, { n: 3, r: "Qua" }, { n: 4, r: "Qui" },
  { n: 5, r: "Sex" }, { n: 6, r: "Sáb" }, { n: 7, r: "Dom" },
];

export default function BomDiaDoAssistente({
  cfg,
  form,
  mudar,
}: {
  cfg: ConfigAssistente;
  form: GravarConfigAssistente;
  mudar: <K extends keyof GravarConfigAssistente>(k: K, v: GravarConfigAssistente[K]) => void;
}) {
  const alternarDia = (n: number) =>
    mudar("bom_dia_dias", form.bom_dia_dias.includes(n)
      ? form.bom_dia_dias.filter((d) => d !== n)
      : [...form.bom_dia_dias, n].sort());
  const copiar = (t: string) => void navigator.clipboard?.writeText(t);

  return (
    <div className="flex flex-col gap-3 border-t border-linha pt-4" id="bomdia-assistente">
      <p className="text-[14px] font-semibold">Bom dia</p>
      <label className="flex items-start gap-3">
        <input type="checkbox" className="mt-1" checked={form.bom_dia_ligado} aria-label="ligar o bom dia"
               onChange={(e) => mudar("bom_dia_ligado", e.target.checked)} />
        <span className="text-[14px]">
          Mandar um bom dia com as pendências
          <span className="block text-[13px] text-suave">
            Só para quem escolher receber, em Perfil ▸ Assistente no WhatsApp. A mensagem diz quantos
            itens a pessoa tem na agenda de produção hoje, com os botões “Ver pendências” (o assistente
            responde tudo) e “Parar o bom dia”.
          </span>
        </span>
      </label>

      {form.bom_dia_ligado && (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo rotulo="Horário" dica="Manda até duas horas depois disso, se o sistema estiver fora no horário.">
              <input className="campo" type="time" aria-label="horário do bom dia" value={form.bom_dia_hora}
                     onChange={(e) => mudar("bom_dia_hora", e.target.value)} />
            </Campo>
            <div>
              <span className="rotulo">Dias</span>
              <div className="mt-1.5 flex flex-wrap gap-1.5" role="group" aria-label="dias do bom dia">
                {DIAS.map((d) => (
                  <button key={d.n} type="button" aria-pressed={form.bom_dia_dias.includes(d.n)}
                          data-dia={d.n} onClick={() => alternarDia(d.n)}
                          className={`min-h-[36px] rounded-full border px-3 text-[13px] ${form.bom_dia_dias.includes(d.n)
                            ? "border-erva bg-erva text-white" : "border-linha text-suave hover:border-erva"}`}>
                    {d.r}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <label className="flex items-center gap-2 text-[14px]">
            <input type="checkbox" checked={form.bom_dia_so_com_pendencia} aria-label="só com pendência"
                   onChange={(e) => mudar("bom_dia_so_com_pendencia", e.target.checked)} />
            Só mandar para quem tiver pendência no dia
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo rotulo="Nome do modelo na Meta" dica={`Em branco: ${cfg.bom_dia.modelo || "botane_bom_dia"}.`}>
              <input className="campo mono" aria-label="nome do modelo" placeholder="botane_bom_dia"
                     value={form.bom_dia_modelo} onChange={(e) => mudar("bom_dia_modelo", e.target.value)} />
            </Campo>
            <Campo rotulo="Idioma do modelo" dica="Em branco: pt_BR.">
              <input className="campo mono" aria-label="idioma do modelo" placeholder="pt_BR"
                     value={form.bom_dia_idioma} onChange={(e) => mudar("bom_dia_idioma", e.target.value)} />
            </Campo>
          </div>
          <div className="rounded-[10px] bg-[var(--color-superficie2)] p-3 text-[13px]">
            <p className="mb-2 font-semibold">Cadastre este modelo na Meta (categoria Utilidade):</p>
            <p className="mono break-words">{cfg.bom_dia.texto_do_modelo}{" "}
              <button type="button" className="link-acao" onClick={() => copiar(cfg.bom_dia.texto_do_modelo)}>copiar</button>
            </p>
            <p className="mt-1">Botões de resposta rápida, nesta ordem: {cfg.bom_dia.botoes.map((b) => `“${b}”`).join(" e ")}.</p>
            <p className="mt-1 text-suave">
              {"{{1}}"} é o primeiro nome; {"{{2}}"} é a contagem (“3 itens”). É a única mensagem do
              assistente que a Meta cobra: as respostas a quem escreveu primeiro são de graça.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
