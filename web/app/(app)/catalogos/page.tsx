"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import CabecalhoTela from "@/components/cabecalho-tela";
import { Aviso, Carregando, Etiqueta, Vazio } from "@/components/ui";
import { useSessao } from "@/lib/sessao";
import * as cat from "@/lib/catalogos";
import NovoCatalogo from "./novo-catalogo";

/**
 * Os catálogos da loja — o que a casa publica para o cliente.
 *
 * 🔑 **Pedido do dono (21/09/2026):** *"o cabeçalho do catálogo, origem, o nome
 * dele no site do cliente, o período de publicação, a situação."*
 *
 * 🔑 **Cartões, não tabela** (reforma de 15/10/2026, pedido do dono: *"o cadastro
 * de catálogos não está muito intuitivo"*). A tabela tinha sete colunas: o
 * período quebrava em seis linhas, os botões da direita saíam da tela e
 * "Situação" e "No ar hoje" respondiam quase a mesma pergunta. Cada cartão
 * agora diz o que importa de relance — um selo só para o estado, quantos pratos,
 * o que falta neles — e ABRE o catálogo. Editar, publicar e o PDF moram na
 * página dele.
 * 🔑 **"No ar" continua NÃO sendo o mesmo que ATIVO**: um ativo com o período
 * vencido aparece como "ativo, fora do período". Quem decide é o servidor.
 */

const dia = (d: string | null) => (d ? new Date(d + "T12:00").toLocaleDateString("pt-BR") : null);

/** O período em palavras — as duas pontas são opcionais e querem dizer coisas diferentes. */
function periodoEmPalavras(c: cat.Catalogo): string {
  const de = dia(c.publica_de);
  const ate = dia(c.publica_ate);
  if (de && ate) return `${de} a ${ate}`;
  if (de) return `de ${de}, sem prazo`;
  if (ate) return `até ${ate}`;
  return "sem período — vale enquanto estiver ativo";
}

function Selo({ c }: { c: cat.Catalogo }) {
  if (c.publicado_hoje) return <Etiqueta cor="erva">no ar</Etiqueta>;
  if (c.situacao === "ATIVO") return <Etiqueta cor="alerta">ativo, fora do período</Etiqueta>;
  return <Etiqueta cor={c.situacao === "RASCUNHO" ? "alerta" : "neutro"}>{cat.ROTULO_SITUACAO[c.situacao].toLowerCase()}</Etiqueta>;
}

/** O que falta no catálogo, em frases curtas — o que o cartão avisa. */
function pendencias(c: cat.Catalogo): string[] {
  if (c.origem !== cat.ORIGEM_PRODUTOS) {
    // ⚠️ Ativo sem PDF é avisado: o site anuncia um cardápio e não tem o que mostrar.
    return !c.arquivo_url ? [c.situacao === "ATIVO" ? "sem PDF — o site não tem o que exibir" : "sem PDF"] : [];
  }
  const r = c.resumo;
  if (!r?.pratos) return ["nenhum prato ainda"];
  const f: string[] = [];
  if (r.sem_foto) f.push(`${r.sem_foto} sem foto`);
  if (r.sem_descricao) f.push(`${r.sem_descricao} sem descrição`);
  if (r.inativos) f.push(`${r.inativos} inativo(s)`);
  return f;
}

export default function PaginaCatalogos() {
  const { pode } = useSessao();
  const podeEditar = pode("catalogos.editar");
  const [lista, setLista] = useState<cat.Catalogo[] | null>(null);
  const [op, setOp] = useState<cat.Opcoes | null>(null);
  const [filtro, setFiltro] = useState<cat.Situacao | "">("");
  const [erro, setErro] = useState("");
  const [criando, setCriando] = useState(false);

  const carregar = useCallback(async () => {
    setErro("");
    try {
      setLista(await cat.listar(filtro));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [filtro]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // ⚠️ O vocabulário vem do SERVIDOR: uma cópia aqui divergiria calada.
  useEffect(() => {
    cat.opcoes().then(setOp).catch(() => setOp(null));
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Portal de Clientes"
        titulo={<>Catálogos</>}
        explica={<>O que o site de reservas e o Cardápio Vivo apresentam ao cliente. Abra um catálogo para montar, conferir e publicar.</>}
        acoes={
          <div className="nao-imprimir flex flex-wrap items-end gap-2">
            <label>
              <span className="rotulo-campo">Situação</span>
              {/* ⚠️ A largura mora no INVÓLUCRO: `.campo` tem `width:100%` fora de camada. */}
              <span className="mt-1.5 block w-[160px]">
                <select className="campo" id="filtro-situacao" value={filtro}
                        onChange={(e) => setFiltro(e.target.value as cat.Situacao | "")}>
                  <option value="">Todas</option>
                  {(op?.situacoes ?? []).map((s) => (
                    <option key={s} value={s}>{cat.ROTULO_SITUACAO[s]}</option>
                  ))}
                </select>
              </span>
            </label>
            {podeEditar && (
              <button type="button" className="btn btn-primario" disabled={!op} onClick={() => setCriando(true)}>
                Novo catálogo
              </button>
            )}
          </div>
        }
      />

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {!lista ? (
        <Carregando />
      ) : !lista.length ? (
        <Vazio>
          {filtro
            ? "Nenhum catálogo nesta situação."
            : "Nenhum catálogo ainda. O primeiro nasce como rascunho — dá para montá-lo com calma e só publicar depois de conferir."}
        </Vazio>
      ) : (
        <ul className="grid gap-4 lg:grid-cols-2" aria-label="catálogos desta loja">
          {lista.map((c) => {
            const faltas = pendencias(c);
            return (
              <li key={c.id} className="cartao flex flex-col gap-3 p-5" data-catalogo={c.id}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <Link href={`/catalogos/${c.id}`} className="link-registro text-[17px] font-bold tracking-tight">
                    {c.nome}
                  </Link>
                  <span className="flex flex-wrap gap-1.5">
                    <Selo c={c} />
                    {c.cardapio_vivo && <Etiqueta cor="erva">Cardápio Vivo</Etiqueta>}
                  </span>
                </div>
                <p className="text-[13.5px] text-suave">
                  {cat.APRESENTA_ORIGEM[c.origem]?.curto ?? c.origem}
                  {c.origem === cat.ORIGEM_PRODUTOS && c.resumo?.pratos ? ` · ${c.resumo.pratos} prato(s)` : ""}
                  {c.origem !== cat.ORIGEM_PRODUTOS && c.arquivo_nome ? ` · ${c.arquivo_nome}` : ""}
                  {" · "}{periodoEmPalavras(c)}
                  {c.exige_cadastro && " · exige cadastro"}
                </p>
                {c.observacao && <p className="text-[13px] text-suave">{c.observacao}</p>}
                <div className="mt-auto flex flex-wrap items-center justify-between gap-2">
                  <span className={`text-[13px] ${faltas.length ? "text-alerta" : "text-suave"}`}>
                    {faltas.length ? `⚠ ${faltas.join(" · ")}` : "nada pendente"}
                  </span>
                  <Link href={`/catalogos/${c.id}`} className="btn btn-secundario">Abrir</Link>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {criando && op && <NovoCatalogo origens={op.origens} aoFechar={() => setCriando(false)} />}
    </div>
  );
}
