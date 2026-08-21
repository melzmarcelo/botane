"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Local, reais } from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import BuscaCadastro from "@/components/busca-cadastro";
import { fonteDaLista, ItemBusca } from "@/lib/busca-cadastro";

type Ficha = {
  id: number;
  id_produto: number;
  produto: string;
  versao: number;
  status: string;
  rendimento_qtd: number;
  rendimento_um: string | null;
};

type Producao = {
  id: number;
  data: string;
  produto: string;
  codigo: string;
  local: string;
  quantidade: number;
  custo_total: number;
  custo_unitario: number;
  versao_ficha: number;
  usuario: string | null;
};

type Resultado = {
  id: number;
  quantidade: number;
  custo_total: number;
  custo_unitario: number;
  versao_ficha: number;
  consumos: { nome: string; quantidade: number; custo: number }[];
};

export default function PaginaProducao() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeProduzir = pode("estoque.saidas");
  const veCusto = pode("fichas.custos");

  const [fichas, setFichas] = useState<Ficha[]>([]);
  const [locais, setLocais] = useState<Local[]>([]);
  const [historico, setHistorico] = useState<Producao[] | null>(null);
  const [f, setF] = useState({ id_produto: "", quantidade: "", id_local: "", observacao: "" });
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const [fs, ls, h] = await Promise.all([
        api.get<Ficha[]>("/fichas?status=HOMOLOGADA"),
        api.get<Local[]>("/locais"),
        api.get<Producao[]>("/estoque/producoes"),
      ]);
      setFichas(fs);
      setLocais(ls);
      setHistorico(h);
      setF((atual) => ({
        ...atual,
        id_local: atual.id_local || String(ls.find((l) => l.principal)?.id ?? ls[0]?.id ?? ""),
      }));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // As receitas já estão carregadas e são poucas por natureza: a janela é a
  // mesma da busca de produto, só que servida da lista da própria tela.
  const fonteReceitas = useMemo(
    () =>
      fonteDaLista(
        "Buscar receita",
        "receita",
        fichas.map((x) => ({
          id: x.id_produto,
          codigo: null,
          nome: x.produto,
          detalhe: `ficha v${x.versao}`,
        })),
        "nome do prato",
      ),
    [fichas],
  );

  const escolhida = fichas.find((x) => String(x.id_produto) === f.id_produto);

  async function produzir(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro("");
    setResultado(null);
    try {
      const r = await api.post<Resultado>("/estoque/producoes", {
        id_produto: Number(f.id_produto),
        quantidade: Number(f.quantidade.replace(",", ".")),
        id_local: f.id_local ? Number(f.id_local) : null,
        observacao: f.observacao || null,
      });
      setResultado(r);
      setF({ ...f, quantidade: "", observacao: "" });
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível produzir");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Estoque</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Produção</h1>
        <p className="mt-1 max-w-[66ch] text-suave">
          Produzir baixa os ingredientes da ficha homologada e devolve o produto pronto ao
          estoque. O custo é o que <b>realmente saiu</b> hoje — se o insumo subiu, o prato
          produzido hoje custa mais.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {resultado && (
        <Cartao
          titulo="Produção registrada"
          descricao={`Ficha v${resultado.versao_ficha} · ${resultado.quantidade} produzido(s)`}
        >
          <div className="grid gap-4 sm:grid-cols-3">
            {veCusto && (
              <>
                <div>
                  <p className="rotulo">Custo consumido</p>
                  <p className="mono mt-1 text-[19px]">{reais(Number(resultado.custo_total))}</p>
                </div>
                <div>
                  <p className="rotulo">Custo por unidade</p>
                  <p className="mono mt-1 text-[19px] font-bold text-erva">
                    {reais(Number(resultado.custo_unitario))}
                  </p>
                </div>
              </>
            )}
            <div className="sm:col-span-3">
              <p className="rotulo mb-1.5">Saiu do estoque</p>
              <ul className="flex flex-col gap-1 text-[14px]">
                {resultado.consumos.map((c, i) => (
                  <li key={i} className="flex justify-between gap-4 border-b border-linha py-1">
                    <span>{c.nome}</span>
                    <span className="mono">
                      {Number(c.quantidade).toLocaleString("pt-BR", {
                        maximumFractionDigits: 3,
                      })}
                      {veCusto && ` · ${reais(Number(c.custo))}`}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Cartao>
      )}

      {podeProduzir && (
        <Cartao titulo="Registrar produção">
          {!fichas.length ? (
            <p className="text-[14.5px] text-suave">
              Nenhuma ficha homologada ainda.{" "}
              <Link href="/fichas" className="text-erva underline">
                ir para fichas técnicas
              </Link>{" "}
              — só ficha homologada pode ser produzida.
            </p>
          ) : (
            <form onSubmit={produzir} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Campo rotulo="O que foi produzido" className="sm:col-span-2">
                <BuscaCadastro
                  fonte={fonteReceitas}
                  required
                  selecionado={
                    f.id_produto
                      ? { id: Number(f.id_produto), rotulo: escolhida?.produto ?? "" }
                      : null
                  }
                  aoEscolher={(item: ItemBusca | null) =>
                    setF({ ...f, id_produto: item ? String(item.id) : "" })
                  }
                />
                {escolhida && (
                  <span className="mt-1 block text-[12.5px] text-suave">
                    A receita rende {Number(escolhida.rendimento_qtd)}{" "}
                    {escolhida.rendimento_um ?? "un"} — quantidade diferente é proporcional.
                  </span>
                )}
              </Campo>
              <Campo rotulo="Quantidade produzida">
                <input
                  className="campo mono"
                  type="number"
                  step="0.001"
                  min="0.001"
                  required
                  value={f.quantidade}
                  onChange={(e) => setF({ ...f, quantidade: e.target.value })}
                />
              </Campo>
              <Campo rotulo="Local">
                <select
                  className="campo"
                  value={f.id_local}
                  onChange={(e) => setF({ ...f, id_local: e.target.value })}
                >
                  {locais.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.nome}
                    </option>
                  ))}
                </select>
              </Campo>
              <Campo rotulo="Observação" className="sm:col-span-3">
                <input
                  className="campo"
                  value={f.observacao}
                  onChange={(e) => setF({ ...f, observacao: e.target.value })}
                />
              </Campo>
              <div className="flex items-end">
                <button className="btn btn-primario" type="submit" disabled={salvando}>
                  {salvando ? "Produzindo…" : "Produzir"}
                </button>
              </div>
            </form>
          )}
        </Cartao>
      )}

      <Cartao titulo="Produções recentes">
        {!historico ? (
          <Carregando />
        ) : !historico.length ? (
          <Vazio>Nenhuma produção registrada ainda.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Quando</th>
                  <th>Produto</th>
                  <th>Local</th>
                  <th className="num">Qtd</th>
                  {veCusto && <th className="num">Custo total</th>}
                  {veCusto && <th className="num">Por unidade</th>}
                  <th>Ficha</th>
                </tr>
              </thead>
              <tbody>
                {historico.map((h) => (
                  <tr key={h.id}>
                    <td className="mono whitespace-nowrap text-[13px]">
                      {new Date(h.data).toLocaleString("pt-BR", {
                        day: "2-digit",
                        month: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="font-semibold">{h.produto}</td>
                    <td className="text-suave">{h.local}</td>
                    <td className="num">
                      {Number(h.quantidade).toLocaleString("pt-BR", {
                        maximumFractionDigits: 3,
                      })}
                    </td>
                    {veCusto && <td className="num">{reais(Number(h.custo_total))}</td>}
                    {veCusto && (
                      <td className="num font-semibold">{reais(Number(h.custo_unitario))}</td>
                    )}
                    <td>
                      <Etiqueta>v{h.versao_ficha}</Etiqueta>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>
    </div>
  );
}
