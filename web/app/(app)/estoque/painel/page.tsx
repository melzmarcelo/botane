"use client";

import { useEffect, useState } from "react";

import BuscaCadastro from "@/components/busca-cadastro";
import CabecalhoTela from "@/components/cabecalho-tela";
import { Aviso, Carregando, Cartao, Vazio } from "@/components/ui";
import { fonteProdutos, type ItemBusca } from "@/lib/busca-cadastro";
import { hoje } from "@/lib/datas";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import {
  pedirPerdas, pedirProduto, pedirVisaoGeral,
  type Agrupar, type PainelPerdas, type PainelProduto, type VisaoGeral,
} from "@/lib/estoque-painel";

import { andar, janela, MODOS, nomeDoRecorte, type Modo } from "../../vendas/painel/periodo";
import Geral from "./geral";
import Perdas, { type Recorte } from "./perdas";
import Produto from "./produto";

/**
 * O painel de estoque — a visão para decidir (pedido do dono, 22/10/2026).
 *
 * Três abas, cada uma uma pergunta:
 * - **Visão geral**: o que pede ação agora — negativo, abaixo do mínimo, parado, validade e
 *   perdas do mês. O cartão leva à lista de Saldos já filtrada.
 * - **Por produto**: como anda um produto — o saldo no tempo, o que entrou e saiu, e em
 *   quantos dias acaba.
 * - **Perdas**: onde e por quê — motivo, setor, categoria, prateleira e produto.
 *
 * 🔑 **Tudo na URL** (`useEstadoNaUrl`), como no painel de vendas: voltar de um produto
 * devolve o mesmo recorte, e o recorte vira um link que se manda para alguém.
 * ⚠️ Sem datas, o servidor usa os últimos 30 dias.
 */

const ABAS = [
  { valor: "geral", nome: "Visão geral" },
  { valor: "produto", nome: "Por produto" },
  { valor: "perdas", nome: "Perdas" },
] as const;
type Aba = (typeof ABAS)[number]["valor"];

// Um dia não tem evolução de saldo: o painel de estoque começa na semana.
const MODOS_ESTOQUE = MODOS.filter((m) => m.valor !== "dia");
const PRODUTOS = fonteProdutos();

export default function PainelDeEstoque() {
  const [aba, setAba] = useEstadoNaUrl<string>("aba", "geral");
  const [modo, setModo] = useEstadoNaUrl<string>("modo", "periodo");
  const [de, setDe] = useEstadoNaUrl<string>("de", "", { atraso: 0 });
  const [ate, setAte] = useEstadoNaUrl<string>("ate", "", { atraso: 0 });
  const [agrupar, setAgrupar] = useEstadoNaUrl<string>("agrupar", "dia");
  const [idProduto, setIdProduto] = useEstadoNaUrl<string>("produto", "");
  const [motivo, setMotivo] = useEstadoNaUrl<string>("motivo", "");
  const [categoria, setCategoria] = useEstadoNaUrl<string>("categoria", "");
  const [setor, setSetor] = useEstadoNaUrl<string>("setor", "");
  const [local, setLocal] = useEstadoNaUrl<string>("local", "");

  const [geral, setGeral] = useState<VisaoGeral | null>(null);
  const [prod, setProd] = useState<PainelProduto | null>(null);
  const [perdas, setPerdas] = useState<PainelPerdas | null>(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(true);

  const a = (ABAS.some((x) => x.valor === aba) ? aba : "geral") as Aba;
  const m = (MODOS_ESTOQUE.some((x) => x.valor === modo) ? modo : "periodo") as Modo;
  const num = (s: string) => (s === "" ? null : Number(s));

  useEffect(() => {
    let vivo = true;
    setErro("");
    setCarregando(true);
    const pedido: Promise<unknown> =
      a === "geral" ? pedirVisaoGeral().then((r) => vivo && setGeral(r))
      : a === "produto" ? (idProduto
          ? pedirProduto(Number(idProduto), de || undefined, ate || undefined, agrupar as Agrupar)
              .then((r) => vivo && setProd(r))
          : Promise.resolve(setProd(null)))
      : pedirPerdas({
          inicio: de || undefined, fim: ate || undefined, agrupar: agrupar as Agrupar,
          motivo: num(motivo), categoria: num(categoria), setor: num(setor), local: num(local),
        }).then((r) => vivo && setPerdas(r));
    pedido
      .catch((e) => vivo && setErro(e instanceof Error ? e.message : "Falha ao carregar o painel"))
      .finally(() => vivo && setCarregando(false));
    return () => {
      vivo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a, idProduto, de, ate, agrupar, motivo, categoria, setor, local]);

  // O recorte EM VIGOR: o da URL, ou o que o servidor escolheu (os últimos 30 dias).
  const resposta = a === "produto" ? prod : a === "perdas" ? perdas : null;
  const inicio = de || resposta?.inicio || "";
  const fim = ate || resposta?.fim || "";

  function ir([novoDe, novoAte]: [string, string]) {
    setDe(novoDe);
    setAte(novoAte);
  }
  function trocarModo(novo: Modo) {
    setModo(novo);
    if (inicio) ir(janela(novo, inicio, inicio, fim));
    if (novo === "semana") setAgrupar("dia");
  }
  function verProduto(id: number) {
    setIdProduto(String(id));
    setAba("produto");
  }
  function verPerdasDoMes() {
    setAba("perdas");
    setModo("mes");
    ir(janela("mes", hoje()));
    setAgrupar("dia");
  }
  const filtrosPerdas: Record<Recorte, number | null> = {
    motivo: num(motivo), categoria: num(categoria), setor: num(setor), local: num(local),
  };
  function filtrarPerdas(r: Recorte, id: number | null) {
    const v = id === null ? "" : String(id);
    ({ motivo: setMotivo, categoria: setCategoria, setor: setSetor, local: setLocal })[r](v);
  }
  const comRecorte = !!(motivo || categoria || setor || local);
  const nomeDoFiltro = (r: Recorte) => {
    const lista = r === "motivo" ? perdas?.por_motivo : r === "categoria" ? perdas?.por_categoria
      : r === "setor" ? perdas?.por_setor : perdas?.por_local;
    return lista?.find((g) => g.id === filtrosPerdas[r])?.nome;
  };

  return (
    <div className="space-y-4">
      <CabecalhoTela
        caminho="Estoque"
        titulo={<>Painel {a !== "geral" && inicio && (
          <span className="font-normal text-suave">· {nomeDoRecorte(m, inicio, fim)}</span>
        )}</>}
        explica={
          <>
            A visão do estoque para decidir: o que está negativo ou abaixo do mínimo (o cartão
            leva à lista para agir), como anda cada produto e onde estão as perdas. Os números
            são os do razão, líquidos de estorno.
          </>
        }
      />

      <nav className="flex gap-2" aria-label="abas do painel">
        {ABAS.map((x) => (
          <button key={x.valor} type="button" data-aba={x.valor}
                  className={`btn ${a === x.valor ? "btn-primario" : "btn-secundario"}`}
                  onClick={() => setAba(x.valor)}>
            {x.nome}
          </button>
        ))}
      </nav>

      {a !== "geral" && (
        <Cartao>
          <div className="flex flex-wrap items-center gap-3" id="painel-estoque-filtros">
            {a === "produto" && (
              <div className="min-w-[16rem] flex-1 sm:max-w-[26rem]">
                <BuscaCadastro
                  id="painel-estoque-produto"
                  fonte={PRODUTOS}
                  selecionado={prod && String(prod.produto.id) === idProduto
                    ? { id: prod.produto.id, rotulo: `${prod.produto.codigo} · ${prod.produto.nome}` }
                    : idProduto ? { id: Number(idProduto), rotulo: "" } : null}
                  aoEscolher={(item: ItemBusca | null) => setIdProduto(item ? String(item.id) : "")}
                />
              </div>
            )}

            <div className="flex overflow-hidden rounded-lg border border-linha" role="group" aria-label="recorte">
              {MODOS_ESTOQUE.map((x) => (
                <button key={x.valor} type="button" data-modo={x.valor}
                        className={`px-3 py-1.5 text-[13.5px] ${m === x.valor ? "bg-erva font-bold text-white" : "hover:bg-linha/40"}`}
                        onClick={() => trocarModo(x.valor)}>
                  {x.nome}
                </button>
              ))}
            </div>

            {m === "periodo" && (
              <div className="flex flex-wrap items-center gap-2 text-[13.5px]">
                <input type="date" className="campo py-1" style={{ width: "auto" }} id="painel-estoque-de" aria-label="início"
                       value={inicio} onChange={(e) => e.target.value && setDe(e.target.value)} />
                <span className="text-suave">a</span>
                <input type="date" className="campo py-1" style={{ width: "auto" }} id="painel-estoque-ate" aria-label="fim"
                       value={fim} onChange={(e) => e.target.value && setAte(e.target.value)} />
              </div>
            )}

            <div className="flex items-center gap-1">
              <button type="button" className="link-acao px-2 text-[18px]" aria-label="recorte anterior"
                      disabled={!inicio || carregando} onClick={() => ir(andar(m, inicio, fim, -1))}>‹</button>
              <button type="button" className="link-acao px-2 text-[18px]" aria-label="próximo recorte"
                      disabled={!inicio || carregando} onClick={() => ir(andar(m, inicio, fim, 1))}>›</button>
            </div>

            <label className="flex items-center gap-2 text-[13.5px]">
              <span className="text-suave">por</span>
              <select className="campo py-1" style={{ width: "auto" }} id="painel-estoque-agrupar" value={agrupar}
                      onChange={(e) => setAgrupar(e.target.value)}>
                <option value="dia">dia</option>
                <option value="semana">semana</option>
                <option value="mes">mês</option>
              </select>
            </label>

            {a === "perdas" && comRecorte && (
              <button type="button" className="link-acao text-[13px]"
                      onClick={() => { setMotivo(""); setCategoria(""); setSetor(""); setLocal(""); }}>
                limpar recorte ({(["motivo", "setor", "categoria", "local"] as Recorte[])
                  .filter((r) => filtrosPerdas[r] !== null)
                  .map((r) => nomeDoFiltro(r) ?? r).join(" · ")})
              </button>
            )}
          </div>
        </Cartao>
      )}

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <div className={carregando ? "opacity-60" : ""} aria-busy={carregando}>
        {a === "geral" && (geral ? (
          <Geral g={geral} aoVerPerdas={verPerdasDoMes} aoVerProduto={verProduto} />
        ) : carregando && <Carregando />)}

        {a === "produto" && (!idProduto ? (
          <Cartao><Vazio>Escolha um produto para ver como anda o estoque dele.</Vazio></Cartao>
        ) : prod ? <Produto d={prod} /> : carregando && <Carregando />)}

        {a === "perdas" && (perdas ? (
          <Perdas d={perdas} filtros={filtrosPerdas} aoFiltrar={filtrarPerdas} aoVerProduto={verProduto} />
        ) : carregando && <Carregando />)}
      </div>
    </div>
  );
}
