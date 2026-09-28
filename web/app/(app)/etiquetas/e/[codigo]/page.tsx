"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao, Etiqueta as Selo } from "@/components/ui";
import Voltar from "@/components/voltar";
import {
  COR_SITUACAO, ROTULO_SITUACAO, dataHora, imprimir, numero, porCodigo, rotuloConservacao,
  rotuloEvento, usar, type Etiqueta,
} from "@/lib/etiquetas";

import Descarte from "../../descarte";

/**
 * O que o QR da etiqueta abre — pensado para o CELULAR, na frente da câmara fria.
 *
 * 🔑 Tudo sobre o pote e as ações que cabem: usei tudo, descartar (lança a perda),
 * descongelar/reetiquetar (nova etiqueta, a antiga deixa de valer) e reimprimir.
 * ⚠️ Precisa de login: a etiqueta não é pública — ela diz o que a casa tem e onde.
 */
export default function EtiquetaPeloCodigo() {
  const { codigo } = useParams<{ codigo: string }>();
  const aviso = useAviso();
  const [e, setE] = useState<Etiqueta | null>(null);
  const [erro, setErro] = useState("");
  const [descartando, setDescartando] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(() => {
    porCodigo(codigo)
      .then((x) => { setE(x); setErro(""); })
      .catch((x) => setErro(x instanceof Error ? x.message : "Etiqueta não encontrada"));
  }, [codigo]);

  useEffect(() => carregar(), [carregar]);

  async function usarTudo() {
    if (!e) return;
    setOcupado(true);
    try {
      const r = await usar(e.id);
      aviso.sucesso(r.message);
      setE({ ...e, ...r });
    } catch (x) {
      aviso.erro(x instanceof Error ? x.message : "Não foi possível dar baixa");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <div className="flex flex-col gap-4"><Voltar href="/etiquetas/painel">Painel de validades</Voltar><Aviso tipo="erro">{erro}</Aviso></div>;
  if (!e) return <Carregando />;

  const linhas: [string, string][] = [
    [rotuloEvento(e.evento), dataHora(e.feito_em)],
    ["Conservação", rotuloConservacao(e.conservacao)],
    ["Onde", e.local ?? "—"],
    ["Quantidade", e.quantidade ? `${numero(e.quantidade)} ${e.um ?? ""}` : "—"],
    ["Lote", e.lote ?? "—"],
    ["Responsável", e.responsavel],
  ];
  if (e.validade_fabricante) linhas.push(["Validade do fabricante", e.validade_fabricante.split("-").reverse().join("/")]);
  if (e.id_producao) linhas.push(["Produção", `#${e.id_producao}`]);
  if (e.alergenos) linhas.push(["Alérgenos", e.alergenos]);
  if (e.observacao) linhas.push(["Observação", e.observacao]);

  return (
    <div className="mx-auto flex w-full max-w-[560px] flex-col gap-4">
      <Voltar href="/etiquetas/painel">Painel de validades</Voltar>
      <Cartao>
        <p className="rotulo">Etiqueta {e.codigo}</p>
        <h1 className="titulo mt-1 break-words">{e.produto}</h1>
        <div className="mt-3 flex items-end justify-between gap-3">
          <div>
            <span className="text-[12px] uppercase text-suave">Validade</span>
            <b className="mono block text-[26px] leading-none">{dataHora(e.vence_em)}</b>
          </div>
          <Selo cor={COR_SITUACAO[e.situacao]}>{ROTULO_SITUACAO[e.situacao]}</Selo>
        </div>
        <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[14px]">
          {linhas.map(([r, v]) => (
            <div key={r} className="contents"><dt className="text-suave">{r}</dt><dd>{v}</dd></div>
          ))}
        </dl>
        {e.status !== "ATIVA" && (
          <Aviso tipo="info">
            Baixada em {dataHora(e.baixada_em)}{e.baixada_por ? ` por ${e.baixada_por}` : ""}
            {e.motivo ? ` — ${e.motivo}` : ""}{e.id_movimento ? " · perda lançada no estoque" : ""}.
          </Aviso>
        )}
      </Cartao>

      {e.status === "ATIVA" && (
        <div className="grid gap-2 sm:grid-cols-2">
          <button className="btn btn-primario py-3" disabled={ocupado} onClick={() => void usarTudo()}>
            Usei tudo
          </button>
          {e.pode_descartar && (
            <button className="btn btn-perigo py-3" onClick={() => setDescartando(true)}>Descartar</button>
          )}
          <Link className="btn btn-secundario py-3 text-center" href={`/etiquetas?origem=${e.codigo}`}>
            {e.conservacao === "CONGELADO" ? "Descongelei" : "Nova etiqueta (reetiquetar)"}
          </Link>
          <button className="btn btn-secundario py-3" onClick={() => void imprimir([e.id], true).catch(
            (x) => aviso.erro(x instanceof Error ? x.message : "Falha ao imprimir"))}>
            Reimprimir
          </button>
        </div>
      )}

      {descartando && (
        <Descarte etiqueta={e} aoFechar={() => setDescartando(false)}
                  aoConcluir={(r) => { setDescartando(false); setE({ ...e, ...r }); }} />
      )}
    </div>
  );
}
