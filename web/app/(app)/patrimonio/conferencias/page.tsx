"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import ExplicaTela from "@/components/explica-tela";
import { Aviso, Campo, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import Voltar from "@/components/voltar";
import { api } from "@/lib/api";
import type { Setor } from "@/lib/cadastros";
import {
  abrirConferencia, conferencias, dataBr, marcarConferindo, type ConferenciaResumo,
} from "@/lib/patrimonio";
import { useSessao } from "@/lib/sessao";

/**
 * As conferências do patrimônio — etapa 3 (migração 140).
 *
 * 🔑 **Pedido do dono (28/10/2026):** *"pode seguir com a etapa 3 do patrimônio"*: abrir por
 * setor, ler as plaquetas, fechar com transferência ou baixa. A aberta fica no topo; abrir
 * leva direto à tela de leitura e marca ESTE aparelho como o que está conferindo.
 */
export default function PaginaConferencias() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const router = useRouter();
  const podeConferir = pode("patrimonio.conferir");
  const [lista, setLista] = useState<ConferenciaResumo[] | null>(null);
  const [setores, setSetores] = useState<Setor[]>([]);
  const [setor, setSetor] = useState("");
  const [obs, setObs] = useState("");
  const [erro, setErro] = useState("");
  const [abrindo, setAbrindo] = useState(false);

  useEffect(() => {
    conferencias().then(setLista).catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
    api.get<Setor[]>("/setores").then(setSetores).catch(() => {});
  }, []);

  async function abrir() {
    setAbrindo(true);
    try {
      const c = await abrirConferencia(setor ? Number(setor) : null, obs.trim() || null);
      marcarConferindo(c.id);
      aviso.sucesso(c.message);
      router.push(`/patrimonio/conferencias/${c.id}`);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível abrir");
    } finally {
      setAbrindo(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Voltar href="/patrimonio">patrimônio</Voltar>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Conferência do patrimônio</h1>
        <ExplicaTela>
          Ande pelo setor com o celular e leia a plaqueta de cada equipamento. No fim, o que foi
          visto fica <strong>conferido</strong>; o que estava aqui mas o sistema punha em outro
          setor é <strong>transferido</strong>; e o que não apareceu, você escolhe: manter (está
          no conserto, emprestado) ou <strong>dar baixa</strong>. Não mexe no estoque.
        </ExplicaTela>
      </header>

      {podeConferir && (
        <Cartao titulo="Abrir uma conferência"
                descricao="A lista do que procurar é a dos bens do setor AGORA, fora os baixados.">
          <div className="grid gap-3 sm:grid-cols-[minmax(0,260px)_minmax(0,1fr)_auto] sm:items-end">
            <Campo rotulo="O que conferir">
              <select className="campo" id="conferencia-setor" value={setor}
                      onChange={(e) => setSetor(e.target.value)}>
                <option value="">A loja inteira</option>
                {setores.filter((s) => s.ativo).map((s) =>
                  <option key={s.id} value={s.id}>{s.nome}</option>)}
              </select>
            </Campo>
            <Campo rotulo="Observação" opcional>
              <input className="campo" id="conferencia-obs" maxLength={300} value={obs}
                     onChange={(e) => setObs(e.target.value)} placeholder="conferência anual, troca de gerente…" />
            </Campo>
            <button type="button" className="btn btn-primario" id="conferencia-abrir"
                    disabled={abrindo} aria-busy={abrindo} onClick={() => void abrir()}>
              Abrir e começar a ler
            </button>
          </div>
        </Cartao>
      )}

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      <Cartao titulo="Conferências">
        {!lista ? <Carregando /> : !lista.length ? (
          <Vazio>Nenhuma conferência ainda.</Vazio>
        ) : (
          <div className="grid-rolante">
            <table className="tabela" id="conferencias">
              <thead>
                <tr><th>Nº</th><th>O que</th><th>Situação</th><th>Aberta</th>
                  <th className="num">Esperados</th><th className="num">Lidos</th>
                  <th className="num">Faltam</th><th className="num">De outro setor</th></tr>
              </thead>
              <tbody>
                {lista.map((c) => (
                  <tr key={c.id}>
                    <td className="mono">
                      <Link href={`/patrimonio/conferencias/${c.id}`} className="link-registro font-semibold">
                        {c.id}
                      </Link>
                    </td>
                    <td>{c.escopo}</td>
                    <td>
                      <Etiqueta cor={c.status === "ABERTA" ? "alerta" : c.status === "FECHADA" ? "erva" : "neutro"}>
                        {c.status_txt}
                      </Etiqueta>
                    </td>
                    <td>
                      {dataBr(c.aberta_em)}
                      {c.aberta_por_nome && <span className="block text-[12px] text-suave">{c.aberta_por_nome}</span>}
                    </td>
                    <td className="num">{c.esperados}</td>
                    <td className="num">{c.lidos}</td>
                    <td className="num">{c.faltam}</td>
                    <td className="num">{c.de_fora}</td>
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
