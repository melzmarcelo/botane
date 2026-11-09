"use client";

import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Confirmacao, Etiqueta } from "@/components/ui";
import Voltar from "@/components/voltar";
import { api } from "@/lib/api";
import type { Local, Setor } from "@/lib/cadastros";
import { numeroParaMoeda, plural, reais } from "@/lib/numeros";
import {
  COR_GARANTIA, COR_PREVENTIVA, apagar, criar, dataBr, doProduto, imprimirPlaquetas, obter, salvar,
  type BemDetalhe, type DoProduto,
} from "@/lib/patrimonio";
import { useSessao } from "@/lib/sessao";

import AbaCustos from "./aba-custos";
import AbaDados from "./aba-dados";
import AbaGarantia from "./aba-garantia";
import AbaManutencoes from "./aba-manutencoes";
import AbaPreventiva from "./aba-preventiva";
import AbasDaFicha, { DO_FORMULARIO, ehAba, type Aba } from "./abas-da-ficha";
import FaixaDoBem from "./faixa";
import { VAZIO, emDias, paraCorpo, paraForm, type Form } from "./form";

/**
 * A ficha de um bem, em abas: Dados do bem · Garantia · Preventiva · Manutenções · Custos,
 * com os quatro números da ficha numa faixa acima. A mesma tela cria (`/patrimonio/novo`).
 *
 * 🔑 **Pedido do dono (09/11/2026)**, com um desenho da ficha em abas: "ajustar o layout mas
 * deixar no padrão que temos no sistema hoje" — por isso a faixa é a do Início, as abas são as
 * da ficha do produto e cada bloco é um `Cartao`.
 * 🔑 **Um formulário só por baixo das abas**: o estado mora aqui, e o Salvar do cabeçalho grava
 * o que foi mexido em Dados, Garantia ou Preventiva. Manutenções e Custos ficam FORA do
 * `<form>` (a manutenção tem o formulário dela, e form dentro de form não existe).
 * 🔑 **A aba vai no endereço** (`?aba=manutencoes`): o link do alerta e a bateria abrem direto.
 * 🔑 **A próxima preventiva, a garantia e os custos são do servidor**: a tela mostra, não calcula.
 */
export default function FichaDoBem() {
  const { id } = useParams<{ id: string }>();
  const novo = id === "novo";
  const router = useRouter();
  const busca = useSearchParams();
  const caminho = usePathname();
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeCadastrar = pode("patrimonio.cadastrar");
  const podeManutencao = pode("patrimonio.manutencao") || podeCadastrar;
  const [bem, setBem] = useState<BemDetalhe | null>(null);
  const [f, setF] = useState<Form>(VAZIO);
  const [setores, setSetores] = useState<Setor[]>([]);
  const [locais, setLocais] = useState<Local[]>([]);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [apagando, setApagando] = useState(false);
  const [produto, setProduto] = useState<{ id: number; rotulo: string } | null>(null);
  const pedida = busca.get("aba");
  const aba: Aba = ehAba(pedida) && (!novo || DO_FORMULARIO.includes(pedida)) ? pedida : "dados";
  const doQr = busca.get("produto");

  const irPara = useCallback((a: Aba) => {
    const q = new URLSearchParams(busca.toString());
    if (a === "dados") q.delete("aba"); else q.set("aba", a);
    router.replace(q.size ? `${caminho}?${q}` : caminho, { scroll: false });
  }, [busca, caminho, router]);

  const carregar = useCallback(() => {
    if (novo) return;
    obter(Number(id))
      .then((b) => {
        setBem(b);
        setF(paraForm(b));
        setProduto(b.id_produto ? { id: b.id_produto, rotulo: b.produto ?? "" } : null);
        setErro("");
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "Bem não encontrado"));
  }, [id, novo]);

  useEffect(() => { carregar(); }, [carregar]);
  useEffect(() => {
    api.get<Setor[]>("/setores").then(setSetores).catch(() => {});
    api.get<Local[]>("/locais").then(setLocais).catch(() => {});
  }, []);

  /** Preenche só o que está VAZIO com a sugestão do produto (a última entrada dele). */
  const completar = useCallback((d: DoProduto) => {
    setProduto({ id: d.produto.id, rotulo: d.produto.nome });
    setF((atual) => {
      const novoF: Form = { ...atual, id_produto: String(d.produto.id) };
      const s = d.sugestao;
      const vazio = (k: string) => !atual[k];
      if (vazio("descricao")) novoF.descricao = s.descricao;
      if (s.id_setor && vazio("id_setor")) novoF.id_setor = String(s.id_setor);
      if (s.id_local && vazio("id_local")) novoF.id_local = String(s.id_local);
      if (s.data_compra && vazio("data_compra")) novoF.data_compra = s.data_compra;
      if (s.fornecedor && vazio("fornecedor")) novoF.fornecedor = s.fornecedor;
      if (s.nota_fiscal && vazio("nota_fiscal")) novoF.nota_fiscal = s.nota_fiscal;
      if (s.valor_compra && vazio("valor_compra")) novoF.valor_compra = numeroParaMoeda(s.valor_compra);
      return novoF;
    });
  }, []);

  useEffect(() => {
    if (novo && doQr) doProduto(Number(doQr)).then(completar).catch(() => {});
  }, [novo, doQr, completar]);

  function escolherProduto(item: { id: number; nome: string } | null) {
    if (!item) {
      setProduto(null);
      setF({ ...f, id_produto: "" });
    } else if (novo) {
      doProduto(item.id).then(completar).catch(() => {
        setProduto({ id: item.id, rotulo: item.nome });
        setF({ ...f, id_produto: String(item.id) });
      });
    } else {
      setProduto({ id: item.id, rotulo: item.nome });
      setF({ ...f, id_produto: String(item.id), descricao: f.descricao || item.nome });
    }
  }

  const muda = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function gravar(e: FormEvent) {
    e.preventDefault();
    // ⚠️ O nome é o único obrigatório, e mora na aba Dados: salvar de outra aba sem ele
    // levaria a pessoa a um erro sem campo à vista.
    if (!f.descricao?.trim()) {
      irPara("dados");
      aviso.erro("Dê um nome ao equipamento (aba Dados do bem).");
      return;
    }
    setSalvando(true);
    try {
      if (novo) {
        const r = await criar(paraCorpo(f));
        aviso.sucesso(r.message);
        router.replace(`/patrimonio/${r.id}`);
      } else {
        aviso.sucesso((await salvar(Number(id), paraCorpo(f))).message);
        carregar();
      }
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  async function confirmarApagar() {
    try {
      aviso.sucesso((await apagar(Number(id))).message);
      router.replace("/patrimonio");
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível apagar");
      setApagando(false);
    }
  }

  function registrarManutencao() {
    irPara("manutencoes");
    // A aba monta no próximo quadro; aí o foco vai para o primeiro campo do registro.
    setTimeout(() => document.getElementById("manutencao-tipo")?.focus(), 120);
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!novo && !bem) return <Carregando />;

  const parado = bem && ["EM_MANUTENCAO", "PARADO"].includes(bem.situacao);
  const travado = !podeCadastrar;
  const props = { f, setF, muda, travado, bem };

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4 xl:flex-nowrap">
        <div className="min-w-0 flex-1">
          <Voltar href="/patrimonio">patrimônio</Voltar>
          <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
            {novo ? "Novo bem" : <><span className="mono">{bem!.codigo}</span> · {bem!.descricao}</>}
          </h1>
          {bem && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[13.5px]">
              <Etiqueta cor={bem.situacao === "EM_USO" ? "erva" : "alerta"}>{bem.situacao_txt}</Etiqueta>
              {bem.criticidade && (
                <Etiqueta cor={bem.criticidade === "ALTA" ? "alerta" : "neutro"}>Criticidade {bem.criticidade_txt?.toLowerCase()}</Etiqueta>
              )}
              {["ATIVA", "VENCE_30"].includes(bem.status_garantia) && (
                <Etiqueta cor={COR_GARANTIA[bem.status_garantia]}>
                  {bem.status_garantia === "VENCE_30" ? `Garantia vence ${emDias(bem.garantia_dias)}` : `Em garantia até ${dataBr(bem.garantia_ate)}`}
                </Etiqueta>
              )}
              {bem.status_preventiva !== "FORA" && (
                <Etiqueta cor={COR_PREVENTIVA[bem.status_preventiva] ?? "neutro"}>
                  Preventiva: {bem.preventiva_txt}
                  {bem.proxima_preventiva ? ` · próxima ${dataBr(bem.proxima_preventiva)}` : ""}
                </Etiqueta>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2 xl:shrink-0 xl:pt-9">
          {bem && podeCadastrar && (
            <button type="button" className="btn btn-secundario" id="bem-plaqueta"
                    onClick={() => imprimirPlaquetas([bem.id]).catch((x) =>
                      aviso.erro(x instanceof Error ? x.message : "Não foi possível imprimir"))}>
              Imprimir plaqueta
            </button>
          )}
          {bem && podeManutencao && (
            <button type="button" className="btn btn-secundario" id="bem-registrar-manutencao" onClick={registrarManutencao}>
              Registrar manutenção
            </button>
          )}
          {podeCadastrar && (
            <button type="submit" form="bem-form" className="btn btn-primario" id="bem-salvar"
                    disabled={salvando} aria-busy={salvando}>
              {novo ? "Cadastrar" : "Salvar"}
            </button>
          )}
        </div>
      </header>

      {parado && bem?.estoque_no_local && bem.estoque_no_local.produtos > 0 && (
        <Aviso tipo="erro">
          <b>{bem.local}</b> guarda {plural(bem.estoque_no_local.produtos, "produto", "produtos")} com saldo
          {bem.estoque_no_local.valor !== null ? ` (${reais(bem.estoque_no_local.valor)})` : ""}.
          Com o equipamento {bem.situacao_txt.toLowerCase()}, confira se precisam ir para outro local.
        </Aviso>
      )}

      {bem && <FaixaDoBem bem={bem} irPara={irPara} />}

      <AbasDaFicha aba={aba} novo={novo} aoTrocar={irPara} contagem={bem?.manutencoes.length} />

      {/* O form existe sempre (o Salvar do cabeçalho aponta para ele), mesmo vazio nas abas de fora. */}
      <form onSubmit={gravar} id="bem-form" className="flex flex-col gap-6" role="tabpanel"
            aria-labelledby={`aba-${aba}`} hidden={!DO_FORMULARIO.includes(aba)}>
        {aba === "dados" && (
          <AbaDados {...props} setores={setores} locais={locais} produto={produto} aoEscolherProduto={escolherProduto} />
        )}
        {aba === "garantia" && <AbaGarantia {...props} />}
        {aba === "preventiva" && <AbaPreventiva {...props} />}
        {aba === "dados" && podeCadastrar && bem && !bem.manutencoes.length && (
          <div>
            <button type="button" className="btn btn-secundario" onClick={() => setApagando(true)}>Apagar</button>
          </div>
        )}
      </form>

      {bem && aba === "manutencoes" && (
        <div role="tabpanel" aria-labelledby="aba-manutencoes">
          <AbaManutencoes bem={bem} podeRegistrar={podeManutencao} aoMudar={carregar} />
        </div>
      )}
      {bem && aba === "custos" && (
        <div role="tabpanel" aria-labelledby="aba-custos"><AbaCustos bem={bem} /></div>
      )}

      {apagando && (
        <Confirmacao titulo="Apagar este bem?" perigo rotuloConfirmar="Apagar"
                     aoConfirmar={() => void confirmarApagar()} aoCancelar={() => setApagando(false)}>
          Apagar é para cadastro feito por engano. Um bem que existiu e saiu da casa se
          <b> baixa</b> (Situação ▸ Baixado), para o histórico continuar existindo.
        </Confirmacao>
      )}
    </div>
  );
}
