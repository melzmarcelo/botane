"use client";

import { Campo } from "@/components/ui";
import type { ConfigAssistente, GravarConfigAssistente } from "@/lib/assistente";

/**
 * O áudio do assistente: o serviço que transforma a nota de voz em texto (etapa 3, migração 153).
 *
 * 🔑 Pedido do dono (06/11/2026): *"pela manhã mando um áudio ou um texto…"*. A API do Claude
 * não ouve áudio; OpenAI e Groq transcrevem no mesmo formato, então a casa escolhe o provedor e
 * cadastra a chave dele aqui. ⚠️ A chave nunca volta do servidor (em branco ao salvar, mantém).
 */
export default function AudioDoAssistente({
  cfg,
  form,
  mudar,
}: {
  cfg: ConfigAssistente;
  form: GravarConfigAssistente;
  mudar: <K extends keyof GravarConfigAssistente>(k: K, v: GravarConfigAssistente[K]) => void;
}) {
  const provedor = cfg.provedores_transcricao.find((p) => p.id === form.transcricao_provedor);
  const mesmoProvedor = form.transcricao_provedor === cfg.transcricao_provedor;

  return (
    <div className="flex flex-col gap-3 border-t border-linha pt-4" id="audio-assistente">
      <p className="text-[14px] font-semibold">Áudio</p>
      <p className="text-[13.5px] text-suave prosa">
        Para ouvir notas de voz, o assistente usa um serviço que transforma fala em texto. Sem ele,
        responde só a mensagens escritas — e avisa quem mandar áudio.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Campo rotulo="Serviço de transcrição">
          <select className="campo" aria-label="serviço de transcrição" value={form.transcricao_provedor}
                  onChange={(e) => mudar("transcricao_provedor", e.target.value as GravarConfigAssistente["transcricao_provedor"])}>
            <option value="">Nenhum — não ouvir áudio</option>
            {cfg.provedores_transcricao.map((p) => (
              <option key={p.id} value={p.id}>{p.nome}</option>
            ))}
          </select>
        </Campo>
        {provedor && (
          <>
            <Campo rotulo={`Chave da ${provedor.nome}`}
                   dica={mesmoProvedor && cfg.transcricao_chave_configurada ? "configurada — em branco mantém" : "criada no painel do serviço"}>
              <input className="campo mono" type="password" autoComplete="off" aria-label="chave da transcrição"
                     placeholder={mesmoProvedor && cfg.transcricao_chave_configurada ? "••••••••" : ""}
                     value={form.transcricao_chave} onChange={(e) => mudar("transcricao_chave", e.target.value)} />
            </Campo>
            <Campo rotulo="Modelo" dica={`Em branco: ${provedor.modelo}.`}>
              <input className="campo mono" aria-label="modelo da transcrição" placeholder={provedor.modelo}
                     value={form.transcricao_modelo} onChange={(e) => mudar("transcricao_modelo", e.target.value)} />
            </Campo>
          </>
        )}
      </div>
      {provedor && (
        <p className="text-[13px] text-suave prosa">
          O áudio vai para a {provedor.nome} só para virar texto e não fica guardado aqui — fica o texto
          ouvido, que a resposta mostra para a pessoa conferir. Custa centavos por minuto de áudio,
          cobrados na conta de quem cadastrou a chave. Para ouvir, o número precisa do token da Meta.
        </p>
      )}
    </div>
  );
}
