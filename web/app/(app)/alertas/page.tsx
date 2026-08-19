"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

type Alerta = {
  chave: string;
  severidade: "critico" | "atencao" | "aviso";
  titulo: string;
  quantidade: number;
  detalhe: string;
  acao: string;
  href: string;
  valor: number | null;
};

type Vencimento = {
  id: number;
  validade: string;
  dias_restantes: number;
  produto: string;
  codigo: string;
  lote: string | null;
  local: string;
  quantidade: number;
  um_estoque: string | null;
  valor: number;
};

type Minimo = {
  id: number;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  estoque_minimo: number;
  saldo: number;
  faltam: number;
  fornecedor: string | null;
};

const CORES = { critico: "erro", atencao: "alerta", aviso: "suave" } as const;
const ROTULOS = { critico: "agir hoje", atencao: "atenção", aviso: "quando puder" } as const;

export default function PaginaAlertas() {
  const [alertas, setAlertas] = useState<Alerta[] | null>(null);
  const [vencimentos, setVencimentos] = useState<Vencimento[]>([]);
  const [minimos, setMinimos] = useState<Minimo[]>([]);
  const [erro, setErro] = useState("");
  const [baixando, setBaixando] = useState("");

  const carregar = useCallback(async () => {
    try {
      const [a, v, m] = await Promise.all([
        api.get<Alerta[]>("/alertas"),
        api.get<Vencimento[]>("/alertas/vencimentos").catch(() => []),
        api.get<Minimo[]>("/alertas/abaixo-do-minimo").catch(() => []),
      ]);
      setAlertas(a);
      setVencimentos(v);
      setMinimos(m);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function baixar(caminho: string, chave: string) {
    setBaixando(chave);
    setErro("");
    try {
      await api.baixar(caminho);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível baixar");
    } finally {
      setBaixando("");
    }
  }

  const criticos = alertas?.filter((a) => a.severidade === "critico").length ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Operação</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
          O que precisa de atenção
        </h1>
        <p className="mt-1 max-w-[64ch] text-suave">
          O sistema sabe o que está para acabar, o que vence esta semana e o que ficou parado
          esperando alguém. Esta tela junta tudo — para você não descobrir no fim do mês.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {!alertas ? (
        <Carregando />
      ) : !alertas.length ? (
        <Cartao>
          <Vazio>
            Nada pendente. O estoque está acima do mínimo, sem lote vencendo e sem nota
            parada.
          </Vazio>
        </Cartao>
      ) : (
        <Cartao
          titulo={`${alertas.length} ponto(s) de atenção`}
          descricao={
            criticos
              ? `${criticos} pede ação hoje — está no topo da lista.`
              : "Nada crítico no momento."
          }
        >
          <ul className="flex flex-col gap-px bg-linha">
            {alertas.map((a) => (
              <li key={a.chave} className="flex flex-wrap items-start gap-3 bg-superficie py-3.5">
                <span
                  className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${
                    a.severidade === "critico"
                      ? "bg-erro"
                      : a.severidade === "atencao"
                        ? "bg-alerta"
                        : "bg-linha2"
                  }`}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{a.titulo}</span>
                    <span className="mono text-[13px] text-suave">{a.quantidade}</span>
                    {a.valor ? (
                      <span className="mono text-[13px] text-suave">· {reais(a.valor)}</span>
                    ) : null}
                    <Etiqueta cor={a.severidade === "aviso" ? "neutro" : "alerta"}>
                      {ROTULOS[a.severidade]}
                    </Etiqueta>
                  </p>
                  <p className="mt-0.5 text-[13.5px] leading-snug text-suave">{a.detalhe}</p>
                </div>
                <Link href={a.href} className="rotulo whitespace-nowrap text-erva hover:underline">
                  {a.acao} ›
                </Link>
              </li>
            ))}
          </ul>
        </Cartao>
      )}

      <Cartao
        titulo="Vencendo"
        descricao="Lotes com validade dentro da janela configurada nos parâmetros da loja."
        acao={
          vencimentos.length ? (
            <button
              className="btn btn-secundario"
              onClick={() => baixar("/exportar/vencimentos.csv", "venc")}
              disabled={baixando === "venc"}
            >
              {baixando === "venc" ? "Baixando…" : "Baixar planilha"}
            </button>
          ) : undefined
        }
      >
        {!vencimentos.length ? (
          <Vazio>Nenhum lote com validade próxima.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Validade</th>
                  <th>Produto</th>
                  <th>Lote</th>
                  <th>Local</th>
                  <th className="num">Quantidade</th>
                  <th className="num">Valor</th>
                </tr>
              </thead>
              <tbody>
                {vencimentos.map((v) => (
                  <tr key={v.id}>
                    <td className="mono whitespace-nowrap">
                      {new Date(v.validade + "T12:00:00").toLocaleDateString("pt-BR")}
                      <span
                        className={`ml-2 ${v.dias_restantes < 0 ? "text-erro" : "text-suave"}`}
                      >
                        {v.dias_restantes < 0
                          ? `venceu há ${-v.dias_restantes}d`
                          : `em ${v.dias_restantes}d`}
                      </span>
                    </td>
                    <td>
                      <span className="font-semibold">{v.produto}</span>
                      <span className="mono ml-2 text-[12px] text-suave">{v.codigo}</span>
                    </td>
                    <td className="mono text-[13px]">{v.lote ?? "—"}</td>
                    <td className="text-suave">{v.local}</td>
                    <td className="num">
                      {Number(v.quantidade)} {v.um_estoque ?? ""}
                    </td>
                    <td className="num">{reais(Number(v.valor))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>

      <Cartao
        titulo="Abaixo do mínimo"
        descricao="O que vai faltar antes da próxima entrega — a base da lista de compras."
        acao={
          minimos.length ? (
            <button
              className="btn btn-secundario"
              onClick={() => baixar("/exportar/saldos.csv", "saldos")}
              disabled={baixando === "saldos"}
            >
              {baixando === "saldos" ? "Baixando…" : "Baixar estoque"}
            </button>
          ) : undefined
        }
      >
        {!minimos.length ? (
          <Vazio>Nada abaixo do mínimo.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Produto</th>
                  <th className="num">Saldo</th>
                  <th className="num">Mínimo</th>
                  <th className="num">Faltam</th>
                  <th>Fornecedor</th>
                </tr>
              </thead>
              <tbody>
                {minimos.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <span className="font-semibold">{m.produto}</span>
                      <span className="mono ml-2 text-[12px] text-suave">{m.codigo}</span>
                    </td>
                    <td className={`num ${Number(m.saldo) <= 0 ? "text-erro" : ""}`}>
                      {Number(m.saldo)} {m.um_estoque ?? ""}
                    </td>
                    <td className="num text-suave">{Number(m.estoque_minimo)}</td>
                    <td className="num font-semibold">{Number(m.faltam)}</td>
                    <td className="text-suave">{m.fornecedor ?? "—"}</td>
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
