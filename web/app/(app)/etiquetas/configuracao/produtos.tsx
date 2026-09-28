"use client";

import { useCallback, useEffect, useState } from "react";

import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Carregando, Cartao, Vazio } from "@/components/ui";
import {
  produtosComValidade, rotuloConservacao, rotuloEvento, type ProdutoComValidade,
} from "@/lib/etiquetas";

/** Os produtos que já têm validade cadastrada — clicar abre para editar. */
export default function ProdutosComValidade({
  versao, aoEscolher,
}: {
  versao: number;
  aoEscolher: (p: { id: number; rotulo: string }) => void;
}) {
  const [busca, setBusca] = useState("");
  const [lista, setLista] = useState<ProdutoComValidade[] | null>(null);
  const [erro, setErro] = useState("");
  // ⚠️ `prefixoUrl`: a tela tem mais de uma lista, e o endereço é dividido.
  const pag = usePaginacao("etiquetas-validades", { filtros: [busca], prefixoUrl: "val" });

  const carregar = useCallback(async () => {
    if (!pag.pronto) return;
    try {
      const r = await produtosComValidade(pag.parametros, busca);
      setLista(r.itens);
      pag.setTotal(r.total);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.pronto, busca, pag.offset, pag.porPagina, versao]);

  useEffect(() => {
    const t = setTimeout(() => void carregar(), busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

  return (
    <Cartao titulo="Produtos com validade cadastrada"
            acao={<input className="campo w-[220px] text-[13px]" placeholder="buscar" value={busca}
                         onChange={(e) => setBusca(e.target.value)} />}>
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!lista ? <Carregando /> : !lista.length ? (
        <Vazio>Nenhum produto com validade ainda. Escolha um acima e cadastre as regras.</Vazio>
      ) : (
        <div className="grid-rolante">
          <table className="tabela">
            <thead><tr><th>Produto</th><th>Regras</th></tr></thead>
            <tbody>
              {lista.map((p) => (
                <tr key={p.id}>
                  <td>
                    <button className="link-acao text-left" onClick={() => aoEscolher({ id: p.id, rotulo: p.nome })}>
                      {p.nome}
                    </button>
                    <span className="mono block text-[12px] text-suave">{p.codigo}</span>
                  </td>
                  <td className="text-[13px]">
                    {p.regras.map((r) => (
                      <span key={`${r.evento}${r.conservacao}`} className="mr-3 inline-block">
                        {rotuloEvento(r.evento)} · {rotuloConservacao(r.conservacao)}: <b>{r.prazo}{" "}
                        {r.unidade === "HORAS" ? "h" : "d"}</b>{r.padrao ? " ★" : ""}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Paginacao p={pag} rotulo="produto(s)" />
    </Cartao>
  );
}
