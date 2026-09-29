"use client";

import { useCallback, useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Cartao, Confirmacao } from "@/components/ui";
import * as tr from "@/lib/traducao";

/**
 * A chave da Anthropic que traduz o cardápio do site para inglês e alemão.
 *
 * 🔑 Pedido do dono (29/09/2026): *"trocar a informação da chave no servidor por ela ser
 * cadastrada no sistema — aí o cliente pode configurar a sua chave"*. Quem paga a conta da
 * Anthropic a cadastra aqui, sem acesso ao painel do servidor.
 * ⚠️ A chave é cifrada e NUNCA volta inteira — como a senha do e-mail. Campo em branco
 * mantém a guardada.
 */
export default function TraducaoClaude() {
  const aviso = useAviso();
  const [cfg, setCfg] = useState<tr.ConfigTraducao | null>(null);
  const [erro, setErro] = useState("");
  const [chave, setChave] = useState("");
  const [modelo, setModelo] = useState("");
  const [ativa, setAtiva] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const [removendo, setRemovendo] = useState(false);

  const montar = useCallback((c: tr.ConfigTraducao) => {
    setCfg(c);
    setChave("");
    setModelo(c.modelo === c.modelo_padrao ? "" : c.modelo);
    setAtiva(c.chave ? c.ativa : true);
  }, []);

  // Recarregar (depois do teste) só atualiza o que se MOSTRA — nunca apaga o que se digitou.
  const carregar = useCallback(() => {
    tr.verConfig().then(setCfg).catch(() => {});
  }, []);
  // ⚠️ A carga inicial ignora resposta atrasada: a segunda (efeito em dobro no React de
  // desenvolvimento, ou rede lenta) chegaria depois da chave colada e a apagaria.
  useEffect(() => {
    let vivo = true;
    tr.verConfig()
      .then((c) => { if (vivo) montar(c); })
      .catch((e) => { if (vivo) setErro(e instanceof Error ? e.message : "Falha ao carregar"); });
    return () => { vivo = false; };
  }, [montar]);

  async function salvar() {
    setOcupado(true);
    try {
      const r = await tr.salvarConfig({ chave: chave.trim() || null, modelo: modelo.trim() || null, ativa });
      montar(r);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setOcupado(false);
    }
  }

  async function testar() {
    setOcupado(true);
    try {
      const r = await tr.testarConfig();
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "O teste falhou");
    } finally {
      setOcupado(false);
      carregar();
    }
  }

  async function remover() {
    setOcupado(true);
    try {
      const r = await tr.removerChave();
      montar(r);
      aviso.sucesso(r.message);
      setRemovendo(false);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível remover");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!cfg) return null;

  return (
    <Cartao
      titulo="Tradução do cardápio (Claude)"
      descricao="Traduz para inglês e alemão o que o site mostra: catálogos, seções e produtos."
      acao={
        <div className="flex flex-wrap items-center gap-2">
          {cfg.chave && (
            <button className="btn btn-secundario" onClick={() => void testar()} aria-busy={ocupado} disabled={ocupado}>
              Testar a chave
            </button>
          )}
          <button className="btn btn-primario" onClick={() => void salvar()} aria-busy={ocupado} disabled={ocupado}>
            Salvar
          </button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        {cfg.credencial_ilegivel && (
          <Aviso tipo="erro">
            <b>A chave guardada não pode ser lida</b> — foi cifrada com outra
            <span className="mono text-[13px]"> JWT_SECRET</span>. <b>Cole a chave de novo e salve.</b>
          </Aviso>
        )}
        {cfg.ligada ? (
          <Aviso tipo="ok">
            <b>Ligada.</b> Cada catálogo, seção e produto do cardápio é traduzido ao salvar, e de
            novo só quando o português muda.
          </Aviso>
        ) : (
          <Aviso tipo="info">
            <b>Desligada.</b> O site mostra o português onde não houver tradução, e as traduções
            continuam editáveis à mão. Para ligar: crie uma chave em{" "}
            <a className="link" href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener noreferrer">
              console.anthropic.com
            </a>{" "}
            (com crédito na conta, em Billing), cole abaixo e salve.
          </Aviso>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <Campo rotulo={`Chave da Anthropic ${cfg.chave ? `(guardada: ${cfg.chave.slice(-8)})` : ""}`}>
            <input className="campo mono" type="password" autoComplete="new-password"
                   placeholder={cfg.chave ? "deixe em branco para manter" : "sk-ant-…"}
                   value={chave} onChange={(e) => setChave(e.target.value)} />
          </Campo>
          <Campo rotulo="Modelo">
            <input className="campo mono" value={modelo} placeholder={cfg.modelo_padrao}
                   onChange={(e) => setModelo(e.target.value)} />
          </Campo>
        </div>
        <label className="flex items-center gap-2 text-[14px]">
          <input type="checkbox" checked={ativa} onChange={(e) => setAtiva(e.target.checked)} />
          Traduzir automaticamente ao salvar
        </label>

        <p className="text-[13px] text-suave prosa">
          O custo vai para a conta da Anthropic de quem cadastrou a chave: traduzir um cardápio
          inteiro custa centavos. Vale pôr um limite mensal em <i>Settings ▸ Limits</i> lá no console.
          O modelo em branco usa o padrão ({cfg.modelo_padrao}).
        </p>

        {cfg.ultima_mensagem && (
          <p className="text-[13.5px] text-suave">
            Último teste: <b>{cfg.ultimo_status}</b> — {cfg.ultima_mensagem}
          </p>
        )}
        {cfg.chave && (
          <div>
            <button type="button" className="link-acao link-acao-erro text-[13px]" onClick={() => setRemovendo(true)}>
              remover a chave
            </button>
          </div>
        )}
      </div>

      {removendo && (
        <Confirmacao titulo="Remover a chave?" rotuloConfirmar="Remover" perigo ocupado={ocupado}
                     aoConfirmar={() => void remover()} aoCancelar={() => setRemovendo(false)}>
          A tradução automática fica desligada. O que já foi traduzido continua no site.
        </Confirmacao>
      )}
    </Cartao>
  );
}
