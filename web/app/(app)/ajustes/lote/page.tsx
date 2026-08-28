"use client";

/**
 * Ajuste de estoque em LOTE — vários produtos num lançamento só.
 *
 * Quem confere a despensa acha cinco diferenças de uma vez. Lançar uma a uma
 * obriga a sair e voltar na tela cinco vezes — e, pior, as cinco viram cinco
 * lançamentos sem relação nenhuma entre si: quem olhar o razão depois não sabe
 * que vieram da mesma conferência.
 *
 * ⚠️ **Tudo ou nada.** A linha que falha derruba o lote inteiro, e a mensagem
 * diz qual linha. Gravar as que deram certo deixaria a pessoa sem saber o que
 * já entrou — e tentar de novo duplicaria o que passou.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { Aviso, Campo, Cartao } from "@/components/ui";
import { api, ErroApi } from "@/lib/api";
import { fonteProdutos } from "@/lib/busca-cadastro";
import { Local } from "@/lib/cadastros";
import { useSessao } from "@/lib/sessao";

type Motivo = { id: number; nome: string };

const TIPOS = [
  { id: "ENTRADA_MANUAL", nome: "Entrada", chave: "estoque.entradas" },
  { id: "SAIDA_CONSUMO_INTERNO", nome: "Consumo interno", chave: "estoque.saidas" },
  { id: "SAIDA_PERDA", nome: "Perda", chave: "estoque.perdas" },
  { id: "ENTRADA_DEVOLUCAO", nome: "Devolução", chave: "estoque.entradas" },
];

type Linha = {
  chave: number;
  produto: { id: number; rotulo: string } | null;
  tipo: string;
  quantidade: string;
  custo_unitario: string;
  id_motivo_perda: number | "";
};

let sequencia = 1;
const nova = (tipo: string): Linha => ({
  chave: sequencia++,
  produto: null,
  tipo,
  quantidade: "",
  custo_unitario: "",
  id_motivo_perda: "",
});

export default function PaginaAjusteLote() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const permitidos = TIPOS.filter((t) => pode(t.chave));
  const padrao = permitidos[0]?.id ?? "ENTRADA_MANUAL";

  const [locais, setLocais] = useState<Local[]>([]);
  const [idLocal, setIdLocal] = useState<number | "">("");
  const [motivos, setMotivos] = useState<Motivo[]>([]);
  const [linhas, setLinhas] = useState<Linha[]>([nova(padrao)]);
  const [observacao, setObservacao] = useState("");
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get<Local[]>("/locais"),
      api.get<Motivo[]>("/estoque/motivos-perda").catch(() => [] as Motivo[]),
    ])
      .then(([ls, ms]) => {
        setLocais(ls);
        setMotivos(ms);
        const principal = ls.find((x) => x.principal) ?? ls[0];
        if (principal) setIdLocal(principal.id);
      })
      .catch(() => setErro("Falha ao carregar os locais de estoque."));
  }, []);

  const trocar = (i: number, campo: keyof Linha, valor: unknown) =>
    setLinhas((ls) => ls.map((x, j) => (j === i ? { ...x, [campo]: valor } : x)));

  const preenchidas = linhas.filter((l) => l.produto && l.quantidade.trim() !== "");

  async function lancar() {
    if (!preenchidas.length) {
      setErro("Escolha ao menos um produto e informe a quantidade.");
      return;
    }
    setOcupado(true);
    setErro("");
    try {
      const r = await api.post<{ lancados: number }>("/ajustes/estoque", {
        observacao: observacao.trim() || null,
        linhas: preenchidas.map((l) => ({
          id_produto: l.produto!.id,
          tipo: l.tipo,
          quantidade: Number(l.quantidade.replace(",", ".")),
          id_local: idLocal || null,
          custo_unitario: l.custo_unitario.trim()
            ? Number(l.custo_unitario.replace(",", "."))
            : null,
          id_motivo_perda: l.id_motivo_perda || null,
        })),
      });
      aviso.sucesso(`${r.lancados} ajuste(s) lançado(s).`);
      // Fica aberto e limpo: quem confere uma prateleira confere a próxima.
      setLinhas([nova(padrao)]);
      setObservacao("");
    } catch (e) {
      // ⚠️ Erro de AÇÃO vai para o aviso flutuante — o botão está no fim de um
      // formulário longo, e mensagem no topo não é vista por quem clicou.
      aviso.erro(e instanceof ErroApi ? e.message : "Não foi possível lançar o lote.");
    } finally {
      setOcupado(false);
    }
  }

  if (!permitidos.length) {
    return (
      <Cartao>
        <Aviso tipo="erro">Você não tem permissão para lançar ajustes de estoque.</Aviso>
      </Cartao>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <Link href="/ajustes" className="link-voltar">
          ← Ajustes
        </Link>
        <h1 className="titulo mt-2">Ajuste em lote</h1>
        <p className="text-neutro-500 text-[14px] mt-1 max-w-[70ch]">
          Vários produtos num lançamento só, com uma observação que explica o conjunto. As
          linhas podem misturar entrada, consumo e perda. <b>Ou tudo entra, ou nada entra.</b>
        </p>
      </div>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao>
        <div className="grid gap-4 sm:grid-cols-[220px_minmax(0,1fr)]">
          <Campo rotulo="Local de estoque">
            <select
              className="campo mt-1.5"
              value={idLocal}
              onChange={(e) => setIdLocal(Number(e.target.value) || "")}
            >
              {locais.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.nome}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Por que este lote">
            <input
              className="campo mt-1.5"
              placeholder="ex.: conferência da câmara fria"
              value={observacao}
              onChange={(e) => setObservacao(e.target.value)}
            />
          </Campo>
        </div>

        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-[14px]">
            <thead>
              <tr>
                <th className="rotulo text-left pb-2 min-w-[260px]">Produto</th>
                <th className="rotulo text-left pb-2 w-[160px] min-w-[160px]">O que houve</th>
                <th className="rotulo text-left pb-2 w-[110px] min-w-[110px]">Quantidade</th>
                <th className="rotulo text-left pb-2 w-[120px] min-w-[120px]">Custo un.</th>
                <th className="rotulo text-left pb-2 w-[150px] min-w-[150px]">Motivo</th>
                <th className="pb-2 w-[40px]"></th>
              </tr>
            </thead>
            <tbody>
              {linhas.map((l, i) => (
                <tr key={l.chave} className="border-t border-linha align-top">
                  <td className="py-2 pr-3">
                    <BuscaCadastro
                      fonte={fonteProdutos((p) => p.controla_estoque)}
                      selecionado={l.produto}
                      aoEscolher={(item) =>
                        trocar(i, "produto", item ? { id: item.id, rotulo: rotuloDe(item) } : null)
                      }
                    />
                  </td>
                  <td className="py-2 pr-3">
                    <select
                      className="campo"
                      value={l.tipo}
                      onChange={(e) => trocar(i, "tipo", e.target.value)}
                    >
                      {permitidos.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.nome}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="py-2 pr-3">
                    <input
                      className="campo"
                      inputMode="decimal"
                      value={l.quantidade}
                      onChange={(e) => trocar(i, "quantidade", e.target.value)}
                    />
                  </td>
                  <td className="py-2 pr-3">
                    {/* Custo só faz sentido na entrada: a saída sai pelo médio. */}
                    <input
                      className="campo"
                      inputMode="decimal"
                      placeholder={l.tipo.startsWith("ENTRADA") ? "0,00" : "pelo médio"}
                      disabled={!l.tipo.startsWith("ENTRADA")}
                      value={l.custo_unitario}
                      onChange={(e) => trocar(i, "custo_unitario", e.target.value)}
                    />
                  </td>
                  <td className="py-2 pr-3">
                    <select
                      className="campo"
                      disabled={l.tipo !== "SAIDA_PERDA"}
                      value={l.id_motivo_perda}
                      onChange={(e) =>
                        trocar(i, "id_motivo_perda", Number(e.target.value) || "")
                      }
                    >
                      <option value="">—</option>
                      {motivos.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.nome}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="py-2">
                    {linhas.length > 1 && (
                      <button
                        className="btn btn-texto"
                        title="Tirar esta linha"
                        onClick={() => setLinhas((ls) => ls.filter((_, j) => j !== i))}
                      >
                        ×
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap gap-2 mt-4">
          <button
            className="btn btn-secundario"
            onClick={() => setLinhas((ls) => [...ls, nova(padrao)])}
          >
            + Outra linha
          </button>
          <button
            className="btn btn-primario"
            onClick={lancar}
            disabled={ocupado || !preenchidas.length}
          >
            {ocupado ? "Lançando…" : `Lançar ${preenchidas.length || ""} ajuste(s)`}
          </button>
        </div>
      </Cartao>
    </div>
  );
}
