"use client";

import { Aviso, Campo } from "@/components/ui";
import type { NumeroDoWhatsapp, NumeroEmEdicao } from "@/lib/whatsapp";

/**
 * A conexão de UM número com a Meta: o que a loja copia de lá e cola aqui (e o que cola lá).
 *
 * 🔑 **146 (pedido do dono, 30/10/2026):** cada número tem a dele — antes era uma por loja.
 * ⚠️ **Token e segredo nunca voltam do servidor** — a tela mostra "configurado" e o campo
 * em branco. Deixar em branco ao salvar mantém o que já está.
 */
export default function ConexaoDoNumero({
  n,
  gravado,
  principal,
  webhookUrl,
  aoMudar,
  podeEditar,
}: {
  n: NumeroEmEdicao;
  /** O que está no servidor (nulo num número que ainda não foi gravado). */
  gravado: NumeroDoWhatsapp | null;
  /** O número principal (para "usar a conta do principal"); nulo se este é o principal. */
  principal: NumeroEmEdicao | null;
  webhookUrl: string;
  aoMudar: (n: NumeroEmEdicao) => void;
  podeEditar: boolean;
}) {
  const mudar = <K extends keyof NumeroEmEdicao>(k: K, v: NumeroEmEdicao[K]) => aoMudar({ ...n, [k]: v });
  const copiar = (t: string) => void navigator.clipboard?.writeText(t);
  const daConta = !!principal && n.conta_do_principal;

  return (
    <div className="flex flex-col gap-4" data-conexao={n.chave}>
      <label className="flex items-start gap-3">
        <input type="checkbox" className="mt-1" disabled={!podeEditar} checked={n.conectado}
               aria-label="conectar este número"
               onChange={(e) => mudar("conectado", e.target.checked)} />
        <span className="text-[14px]">
          Enviar avisos por este número
          <span className="block text-[13px] text-suave">
            Desligado, nada sai por ele — os avisos vão pelo principal, se ele estiver conectado.
          </span>
        </span>
      </label>

      <fieldset disabled={!podeEditar} className="grid gap-2 sm:grid-cols-2" role="radiogroup">
        {[
          { v: "simulado" as const, r: "Modo simulado",
            d: "As mensagens vão só para o histórico. Use enquanto a conta na Meta não está pronta." },
          { v: "real" as const, r: "Enviar de verdade",
            d: "Pela API da Meta, com os modelos aprovados. Cada mensagem é cobrada pela Meta." },
        ].map((o) => (
          <button key={o.v} type="button" role="radio" aria-checked={n.modo === o.v}
                  data-modo={o.v} onClick={() => mudar("modo", o.v)}
                  className={`rounded-[10px] border p-3 text-left ${n.modo === o.v
                    ? "border-[var(--color-erva)] bg-[var(--color-erva-claro)]"
                    : "border-[var(--color-linha)] hover:border-[var(--color-erva)]"}`}>
            <b className="block text-[14px]">{o.r}</b>
            <span className="text-[12.5px] text-suave">{o.d}</span>
          </button>
        ))}
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        <Campo rotulo="Identificação do número (Phone number ID)" dica="Meta → WhatsApp → Configuração da API">
          <input className="campo mono" disabled={!podeEditar} value={n.phone_number_id}
                 aria-label="Phone number ID" onChange={(e) => mudar("phone_number_id", e.target.value)} />
        </Campo>
        <Campo rotulo="Conta do WhatsApp Business (WABA ID)" opcional>
          <input className="campo mono" disabled={!podeEditar} value={n.waba_id}
                 onChange={(e) => mudar("waba_id", e.target.value)} />
        </Campo>
        <Campo rotulo="Versão da API" dica="ex.: v21.0">
          <input className="campo mono" disabled={!podeEditar} value={n.api_versao}
                 onChange={(e) => mudar("api_versao", e.target.value)} />
        </Campo>
      </div>

      {principal && (
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1" disabled={!podeEditar} checked={n.conta_do_principal}
                 aria-label="usar a conta do principal"
                 onChange={(e) => mudar("conta_do_principal", e.target.checked)} />
          <span className="text-[14px]">
            Usar o token e a chave secreta do principal ({principal.rotulo || principal.numero})
            <span className="block text-[13px] text-suave">
              Quando os dois números estão no mesmo app da Meta — o caso comum.
            </span>
          </span>
        </label>
      )}
      {!daConta && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo rotulo="Token de acesso permanente"
                 dica={gravado?.token_configurado ? "configurado — em branco mantém" : "do usuário do sistema, na Meta"}>
            <input className="campo mono" type="password" autoComplete="off" disabled={!podeEditar}
                   aria-label="token" placeholder={gravado?.token_configurado ? "••••••••" : ""}
                   value={n.token} onChange={(e) => mudar("token", e.target.value)} />
          </Campo>
          <Campo rotulo="Chave secreta do app (App secret)"
                 dica={gravado?.segredo_configurado ? "configurada — em branco mantém" : "confere a assinatura do webhook"}>
            <input className="campo mono" type="password" autoComplete="off" disabled={!podeEditar}
                   aria-label="chave secreta" placeholder={gravado?.segredo_configurado ? "••••••••" : ""}
                   value={n.app_secret} onChange={(e) => mudar("app_secret", e.target.value)} />
          </Campo>
        </div>
      )}

      {gravado ? (
        <div className="rounded-[10px] bg-[var(--color-superficie2)] p-3 text-[13px]">
          <p className="mb-2 font-semibold">Na Meta, em WhatsApp → Configuração → Webhook, informe:</p>
          <p className="break-all">
            URL de retorno: <span className="mono">{webhookUrl}</span>{" "}
            <button type="button" className="link-acao" onClick={() => copiar(webhookUrl)}>copiar</button>
          </p>
          <p className="break-all">
            Token de verificação: <span className="mono">{gravado.verify_token}</span>{" "}
            <button type="button" className="link-acao" onClick={() => copiar(gravado.verify_token)}>copiar</button>
          </p>
          <p className="mt-1 text-suave">
            E assine o campo <span className="mono">messages</span>. O webhook é do app: números no
            mesmo app usam um só (qualquer token de verificação da loja serve).
          </p>
        </div>
      ) : (
        <p className="text-[13px] text-suave">O endereço do webhook aparece depois de salvar.</p>
      )}

      {gravado?.ultimo_status === "erro" && gravado.ultima_mensagem && (
        <Aviso tipo="erro">Último envio falhou: {gravado.ultima_mensagem}</Aviso>
      )}
    </div>
  );
}
