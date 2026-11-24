"use client";

import { useEffect, useState } from "react";

import { Aviso, Carregando, Etiqueta, Modal, Vazio } from "@/components/ui";
import { qtd, textoParaNumero } from "@/lib/numeros";
import {
  pedirLote,
  qtdParaCampo,
  Sugestao,
  sugestoesOrdem,
  Urgencia,
  URGENCIAS,
} from "@/lib/ordens-compra";

/**
 * Etapa 2: o que está abaixo do mínimo, para pôr na lista sem ninguém precisar lembrar.
 *
 * 🔑 **Vem marcado o que falta**, na unidade de pedir e arredondado para cima pela embalagem.
 * O que já está na lista e cobre a falta vem desmarcado, com o selo "já na lista".
 * ⚠️ Só produtos comprados: o que a casa produz se repõe pela agenda de produção.
 */

type Linha = { marcado: boolean; quantidade: string; um: string };

/** Quantas embalagens cobrem a falta, nesta unidade. */
function emEmbalagens(s: Sugestao, um: string): string {
  const fator = Number(s.unidades.find((u) => u.um === um)?.fator ?? s.fator) || 1;
  const n = Math.ceil(Number(s.faltam) / fator - 1e-9);
  return n > 0 ? String(n) : "";
}

export default function JanelaSugestoes({
  aoFechar,
  aoPor,
}: {
  aoFechar: () => void;
  aoPor: (mensagem: string) => void;
}) {
  const [lista, setLista] = useState<Sugestao[] | null>(null);
  const [linhas, setLinhas] = useState<Record<number, Linha>>({});
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  // Uma urgência para o lote todo: abaixo do mínimo ainda não é falta, então "Esta semana".
  const [urgencia, setUrgencia] = useState<Urgencia>("SEMANA");

  useEffect(() => {
    sugestoesOrdem()
      .then((l) => {
        setLista(l);
        setLinhas(Object.fromEntries(l.map((s) => [s.id_produto, {
          marcado: Number(s.sugerida) > 0,
          quantidade: Number(s.sugerida) > 0 ? qtdParaCampo(s.sugerida) : "",
          um: s.um,
        }])));
      })
      .catch((e) => {
        setLista([]);
        setErro(e instanceof Error ? e.message : "Falha ao calcular as sugestões");
      });
  }, []);

  const mudar = (id: number, parte: Partial<Linha>) =>
    setLinhas((m) => ({ ...m, [id]: { ...m[id], ...parte } }));
  const marcadas = (lista ?? []).filter((s) => linhas[s.id_produto]?.marcado);
  const todas = !!lista?.length && marcadas.length === lista.length;

  async function por() {
    const itens = marcadas.map((s) => ({
      id_produto: s.id_produto,
      quantidade: textoParaNumero(linhas[s.id_produto].quantidade) ?? 0,
      um: linhas[s.id_produto].um,
      urgencia,
    }));
    const ruim = itens.findIndex((i) => i.quantidade <= 0);
    if (ruim >= 0) return setErro(`Informe a quantidade de ${marcadas[ruim].nome}.`);
    setOcupado(true);
    setErro("");
    try {
      const r = await pedirLote(itens);
      aoPor(r.message);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível pôr na lista");
      setOcupado(false);
    }
  }

  return (
    <Modal titulo="Abaixo do estoque mínimo" aoFechar={aoFechar} largura="720px"
           rodape={
             <div className="flex flex-wrap items-center justify-end gap-2">
               {!!lista?.length && (
                 <button type="button" className="link-acao mr-auto text-[13px]" id="ordem-sugestoes-todas"
                         onClick={() => setLinhas((m) => Object.fromEntries(Object.entries(m).map(
                           ([k, v]) => [k, { ...v, marcado: !todas }])))}>
                   {todas ? "desmarcar todas" : "marcar todas"}
                 </button>
               )}
               {!!lista?.length && (
                 <select className="campo w-auto" id="ordem-sugestoes-urgencia" aria-label="Para quando"
                         value={urgencia} onChange={(e) => setUrgencia(e.target.value as Urgencia)}>
                   {URGENCIAS.map((u) => <option key={u.valor} value={u.valor}>{u.rotulo}</option>)}
                 </select>
               )}
               <button type="button" className="btn" onClick={aoFechar}>Fechar</button>
               <button type="button" className="btn btn-primario" id="ordem-por-na-lista"
                       disabled={ocupado || !marcadas.length} onClick={() => void por()}>
                 {ocupado ? "Pondo…" : `Pôr ${marcadas.length} na lista`}
               </button>
             </div>
           }>
      <div className="flex flex-col gap-3" id="ordem-sugestoes">
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <p className="text-[13px] text-suave">
          Produtos comprados com saldo abaixo do mínimo nesta loja. A quantidade repõe até o
          máximo do cadastro (ou até o mínimo, sem máximo), já descontado o que está na lista.
        </p>
        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>Nenhum produto comprado está abaixo do mínimo.</Vazio>
        ) : (
          <ul className="flex flex-col divide-y divide-[var(--borda)]">
            {lista.map((s) => {
              const l = linhas[s.id_produto];
              if (!l) return null;
              const coberto = Number(s.sugerida) <= 0;
              return (
                <li key={s.id_produto} data-sugestao={s.id_produto}
                    className="flex flex-wrap items-center gap-x-3 gap-y-2 py-2.5">
                  <input type="checkbox" className="h-5 w-5" data-marcar
                         aria-label={`pôr ${s.nome} na lista`} checked={l.marcado}
                         onChange={(e) => mudar(s.id_produto, { marcado: e.target.checked })} />
                  <div className="min-w-[12rem] flex-1">
                    <p className="font-semibold">
                      {s.nome}
                      {s.codigo && <span className="mono ml-2 font-normal text-suave">{s.codigo}</span>}
                      {coberto && <span className="ml-2"><Etiqueta>já na lista</Etiqueta></span>}
                    </p>
                    <p className="text-[12.5px] text-suave">
                      tem {qtd(s.saldo)} {s.um_estoque} · mínimo {qtd(s.estoque_minimo)}
                      {s.ate_o_maximo && <> · repor até {qtd(s.repor_ate)}</>}
                      {!!s.na_lista.length && <> · na lista: {s.na_lista.map(
                        (a) => `${qtd(a.quantidade)} ${a.um}`).join(", ")}</>}
                      {s.fornecedor && <> · {s.fornecedor}</>}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <input className="campo w-20 text-right" inputMode="decimal" data-sugestao-qtd
                           aria-label={`quantidade de ${s.nome}`} value={l.quantidade}
                           onFocus={(e) => e.target.select()}
                           onChange={(e) => mudar(s.id_produto, {
                             quantidade: e.target.value, marcado: !!e.target.value.trim() })} />
                    <select className="campo w-20" aria-label={`unidade de ${s.nome}`} value={l.um}
                            onChange={(e) => mudar(s.id_produto, {
                              um: e.target.value, quantidade: emEmbalagens(s, e.target.value) || l.quantidade })}>
                      {s.unidades.map((u) => <option key={u.um} value={u.um}>{u.um}</option>)}
                    </select>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Modal>
  );
}
