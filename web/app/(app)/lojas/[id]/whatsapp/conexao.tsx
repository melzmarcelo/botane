"use client";

import { Aviso, Campo, Cartao, Etiqueta } from "@/components/ui";
import type { GravarWhatsapp, WhatsappDaLoja } from "@/lib/whatsapp";

/**
 * A conexão com a Meta: o que a loja copia de lá e cola aqui (e o que cola lá).
 *
 * ⚠️ **Token e segredo nunca voltam do servidor** — a tela mostra "configurado" e o campo
 * em branco. Deixar em branco ao salvar mantém o que já está.
 */
export default function ConexaoDoWhatsapp({
  dados,
  form,
  aoMudar,
  podeEditar,
}: {
  dados: WhatsappDaLoja;
  form: GravarWhatsapp;
  aoMudar: (f: GravarWhatsapp) => void;
  podeEditar: boolean;
}) {
  const mudar = <K extends keyof GravarWhatsapp>(k: K, v: GravarWhatsapp[K]) =>
    aoMudar({ ...form, [k]: v });
  const copiar = (t: string) => void navigator.clipboard?.writeText(t);

  return (
    <Cartao
      titulo="Conexão com a Meta"
      descricao="A API oficial do WhatsApp Business (Cloud API). A loja faz a validação na Meta e informa aqui."
      acao={
        dados.ativa ? (
          <Etiqueta cor={dados.modo === "real" ? "erva" : "alerta"}>
            {dados.modo === "real" ? "enviando de verdade" : "modo simulado"}
          </Etiqueta>
        ) : <Etiqueta>desligado</Etiqueta>
      }
    >
      <div className="flex flex-col gap-5">
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1" disabled={!podeEditar} checked={form.ativa}
                 onChange={(e) => mudar("ativa", e.target.checked)} />
          <span className="text-[14px]">
            Usar WhatsApp nesta loja
            <span className="block text-[13px] text-suave">
              Desligado, nenhum aviso entra na fila — nem simulado.
            </span>
          </span>
        </label>

        <fieldset disabled={!podeEditar} className="grid gap-2 sm:grid-cols-2" role="radiogroup">
          {[
            { v: "simulado" as const, r: "Modo simulado",
              d: "As mensagens vão só para o histórico. Use enquanto a conta na Meta não está pronta." },
            { v: "real" as const, r: "Enviar de verdade",
              d: "Pela API da Meta, com o número e os modelos aprovados. Cada mensagem é cobrada pela Meta." },
          ].map((o) => (
            <button key={o.v} type="button" role="radio" aria-checked={form.modo === o.v}
                    onClick={() => mudar("modo", o.v)}
                    className={`rounded-[10px] border p-3 text-left ${form.modo === o.v
                      ? "border-[var(--color-erva)] bg-[var(--color-erva-claro)]"
                      : "border-[var(--color-linha)] hover:border-[var(--color-erva)]"}`}>
              <b className="block text-[14px]">{o.r}</b>
              <span className="text-[12.5px] text-suave">{o.d}</span>
            </button>
          ))}
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2">
          <Campo rotulo="Número (como aparece)" dica="só para exibir — ex.: (47) 99910-5033">
            <input className="campo mono" disabled={!podeEditar} value={form.numero ?? ""}
                   onChange={(e) => mudar("numero", e.target.value)} />
          </Campo>
          <Campo rotulo="Identificação do número (Phone number ID)" dica="Meta → WhatsApp → Configuração da API">
            <input className="campo mono" disabled={!podeEditar} value={form.phone_number_id ?? ""}
                   onChange={(e) => mudar("phone_number_id", e.target.value)} />
          </Campo>
          <Campo rotulo="Conta do WhatsApp Business (WABA ID)" opcional>
            <input className="campo mono" disabled={!podeEditar} value={form.waba_id ?? ""}
                   onChange={(e) => mudar("waba_id", e.target.value)} />
          </Campo>
          <Campo rotulo="Versão da API" dica="ex.: v21.0">
            <input className="campo mono" disabled={!podeEditar} value={form.api_versao}
                   onChange={(e) => mudar("api_versao", e.target.value)} />
          </Campo>
          <Campo rotulo="Token de acesso permanente"
                 dica={dados.token_configurado ? "configurado — em branco mantém" : "do usuário do sistema, na Meta"}>
            <input className="campo mono" type="password" autoComplete="off" disabled={!podeEditar}
                   placeholder={dados.token_configurado ? "••••••••" : ""} value={form.token}
                   onChange={(e) => mudar("token", e.target.value)} />
          </Campo>
          <Campo rotulo="Chave secreta do app (App secret)"
                 dica={dados.segredo_configurado ? "configurada — em branco mantém" : "confere a assinatura do webhook"}>
            <input className="campo mono" type="password" autoComplete="off" disabled={!podeEditar}
                   placeholder={dados.segredo_configurado ? "••••••••" : ""} value={form.app_secret}
                   onChange={(e) => mudar("app_secret", e.target.value)} />
          </Campo>
        </div>

        <div className="rounded-[10px] bg-[var(--color-superficie2)] p-3 text-[13px]">
          <p className="mb-2 font-semibold">Na Meta, em WhatsApp → Configuração → Webhook, informe:</p>
          <p className="break-all">
            URL de retorno: <span className="mono">{dados.webhook_url}</span>{" "}
            <button type="button" className="link-acao" onClick={() => copiar(dados.webhook_url)}>copiar</button>
          </p>
          <p className="break-all">
            Token de verificação: <span className="mono">{dados.verify_token}</span>{" "}
            <button type="button" className="link-acao" onClick={() => copiar(dados.verify_token)}>copiar</button>
          </p>
          <p className="mt-1 text-suave">E assine o campo <span className="mono">messages</span>.</p>
        </div>

        {dados.ultimo_status === "erro" && dados.ultima_mensagem && (
          <Aviso tipo="erro">Último envio falhou: {dados.ultima_mensagem}</Aviso>
        )}

        <details className="text-[13px]">
          <summary className="cursor-pointer font-semibold">Passo a passo na Meta</summary>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-suave">
            <li>Em business.facebook.com, use o portfólio empresarial da casa (verifique a empresa, se a Meta pedir).</li>
            <li>Em developers.facebook.com, crie um app do tipo Empresa e adicione o produto WhatsApp.</li>
            <li>Adicione o número da casa (o atual pode ser usado — siga a opção de usar com o app WhatsApp Business, se oferecida).</li>
            <li>Crie um usuário do sistema com acesso ao app e gere um token permanente com as permissões de WhatsApp. Cole acima.</li>
            <li>Copie o Phone number ID e a App secret (Configurações do app → Básico). Cole acima.</li>
            <li>Configure o webhook com a URL e o token acima.</li>
            <li>Cadastre os modelos de mensagem (abaixo, cada aviso traz o texto pronto) e espere a aprovação.</li>
            <li>Ligue os avisos, teste, e mude para “Enviar de verdade”.</li>
          </ol>
        </details>
      </div>
    </Cartao>
  );
}
