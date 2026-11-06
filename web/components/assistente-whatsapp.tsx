"use client";

import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Cartao, Etiqueta } from "@/components/ui";
import {
  desvincularAssistente,
  gerarCodigoAssistente,
  vinculoAssistente,
  type CodigoAssistente,
  type VinculoAssistente,
} from "@/lib/assistente";

/**
 * O WhatsApp do assistente no Perfil (etapa 1, migração 151).
 *
 * 🔑 **Pedido do dono (06/11/2026):** *"no meu usuário vou vincular o meu número de telefone"*.
 * ⚠️ **O telefone não é digitado aqui, de propósito**: a pessoa recebe um código e o manda do
 * próprio WhatsApp; o número que fica é o que a Meta entregou. Prova a posse e evita o nono
 * dígito. O código em claro só existe na resposta de "Gerar código" — recarregar a tela o perde,
 * e aí se gera outro.
 */
export default function AssistenteWhatsapp() {
  const aviso = useAviso();
  const [estado, setEstado] = useState<VinculoAssistente | null>(null);
  const [codigo, setCodigo] = useState<CodigoAssistente | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [confirmando, setConfirmando] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setEstado(await vinculoAssistente());
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível carregar o assistente");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function gerar() {
    setOcupado(true);
    try {
      const c = await gerarCodigoAssistente();
      setCodigo(c);
      setEstado(c);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gerar o código");
    } finally {
      setOcupado(false);
    }
  }

  async function desvincular() {
    setOcupado(true);
    try {
      setEstado(await desvincularAssistente());
      setCodigo(null);
      setConfirmando(false);
      aviso.sucesso("WhatsApp desligado do seu usuário");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível desvincular");
    } finally {
      setOcupado(false);
    }
  }

  const semNumero = estado && !estado.assistente;

  return (
    <Cartao
      className="max-w-[560px]"
      titulo="Assistente no WhatsApp"
      descricao="Pergunte pelo WhatsApp, por texto ou áudio: suas pendências do dia, uma receita, o estoque, as vendas — de todas as suas lojas, com as suas permissões. Por enquanto ele só consulta; lançar produção chega em breve."
    >
      <div className="flex flex-col gap-4" id="assistente-whatsapp">
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        {!estado && !erro && <p className="text-[14px] text-suave">Carregando…</p>}

        {estado && (
          <div className="flex flex-wrap items-center gap-2" data-vinculado={estado.vinculado}>
            {estado.vinculado ? (
              <>
                <Etiqueta cor="erva">vinculado</Etiqueta>
                <span className="mono text-[14px]">{estado.telefone}</span>
              </>
            ) : (
              <Etiqueta>nenhum WhatsApp vinculado</Etiqueta>
            )}
          </div>
        )}

        {semNumero && (
          <Aviso tipo="info">
            O número do assistente ainda não está ligado. Quem administra o sistema o configura em
            Integrações ▸ Assistente.
          </Aviso>
        )}

        {codigo && (
          // ⚠️ `div` com a forma do `Aviso`: parágrafo com link e botão dentro é HTML inválido.
          <div className="aviso aviso-ok" role="status" id="codigo-assistente">
            <p className="font-semibold">Mande esta mensagem do seu WhatsApp em até 15 minutos:</p>
            <p className="mono mt-2 text-[18px] tracking-wider">{codigo.mensagem}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <a className="btn btn-primario" href={codigo.assistente.link} target="_blank" rel="noreferrer">
                Abrir no WhatsApp
              </a>
              <button
                type="button"
                className="btn btn-secundario"
                onClick={() => {
                  void navigator.clipboard?.writeText(codigo.mensagem);
                  aviso.sucesso("Mensagem copiada");
                }}
              >
                Copiar
              </button>
            </div>
            <p className="mt-2 text-[13px]">
              Pelo computador? Mande para {codigo.assistente.numero}.
              Depois de enviar, o assistente responde e{" "}
              <button type="button" className="link-acao" onClick={() => { setCodigo(null); void carregar(); }}>
                esta tela atualiza aqui
              </button>.
            </p>
          </div>
        )}

        {estado && (
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="btn btn-secundario" onClick={gerar}
                    disabled={ocupado || !!semNumero} aria-busy={ocupado} id="gerar-codigo-assistente">
              {estado.vinculado ? "Trocar de WhatsApp" : "Vincular meu WhatsApp"}
            </button>
            {estado.vinculado && !confirmando && (
              <button type="button" className="link-acao text-[13px]" onClick={() => setConfirmando(true)}>
                desvincular
              </button>
            )}
            {confirmando && (
              <>
                <span className="text-[13px]">O assistente deixa de atender este número.</span>
                <button type="button" className="btn btn-perigo" onClick={desvincular} disabled={ocupado}>
                  Desvincular
                </button>
                <button type="button" className="link-acao text-[13px]" onClick={() => setConfirmando(false)}>
                  cancelar
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </Cartao>
  );
}
