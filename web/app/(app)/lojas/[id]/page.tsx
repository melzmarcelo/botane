"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Cartao, Etiqueta } from "@/components/ui";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import FormularioLoja, { corpoDaLoja, LOJA_VAZIA, LojaForm } from "../formulario";

/**
 * Uma loja: o cadastro dela e os parâmetros que mudam o comportamento do
 * sistema nela.
 *
 * 🔑 **Tudo de uma loja num lugar só.** Os parâmetros moravam na LISTA, e
 * escolher a loja era clicar numa linha para o bloco aparecer embaixo — o mesmo
 * padrão que Compras, Vendas e Fornecedores já abandonaram. Aqui o endereço
 * guarda a loja: dá para voltar, guardar o link e saber de qual se está falando.
 *
 * ⚠️ **A integração NÃO fica aqui**, e é de propósito: ela é por loja, mas mora
 * na tela de Integrações, resolvida pela loja ATUAL do seletor. Duas portas para
 * a mesma configuração seriam duas versões da mesma verdade.
 */

type Loja = {
  id: number;
  nome: string;
  apelido: string | null;
  cnpj: string | null;
  inscricao_estadual: string | null;
  matriz: boolean;
  ativo: boolean;
  cep: string | null;
  logradouro: string | null;
  numero: string | null;
  complemento: string | null;
  bairro: string | null;
  cidade: string | null;
  uf: string | null;
  telefone: string | null;
  email: string | null;
  mesas: number | null;
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

// ⚠️ `dia_fechamento_cmv` saiu daqui: virou parte do bloco de ritmo do
// fechamento, onde só aparece quando o ciclo é mensal. Perdido no meio dos
// outros números, ele prometia uma configuração que ninguém lia — era campo
// morto até a virada dos ciclos.
const NUMEROS: { campo: string; nome: string; dica: string }[] = [
  { campo: "alerta_validade_dias", nome: "Alertar validade com (dias)", dica: "0 desliga" },
  { campo: "alerta_variacao_preco_pct", nome: "Avisar se o preço subir (%)", dica: "vs. última compra" },
  { campo: "casas_decimais_qtd", nome: "Casas decimais na quantidade", dica: "0 a 6" },
];

const CICLOS = [
  { valor: "DIARIO", nome: "Diariamente", explica: "Cada dia é um período." },
  { valor: "SEMANAL", nome: "Semanalmente", explica: "Cada semana é um período." },
  { valor: "MENSAL", nome: "Mensalmente", explica: "Cada mês é um período." },
];

// ISO, igual ao servidor: 1 = segunda … 7 = domingo.
const DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"];

type Previa = { descricao: string; periodos: { inicio: string; fim: string; rotulo: string }[] };

export default function PaginaLoja() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeEditar = pode("admin.unidades");
  const id = Number(useParams().id);

  const [loja, setLoja] = useState<Loja | null>(null);
  const [f, setF] = useState<LojaForm>(LOJA_VAZIA);
  const [param, setParam] = useState<Parametros | null>(null);
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    if (!id) return;
    api
      .get<Loja[]>("/unidades?incluir_inativas=true")
      .then((lista) => {
        const achada = lista.find((l) => l.id === id) ?? null;
        setLoja(achada);
        if (achada) {
          setF({
            nome: achada.nome ?? "",
            apelido: achada.apelido ?? "",
            cnpj: achada.cnpj ?? "",
            inscricao_estadual: achada.inscricao_estadual ?? "",
            matriz: achada.matriz,
            ativo: achada.ativo,
            cep: achada.cep ?? "",
            logradouro: achada.logradouro ?? "",
            numero: achada.numero ?? "",
            complemento: achada.complemento ?? "",
            bairro: achada.bairro ?? "",
            cidade: achada.cidade ?? "",
            uf: achada.uf ?? "",
            telefone: achada.telefone ?? "",
            email: achada.email ?? "",
            mesas: achada.mesas === null || achada.mesas === undefined ? "" : String(achada.mesas),
          });
        }
      })
      .catch((e) => setErro(e.message));
  }, [id]);

  useEffect(() => {
    if (!id) return;
    api
      .get<Parametros>(`/unidades/${id}/parametros`)
      .then(setParam)
      .catch((e) => setErro(e.message));
  }, [id]);

  // ⚠️ A prévia vem do SERVIDOR, com os valores do formulário — não do banco.
  // É o mesmo código que vai fechar o período de verdade; recalcular semana e
  // mês aqui em TypeScript daria duas aritméticas que concordam hoje e
  // divergem no primeiro caso de borda.
  const ciclo = String(param?.ciclo_fechamento ?? "MENSAL");
  const diaSemana = Number(param?.fechamento_dia_semana ?? 7);
  const diaMes = Number(param?.dia_fechamento_cmv ?? 1);

  useEffect(() => {
    if (!id || !param) return;
    let vivo = true;
    api
      .get<Previa>(
        `/unidades/${id}/parametros/previa-fechamento` +
          `?ciclo=${ciclo}&dia_semana=${diaSemana}&dia_mes=${diaMes}`,
      )
      .then((p) => vivo && setPrevia(p))
      .catch(() => vivo && setPrevia(null));
    return () => {
      vivo = false;
    };
  }, [id, param, ciclo, diaSemana, diaMes]);

  async function salvarCadastro() {
    setOcupado(true);
    try {
      await api.put(`/unidades/${id}`, corpoDaLoja(f));
      aviso.sucesso("Loja salva.");
      // O nome e o apelido aparecem no seletor do topo: sem recarregar, quem
      // acabou de corrigi-los continuaria vendo o antigo até dar F5.
      window.location.reload();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
      setOcupado(false);
    }
  }

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

  if (erro && !loja) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!loja) return <Carregando />;

  return (
    <div className="mx-auto flex max-w-[860px] flex-col gap-6">
      <header>
        <Link href="/lojas" className="link-voltar">
          Lojas
        </Link>
        <h1 className="mt-2 flex flex-wrap items-baseline gap-x-3 text-[26px] font-bold tracking-tight sm:text-[30px]">
          {loja.apelido || loja.nome}
          {loja.matriz && <Etiqueta cor="erva">matriz</Etiqueta>}
          {!loja.ativo && <Etiqueta cor="alerta">inativa</Etiqueta>}
        </h1>
        <p className="mt-1 max-w-[68ch] text-suave">
          O cadastro desta loja e os parâmetros que mudam como o sistema se comporta nela.
          As integrações são configuradas em <Link href="/integracoes">Integrações</Link>, com
          a loja escolhida no seletor do topo.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <FormularioLoja
        valor={f}
        aoTrocar={setF}
        aoSalvar={salvarCadastro}
        ocupado={ocupado}
        rotuloSalvar="Salvar cadastro"
        podeEditar={podeEditar}
        eraMatriz={loja.matriz}
      />

      <Cartao
        titulo="Parâmetros de operação"
        descricao={loja.nome}
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
            {/* O ritmo do fechamento é o parâmetro que muda mais coisa na tela:
                o painel de CMV, a tela inicial e o que o razão aceita lançar.
                Por isso tem bloco próprio, e não uma linha na grade de números. */}
            <section className="rounded border border-linha bg-fundo p-4">
              <p className="rotulo">Ritmo do fechamento do CMV</p>
              <p className="mt-1 text-[13px] leading-snug text-suave">
                De quanto em quanto tempo a casa apura o custo e congela o período. É este
                ritmo que o painel de CMV e a tela inicial passam a mostrar.
              </p>

              <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <Campo rotulo="Fecha">
                  <select
                    className="campo"
                    disabled={!podeEditar}
                    value={ciclo}
                    onChange={(e) =>
                      setParam({ ...param, ciclo_fechamento: e.target.value as never })
                    }
                  >
                    {CICLOS.map((c) => (
                      <option key={c.valor} value={c.valor}>
                        {c.nome}
                      </option>
                    ))}
                  </select>
                </Campo>

                {/* Cada ritmo pede uma pergunta diferente — e só uma. Mostrar as
                    duas faria escolher um dia da semana num fechamento mensal. */}
                {ciclo === "SEMANAL" && (
                  <Campo rotulo="Dia em que a semana fecha">
                    <select
                      className="campo"
                      disabled={!podeEditar}
                      value={diaSemana}
                      onChange={(e) =>
                        setParam({ ...param, fechamento_dia_semana: Number(e.target.value) })
                      }
                    >
                      {DIAS.map((d, i) => (
                        <option key={d} value={i + 1}>
                          {d}
                        </option>
                      ))}
                    </select>
                  </Campo>
                )}

                {ciclo === "MENSAL" && (
                  <Campo rotulo="Dia em que o mês começa" dica="1 = mês do calendário">
                    <input
                      className="campo mono"
                      type="number"
                      min={1}
                      max={28}
                      disabled={!podeEditar}
                      value={diaMes}
                      onChange={(e) =>
                        setParam({ ...param, dia_fechamento_cmv: Number(e.target.value) })
                      }
                    />
                  </Campo>
                )}
              </div>

              {previa && (
                <div className="mt-3 border-t border-linha pt-3">
                  <p className="text-[13.5px] font-semibold">{previa.descricao}</p>
                  <p className="mt-2 text-[13px] text-suave">
                    Os próximos períodos ficariam assim:
                  </p>
                  <ul className="mt-1 flex flex-wrap gap-2">
                    {previa.periodos.map((p) => (
                      <li key={p.inicio}>
                        <Etiqueta>{p.rotulo}</Etiqueta>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>

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
