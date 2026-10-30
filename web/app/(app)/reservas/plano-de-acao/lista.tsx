"use client";

import { useEffect, useMemo, useState } from "react";

import { fatiar, Paginacao, usePaginacao } from "@/components/paginacao";
import { Cartao, Vazio } from "@/components/ui";
import { plural } from "@/lib/numeros";
import type { ListaDoPlano, PessoaDoPlano } from "@/lib/reservas";

/**
 * Uma das três listas do Plano de ação: a mensagem (editável) e as pessoas, cada uma com o
 * botão que abre o WhatsApp já com o texto.
 *
 * ⚠️ **O botão ABRE a conversa, não envia.** É o WhatsApp de quem está na tela (wa.me), com
 * o texto pronto para revisar: reativação é mensagem de marketing, e mandar em lote pela API
 * oficial exige modelo aprovado pela Meta e o consentimento — fica para quando o WhatsApp
 * da loja estiver no ar.
 * ⚠️ Quem respondeu "PARAR" ao WhatsApp da casa aparece, mas SEM o botão.
 */

const ORDENS: Record<ListaDoPlano, { v: string; r: string }[]> = {
  vips: [
    { v: "reservas", r: "Nº de reservas" },
    { v: "mais", r: "Sumiu há mais tempo" },
    { v: "menos", r: "Sumiu há menos tempo" },
  ],
  organizadores: [
    { v: "pessoas", r: "Por pessoas" },
    { v: "grupos", r: "Por grupos" },
    { v: "mais", r: "Sumiu há mais tempo" },
    { v: "menos", r: "Sumiu há menos tempo" },
  ],
  adormecidos: [
    { v: "menos", r: "Sumiu há menos tempo" },
    { v: "mais", r: "Sumiu há mais tempo" },
  ],
};

const ORDENAR: Record<string, (a: PessoaDoPlano, b: PessoaDoPlano) => number> = {
  reservas: (a, b) => b.reservas - a.reservas || b.dias - a.dias,
  pessoas: (a, b) => b.pessoas - a.pessoas || b.grupos - a.grupos,
  grupos: (a, b) => b.grupos - a.grupos || b.pessoas - a.pessoas,
  mais: (a, b) => b.dias - a.dias,
  menos: (a, b) => a.dias - b.dias,
};

/** "99999999999" → "(99) 99999-9999". */
const fone = (t: string) => {
  const m = t.match(/^(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : t;
};

const dataBr = (iso: string) => iso.slice(0, 10).split("-").reverse().join("/");

/** O primeiro nome, com só a inicial maiúscula ("MARIA SILVA" → "Maria"). */
const primeiroNome = (nome: string | null) => {
  const p = (nome ?? "").trim().split(/\s+/)[0] ?? "";
  return p ? p[0].toUpperCase() + p.slice(1).toLowerCase() : "";
};

export const montarMensagem = (modelo: string, nome: string | null, loja: string) =>
  modelo
    .replaceAll("{nome}", primeiroNome(nome) || "tudo bem")
    .replaceAll("{loja}", loja);

export default function ListaDoPlanoDeAcao({
  lista,
  titulo,
  descricao,
  pessoas,
  loja,
  modelo,
  setModelo,
}: {
  lista: ListaDoPlano;
  titulo: string;
  descricao: string;
  pessoas: PessoaDoPlano[];
  loja: string;
  modelo: string;
  setModelo: (v: string) => void;
}) {
  const [ordem, setOrdem] = useState(ORDENS[lista][0].v);
  const ordenadas = useMemo(
    () => [...pessoas].sort(ORDENAR[ordem] ?? ORDENAR.mais),
    [pessoas, ordem],
  );
  const pag = usePaginacao(`plano-${lista}`, { filtros: [lista, ordem] });
  const { setTotal } = pag;
  useEffect(() => {
    setTotal(ordenadas.length);
  }, [ordenadas.length, setTotal]);

  return (
    <Cartao titulo={`${titulo} · ${plural(pessoas.length, "pessoa", "pessoas")}`} descricao={descricao}>
      <div className="flex flex-col gap-4 px-5 py-4">
        {/* Recolhida: é escrita uma vez e lida a cada clique. Aberta, empurrava a lista
            para baixo da dobra no computador. */}
        <details>
          <summary className="cursor-pointer text-[14px]">
            <span className="rotulo-campo">Mensagem do convite</span>{" "}
            <span className="text-suave">· editar</span>
            <span className="mt-1 block truncate text-[13px] text-suave">{modelo}</span>
          </summary>
          <textarea
            aria-label="Mensagem do convite"
            className="campo mt-2 min-h-[88px]"
            value={modelo}
            onChange={(e) => setModelo(e.target.value)}
          />
          <span className="mt-1 block text-[12px] text-suave">
            {"{nome}"} vira o primeiro nome do cliente e {"{loja}"}, o nome da casa. O texto
            abre no WhatsApp para você revisar antes de enviar.
          </span>
        </details>
        <label className="block max-w-[240px]">
          <span className="rotulo-campo">Ordenar</span>
          <select className="campo mt-1.5" value={ordem} onChange={(e) => setOrdem(e.target.value)}>
            {ORDENS[lista].map((o) => (
              <option key={o.v} value={o.v}>{o.r}</option>
            ))}
          </select>
        </label>
      </div>

      {!ordenadas.length ? (
        <Vazio>Ninguém nesta lista com os critérios de agora.</Vazio>
      ) : (
        <>
          <ul className="divide-y divide-linha border-t border-linha">
            {fatiar(ordenadas, pag).map((p) => (
              <li key={p.telefone} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3">
                {/* No celular o nome ocupa a linha inteira; no computador, divide com os números. */}
                <div className="min-w-0 basis-full sm:basis-0 sm:flex-1">
                  <b className="block truncate">{p.nome || "Sem nome"}</b>
                  <span className="mono whitespace-nowrap text-[13px] text-suave">{fone(p.telefone)}</span>
                </div>
                <div className="min-w-0 flex-1 text-[13px] text-suave sm:flex-none">
                  {lista === "organizadores" ? (
                    <>
                      <span className="mono text-tinta">{p.grupos}</span>{" "}
                      {p.grupos === 1 ? "grupo" : "grupos"} ·{" "}
                      <span className="mono text-tinta">{p.pessoas}</span> pessoas · maior{" "}
                      <span className="mono text-tinta">{p.maior_grupo}</span>
                    </>
                  ) : (
                    <>
                      <span className="mono text-tinta">{p.reservas}</span>{" "}
                      {p.reservas === 1 ? "reserva" : "reservas"}
                    </>
                  )}
                  {p.faltas > 0 && <> · {plural(p.faltas, "falta", "faltas")}</>}
                  <span className="block">
                    última em <span className="mono">{dataBr(p.ultima)}</span> · há{" "}
                    <span className="mono text-tinta">{p.dias}</span> dias
                  </span>
                </div>
                {p.nao_quer_whatsapp ? (
                  <span className="text-[12px] text-suave" title="Respondeu PARAR ao WhatsApp da casa">
                    não quer receber
                  </span>
                ) : (
                  <a
                    className="btn btn-secundario px-3 py-1.5 text-[13px]"
                    href={`https://wa.me/55${p.telefone}?text=${encodeURIComponent(
                      montarMensagem(modelo, p.nome, loja),
                    )}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    WhatsApp
                  </a>
                )}
              </li>
            ))}
          </ul>
          <Paginacao p={pag} rotulo="pessoas" />
        </>
      )}
    </Cartao>
  );
}
