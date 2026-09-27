"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import ExplicaTela from "@/components/explica-tela";
import { Aviso, Carregando, Cartao, Confirmacao, Vazio } from "@/components/ui";
import {
  cancelarPedido,
  codigosDoCaixa,
  selosDoPedido,
  type CodigosDoCaixa,
  type PedidoDeCodigo,
} from "@/lib/fidelidade";

/**
 * Fidelidade → Códigos: a tela do CAIXA no método "código de confirmação".
 *
 * 🔑 **Pedido do dono (27/09/2026):** *"na tela do nosso sistema vão aparecer os códigos e
 * clientes. O usuário vê que tem um código gerado para o cliente e deve passar este para o
 * cliente confirmar a visita. E pode informar a quantidade de selos que o cliente recebeu
 * nesta visita, por padrão 1."*
 *
 * ⚠️ **Atualiza sozinha** (a cada 5 s): o cliente lê o QR no balcão e o código tem de
 * aparecer aqui sem ninguém apertar F5. Pausa com a aba escondida — ninguém está olhando.
 * ⚠️ **Os selos se ajustam ANTES de o cliente digitar**: confirmado, o pedido sai da lista.
 */
const INTERVALO_MS = 5000;

function telefone(t: string) {
  const m = t.match(/^(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : t;
}

const hora = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "—";

function Restante({ ate }: { ate: string }) {
  const [agora, setAgora] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setAgora(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const s = Math.max(0, Math.round((new Date(ate).getTime() - agora) / 1000));
  return (
    <span className={`mono ${s < 60 ? "text-[var(--color-erro)]" : "text-suave"}`}>
      {Math.floor(s / 60)}:{String(s % 60).padStart(2, "0")}
    </span>
  );
}

function Pedido({
  p,
  aoMudar,
  aoCancelar,
}: {
  p: PedidoDeCodigo;
  aoMudar: (selos: number) => void;
  aoCancelar: () => void;
}) {
  return (
    <li className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-[12px] border border-[var(--color-linha)] bg-[var(--color-superficie)] p-4">
      <div className="min-w-[180px] flex-1">
        <p className="text-[16px] font-semibold">{p.nome}</p>
        <p className="mono text-[13px] text-suave">{telefone(p.telefone)}</p>
        <p className="mt-1 text-[12.5px] text-suave">
          pediu às {hora(p.criada_em)} · vence em <Restante ate={p.expira_em} />
          {p.tentativas > 0 && ` · ${p.tentativas} tentativa(s) errada(s)`}
        </p>
      </div>
      {/* O código é o que se FALA ao cliente: grande, espaçado, fácil de ler de longe. */}
      <div className="text-center">
        <p className="text-[11px] uppercase tracking-wide text-suave">código</p>
        <p className="mono text-[34px] font-bold leading-none tracking-[0.2em]">{p.codigo}</p>
      </div>
      <div className="text-center">
        <p className="mb-1 text-[11px] uppercase tracking-wide text-suave">selos</p>
        <div className="flex items-center gap-1">
          <button type="button" className="btn btn-secundario h-9 w-9 p-0" aria-label="menos um selo"
                  disabled={p.selos <= 1} onClick={() => aoMudar(p.selos - 1)}>
            −
          </button>
          <span className="mono w-9 text-center text-[20px] font-bold">{p.selos}</span>
          <button type="button" className="btn btn-secundario h-9 w-9 p-0" aria-label="mais um selo"
                  disabled={p.selos >= 100} onClick={() => aoMudar(p.selos + 1)}>
            +
          </button>
        </div>
      </div>
      <button type="button" className="link-acao link-acao-erro" onClick={aoCancelar}>
        cancelar
      </button>
    </li>
  );
}

export default function CodigosDoCaixa() {
  const aviso = useAviso();
  const [dados, setDados] = useState<CodigosDoCaixa | null>(null);
  const [erro, setErro] = useState("");
  const [cancelando, setCancelando] = useState<PedidoDeCodigo | null>(null);

  const carregar = useCallback(async () => {
    try {
      setDados(await codigosDoCaixa());
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar os códigos");
    }
  }, []);

  useEffect(() => {
    void carregar();
    const t = setInterval(() => {
      if (document.visibilityState === "visible") void carregar();
    }, INTERVALO_MS);
    return () => clearInterval(t);
  }, [carregar]);

  async function mudarSelos(p: PedidoDeCodigo, selos: number) {
    // Mostra na hora; o servidor confirma na próxima leitura.
    setDados((d) => d && {
      ...d,
      pendentes: d.pendentes.map((x) => (x.id === p.id ? { ...x, selos } : x)),
    });
    try {
      await selosDoPedido(p.id, selos);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível mudar os selos");
      void carregar();
    }
  }

  async function cancelar(p: PedidoDeCodigo) {
    setCancelando(null);
    try {
      const r = await cancelarPedido(p.id);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível cancelar");
    }
    void carregar();
  }

  if (!dados && !erro) return <Carregando />;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Portal de Clientes · Fidelidade</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Códigos</h1>
        <ExplicaTela>
          O cliente lê o QR code do caixa e fica esperando um código. Ele aparece aqui: confira
          o nome, ajuste os selos desta visita e fale o código para o cliente digitar.
        </ExplicaTela>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {dados && dados.metodo !== "CODIGO_CAIXA" && (
        <Aviso tipo="info">
          O método em uso é o <b>QR code na mesa</b> — a visita conta sozinha e nenhum código é
          gerado. Para usar o código do caixa, mude em{" "}
          <Link href="/fidelidade/configuracao" className="link-acao">Fidelidade → Configuração</Link>.
        </Aviso>
      )}

      <Cartao titulo={`Aguardando código (${dados?.pendentes.length ?? 0})`}
              descricao="Atualiza sozinho a cada 5 segundos.">
        {!dados?.pendentes.length ? (
          <Vazio>Nenhum cliente esperando código agora.</Vazio>
        ) : (
          <ul className="flex flex-col gap-3">
            {dados.pendentes.map((p) => (
              <Pedido key={p.id} p={p} aoMudar={(n) => void mudarSelos(p, n)}
                      aoCancelar={() => setCancelando(p)} />
            ))}
          </ul>
        )}
      </Cartao>

      {!!dados?.confirmados.length && (
        <Cartao titulo={`Confirmados hoje (${dados.confirmados.length})`}>
          <ul className="flex flex-col gap-px bg-[var(--color-linha)]">
            {dados.confirmados.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 bg-[var(--color-superficie)] py-2.5">
                <span>
                  <span className="font-medium">{p.nome}</span>
                  <span className="mono ml-2 text-[12.5px] text-suave">{telefone(p.telefone)}</span>
                </span>
                <span className="text-[13px] text-suave">
                  {p.selos} selo(s) · às {hora(p.confirmada_em)}
                </span>
              </li>
            ))}
          </ul>
        </Cartao>
      )}

      {cancelando && (
        <Confirmacao
          titulo="Cancelar este pedido de código?"
          perigo
          rotuloConfirmar="Sim, cancelar"
          aoConfirmar={() => void cancelar(cancelando)}
          aoCancelar={() => setCancelando(null)}
        >
          <p>
            O código de <b>{cancelando.nome}</b> deixa de valer. Se foi engano, o cliente lê o
            QR code do caixa de novo e ganha outro.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
