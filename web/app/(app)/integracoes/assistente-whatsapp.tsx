"use client";

import { useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Cartao } from "@/components/ui";
import * as assist from "@/lib/assistente";

/**
 * O número do assistente no WhatsApp — UM, da casa toda (etapa 1, migração 151).
 *
 * 🔑 Pedido do dono (06/11/2026): *"este número poderia ser compartilhado entre lojas. Pois eu
 * posso ter acesso às duas lojas, e quando pergunto o que tenho de pendência, poderia encontrar
 * coisas de duas lojas"*. Por isso mora aqui, e não na aba WhatsApp de cada loja (que é dos
 * CLIENTES). O que cada pessoa vê é decidido pelo usuário dela.
 * ⚠️ Token e segredo nunca voltam do servidor: a tela mostra "configurado" e o campo em branco,
 * que ao salvar mantém o que está.
 */
const vazio = (c: assist.ConfigAssistente): assist.GravarConfigAssistente => ({
  ativa: c.ativa, modo: c.modo, numero: c.numero, phone_number_id: c.phone_number_id,
  waba_id: c.waba_id, api_versao: c.api_versao, token: "", app_secret: "",
  modelo: c.modelo, limite_diario: c.limite_diario,
});

export default function AssistenteWhatsappConfig() {
  const aviso = useAviso();
  const [cfg, setCfg] = useState<assist.ConfigAssistente | null>(null);
  const [form, setForm] = useState<assist.GravarConfigAssistente | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  // ⚠️ A carga inicial ignora resposta atrasada (efeito em dobro no desenvolvimento).
  useEffect(() => {
    let vivo = true;
    assist.verConfigAssistente()
      .then((c) => { if (vivo) { setCfg(c); setForm(vazio(c)); } })
      .catch((e) => { if (vivo) setErro(e instanceof Error ? e.message : "Falha ao carregar"); });
    return () => { vivo = false; };
  }, []);

  async function salvar() {
    if (!form) return;
    setOcupado(true);
    try {
      const r = await assist.salvarConfigAssistente(form);
      setCfg(r);
      setForm(vazio(r));
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!cfg || !form) return null;
  const mudar = <K extends keyof assist.GravarConfigAssistente>(k: K, v: assist.GravarConfigAssistente[K]) =>
    setForm({ ...form, [k]: v });
  const copiar = (t: string) => void navigator.clipboard?.writeText(t);

  return (
    <Cartao
      titulo="Assistente no WhatsApp"
      descricao="Um número só, para toda a casa: cada funcionário vincula o próprio WhatsApp em Perfil e conversa com o sistema por ele, com as lojas e permissões do seu usuário."
      acao={
        <button className="btn btn-primario" onClick={() => void salvar()} aria-busy={ocupado} disabled={ocupado}
                id="salvar-assistente">
          Salvar
        </button>
      }
    >
      <div className="flex flex-col gap-4" id="config-assistente">
        {cfg.ativa ? (
          <Aviso tipo={cfg.modo === "real" ? "ok" : "info"}>
            <b>Ligado{cfg.modo === "real" ? "" : ", em modo simulado"}.</b>{" "}
            {cfg.modo === "real"
              ? "Quem vinculou o WhatsApp já conversa com o assistente."
              : "Os vínculos funcionam, mas as respostas não saem para a Meta — use enquanto a conta não está pronta."}
          </Aviso>
        ) : (
          <Aviso tipo="info">
            <b>Desligado.</b> Um número exclusivo, que não esteja no aplicativo do WhatsApp (pode ser
            um fixo virtual, sem chip). Não use um número das lojas: aqueles atendem clientes.
          </Aviso>
        )}

        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1" checked={form.ativa} aria-label="ligar o assistente"
                 onChange={(e) => mudar("ativa", e.target.checked)} />
          <span className="text-[14px]">
            Ligar o assistente
            <span className="block text-[13px] text-suave">
              Desligado, ele não responde nem vincula ninguém.
            </span>
          </span>
        </label>

        <fieldset className="grid gap-2 sm:grid-cols-2" role="radiogroup">
          {[
            { v: "simulado" as const, r: "Modo simulado", d: "As respostas ficam só no sistema. Use enquanto a conta na Meta não está pronta." },
            { v: "real" as const, r: "Enviar de verdade", d: "Pela API da Meta. Resposta a quem escreveu primeiro não é cobrada (janela de 24 h)." },
          ].map((o) => (
            <button key={o.v} type="button" role="radio" aria-checked={form.modo === o.v} data-modo={o.v}
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
          <Campo rotulo="Número do assistente" dica="É para ele que os funcionários mandam mensagem.">
            <input className="campo mono" maxLength={30} placeholder="(47) 3333-4444" aria-label="número do assistente"
                   value={form.numero} onChange={(e) => mudar("numero", e.target.value)} />
          </Campo>
          <Campo rotulo="Identificação do número (Phone number ID)" dica="Meta → WhatsApp → Configuração da API">
            <input className="campo mono" value={form.phone_number_id} aria-label="Phone number ID"
                   onChange={(e) => mudar("phone_number_id", e.target.value)} />
          </Campo>
          <Campo rotulo="Conta do WhatsApp Business (WABA ID)" opcional>
            <input className="campo mono" value={form.waba_id} onChange={(e) => mudar("waba_id", e.target.value)} />
          </Campo>
          <Campo rotulo="Versão da API" dica="ex.: v21.0">
            <input className="campo mono" value={form.api_versao} onChange={(e) => mudar("api_versao", e.target.value)} />
          </Campo>
          <Campo rotulo="Token de acesso permanente"
                 dica={cfg.token_configurado ? "configurado — em branco mantém" : "do usuário do sistema, na Meta"}>
            <input className="campo mono" type="password" autoComplete="off" aria-label="token"
                   placeholder={cfg.token_configurado ? "••••••••" : ""}
                   value={form.token} onChange={(e) => mudar("token", e.target.value)} />
          </Campo>
          <Campo rotulo="Chave secreta do app (App secret)"
                 dica={cfg.segredo_configurado ? "configurada — em branco mantém" : "confere a assinatura do webhook"}>
            <input className="campo mono" type="password" autoComplete="off" aria-label="chave secreta"
                   placeholder={cfg.segredo_configurado ? "••••••••" : ""}
                   value={form.app_secret} onChange={(e) => mudar("app_secret", e.target.value)} />
          </Campo>
        </div>

        <div className="flex flex-col gap-3 border-t border-linha pt-4" id="conversa-assistente">
          <p className="text-[14px] font-semibold">A conversa (Claude)</p>
          {cfg.chave_anthropic ? (
            <p className="text-[13.5px] text-suave">
              Usa a chave da Anthropic cadastrada em Integrações ▸ Tradução. O custo vai para essa conta.
            </p>
          ) : (
            <Aviso tipo="erro">
              Sem a chave da Anthropic o assistente não responde perguntas. Cadastre-a em
              Integrações ▸ Tradução — é a mesma para os dois.
            </Aviso>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo rotulo="Modelo" dica={`Em branco: ${cfg.modelo_padrao}. O claude-haiku-5-5 custa bem menos e responde mais rápido.`}>
              <input className="campo mono" value={form.modelo} placeholder={cfg.modelo_padrao}
                     aria-label="modelo" onChange={(e) => mudar("modelo", e.target.value)} />
            </Campo>
            <Campo rotulo="Perguntas por pessoa, por dia" dica="Um teto de custo: passou dele, o assistente avisa e para até o dia seguinte.">
              <input className="campo" type="number" min={1} max={500} value={form.limite_diario}
                     aria-label="limite por dia"
                     onChange={(e) => mudar("limite_diario", Math.max(1, Number(e.target.value) || 1))} />
            </Campo>
          </div>
          <p className="text-[13px] text-suave prosa">
            Nesta versão o assistente só consulta, com as mesmas permissões e lojas de cada pessoa:
            pendências, receitas, estoque, vendas. As conversas ficam guardadas por 30 dias e não
            aparecem no histórico das lojas.
          </p>
        </div>

        <div className="rounded-[10px] bg-[var(--color-superficie2)] p-3 text-[13px]">
          <p className="mb-2 font-semibold">Na Meta, em WhatsApp → Configuração → Webhook, informe:</p>
          <p className="break-all">
            URL de retorno: <span className="mono">{cfg.webhook_url}</span>{" "}
            <button type="button" className="link-acao" onClick={() => copiar(cfg.webhook_url)}>copiar</button>
          </p>
          <p className="break-all">
            Token de verificação: <span className="mono">{cfg.verify_token}</span>{" "}
            <button type="button" className="link-acao" onClick={() => copiar(cfg.verify_token)}>copiar</button>
          </p>
          <p className="mt-1 text-suave">
            E assine o campo <span className="mono">messages</span>. É o mesmo endereço do WhatsApp das
            lojas: se o número estiver no mesmo app da Meta, o webhook já configurado serve.
          </p>
        </div>

        {cfg.ultimo_status === "erro" && cfg.ultima_mensagem && (
          <Aviso tipo="erro">Último envio falhou: {cfg.ultima_mensagem}</Aviso>
        )}
      </div>
    </Cartao>
  );
}
