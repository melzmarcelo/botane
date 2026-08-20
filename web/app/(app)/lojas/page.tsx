"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Aviso, Campo, Carregando, Cartao, Etiqueta } from "@/components/ui";

type Loja = {
  id: number;
  nome: string;
  apelido: string | null;
  cnpj: string | null;
  matriz: boolean;
  cidade: string | null;
  uf: string | null;
  telefone: string | null;
  mesas: number | null;
  ativo: boolean;
};

type Parametros = Record<string, number | boolean | null> & { id_unidade: number };

const INTERRUPTORES: { campo: string; nome: string; explica: string }[] = [
  {
    campo: "bloquear_retroativo",
    nome: "Travar lançamento em período fechado",
    explica: "Depois do fechamento, ninguém lança para trás sem permissão de reabertura.",
  },
  {
    campo: "permitir_saldo_negativo",
    nome: "Permitir saída sem saldo",
    explica: "A cozinha usa antes de a nota chegar. Bloquear trava a operação; aqui o sistema avisa.",
  },
  {
    campo: "exigir_motivo_perda",
    nome: "Exigir motivo na perda",
    explica: "Perda com nome vira decisão; perda anônima vira desconfiança.",
  },
  {
    campo: "exigir_local_movimento",
    nome: "Exigir local no movimento",
    explica: "Câmara fria, estoque seco, bar — sem local o inventário não fecha.",
  },
  {
    campo: "bloquear_saida_vencido",
    nome: "Bloquear saída de item vencido",
    explica: "Desligado por padrão: travar em pleno serviço é pior que avisar.",
  },
  {
    campo: "criar_produto_da_nota",
    nome: "Criar produto novo a partir da nota",
    explica: "Item sem vínculo vira produto rascunho — que não entra no estoque até ser revisado.",
  },
];

const NUMEROS: { campo: string; nome: string; dica: string }[] = [
  { campo: "dia_fechamento_cmv", nome: "Dia de fechamento do CMV", dica: "1 a 28" },
  { campo: "alerta_validade_dias", nome: "Alertar validade com (dias)", dica: "0 desliga" },
  { campo: "alerta_variacao_preco_pct", nome: "Avisar se o preço subir (%)", dica: "vs. última compra" },
  { campo: "casas_decimais_qtd", nome: "Casas decimais na quantidade", dica: "0 a 6" },
];

export default function PaginaLojas() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeEditar = pode("admin.unidades");

  const [lojas, setLojas] = useState<Loja[] | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [param, setParam] = useState<Parametros | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    api
      .get<Loja[]>("/unidades?incluir_inativas=true")
      .then((l) => {
        setLojas(l);
        setSel(l[0]?.id ?? null);
      })
      .catch((e) => setErro(e.message));
  }, []);

  useEffect(() => {
    if (sel == null) return;
    setParam(null);
    api
      .get<Parametros>(`/unidades/${sel}/parametros`)
      .then(setParam)
      .catch((e) => setErro(e.message));
  }, [sel]);

  async function salvarParametros() {
    if (!param) return;
    setErro("");
    try {
      const { id_unidade, ...resto } = param;
      await api.put(`/unidades/${id_unidade}/parametros`, resto);
      aviso.sucesso("Parâmetros salvos.");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
    }
  }

  if (erro && !lojas) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!lojas) return <Carregando />;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Administração</p>
        <h1 className="mt-1 text-[30px] font-bold tracking-tight">Lojas e parâmetros</h1>
        <p className="mt-1 max-w-[64ch] text-suave">
          Todo movimento nasce carimbado com a loja. Os parâmetros abaixo mudam o comportamento
          do sistema — não são preferência de tela.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao titulo="Lojas">
        <div className="overflow-x-auto">
          <table className="tabela">
            <thead>
              <tr>
                <th>Nome</th>
                <th>CNPJ</th>
                <th>Cidade</th>
                <th>Mesas</th>
                <th>Situação</th>
              </tr>
            </thead>
            <tbody>
              {lojas.map((l) => (
                <tr
                  key={l.id}
                  onClick={() => setSel(l.id)}
                  className={`cursor-pointer ${sel === l.id ? "bg-erva-claro" : ""}`}
                >
                  <td>
                    <span className="font-semibold">{l.nome}</span>
                    {l.matriz && (
                      <span className="ml-2">
                        <Etiqueta cor="erva">matriz</Etiqueta>
                      </span>
                    )}
                  </td>
                  <td className="mono">{l.cnpj ?? "—"}</td>
                  <td>{l.cidade ? `${l.cidade}${l.uf ? "/" + l.uf : ""}` : "—"}</td>
                  <td className="mono">{l.mesas ?? "—"}</td>
                  <td>{l.ativo ? "ativa" : "inativa"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-[13.5px] text-suave">
          Cadastro completo da loja (endereço, horário de funcionamento) entra junto com a
          segunda unidade — hoje há uma só.
        </p>
      </Cartao>

      <Cartao
        titulo="Parâmetros de operação"
        descricao={lojas.find((l) => l.id === sel)?.nome}
        acao={
          podeEditar && param ? (
            <button className="btn btn-primario" onClick={salvarParametros}>
              Salvar
            </button>
          ) : undefined
        }
      >
        {!param ? (
          <Carregando />
        ) : (
          <div className="flex flex-col gap-5">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {NUMEROS.map((n) => (
                <Campo key={n.campo} rotulo={n.nome} dica={n.dica}>
                  <input
                    className="campo mono"
                    type="number"
                    disabled={!podeEditar}
                    value={String(param[n.campo] ?? "")}
                    onChange={(e) =>
                      setParam({ ...param, [n.campo]: Number(e.target.value) })
                    }
                  />
                </Campo>
              ))}
            </div>

            <ul className="grid gap-px overflow-hidden rounded border border-linha bg-linha sm:grid-cols-2">
              {INTERRUPTORES.map((i) => (
                <li key={i.campo} className="flex items-start gap-3 bg-superficie p-4">
                  <input
                    id={i.campo}
                    type="checkbox"
                    className="mt-1 h-4 w-4 accent-erva"
                    disabled={!podeEditar}
                    checked={!!param[i.campo]}
                    onChange={(e) => setParam({ ...param, [i.campo]: e.target.checked })}
                  />
                  <label htmlFor={i.campo} className="cursor-pointer">
                    <span className="block text-[14.5px] font-semibold">{i.nome}</span>
                    <span className="mt-0.5 block text-[13px] leading-snug text-suave">
                      {i.explica}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Cartao>
    </div>
  );
}
