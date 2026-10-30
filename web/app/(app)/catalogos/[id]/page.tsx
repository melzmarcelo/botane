"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Aviso, Carregando, Etiqueta } from "@/components/ui";
import CabecalhoTela from "@/components/cabecalho-tela";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { useSessao } from "@/lib/sessao";
import * as cat from "@/lib/catalogos";
import AbaArquivo from "./aba-arquivo";
import AbaCardapio from "./aba-cardapio";
import AbaPublicacao from "./aba-publicacao";
import AbaPrevia from "./aba-previa";
import PedidosDoCatalogo from "./pedidos";
import { TraducoesDoCatalogo } from "./traducoes-do-catalogo";

/**
 * O editor do cardápio montado aqui dentro.
 *
 * 🔑 **Pedido do dono (22/09/2026):** *"quando for esta origem, ao listar os
 * catálogos, ao clicar sobre vai abrir uma nova página para configuração."*
 *
 * 🔑 **Quatro abas, e o CARDÁPIO abre primeiro** (reforma de 15/10/2026, pedido do
 * dono: *"o cadastro de catálogos não está muito intuitivo"*). Cada fase tinha
 * pendurado o seu cartão onde coube — pedidos e idiomas ficavam EM CIMA das
 * seções, uma tela inteira de configuração que se faz uma vez e ficava no
 * caminho toda vez. Publicar exigia voltar à lista. Agora: Cardápio (onde se
 * passa o tempo), Publicação (a capa e o botão de pôr no ar), Pedidos e Idiomas.
 * ⚠️ A aba vai na URL (`?aba=`): o voltar de quem abriu o produto e a bateria
 * caem na aba certa.
 */

const ABAS = [
  { v: "cardapio", r: "Cardápio" },
  { v: "publicacao", r: "Publicação" },
  { v: "pedidos", r: "Pedidos" },
  { v: "idiomas", r: "Idiomas" },
  // 🔑 30/10/2026 (pedido do dono): o que vai ao ar, com pedido de teste.
  { v: "previa", r: "Pré-visualização" },
];
/** ⚠️ O catálogo de PDF não tem seções, pedidos nem tradução: só o arquivo e a capa. */
const ABAS_PDF = [
  { v: "arquivo", r: "Arquivo" },
  { v: "publicacao", r: "Publicação" },
];

export default function EditorDoCatalogo() {
  const { id } = useParams<{ id: string }>();
  const idCatalogo = Number(id);
  const { pode } = useSessao();
  const podeEditar = pode("catalogos.editar");
  const [abaNaUrl, setAba] = useEstadoNaUrl<string>("aba", "", { atraso: 0 });

  const [capa, setCapa] = useState<cat.Catalogo | null>(null);
  const [erro, setErro] = useState("");

  const recarregarCapa = useCallback(async () => {
    try {
      setCapa(await cat.obter(idCatalogo));
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [idCatalogo]);

  useEffect(() => {
    void recarregarCapa();
  }, [recarregarCapa]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!capa) return <Carregando />;

  const pdf = capa.origem !== cat.ORIGEM_PRODUTOS;
  const abas = pdf ? ABAS_PDF : ABAS;
  // Aba que não existe neste tipo (ou nenhuma) cai na primeira.
  const aba = abas.some((x) => x.v === abaNaUrl) ? abaNaUrl : abas[0].v;

  return (
    <div className="flex flex-col gap-5">
      <CabecalhoTela
        caminho="Catálogos"
        titulo={capa.nome}
        explica={pdf
          ? "Um cardápio em PDF: o arquivo que o site mostra e quando ele vai ao ar."
          : "O cardápio que o site e o Cardápio Vivo mostram: as seções, os pratos de cada uma e quando ele vai ao ar."}
        acoes={
          <span className="flex flex-wrap items-center gap-2">
            {/* 🔑 Um selo só responde "o cliente está vendo?" — "no ar" não é o
                mesmo que ATIVO: um ativo com o período vencido saiu sozinho. */}
            <Etiqueta cor={capa.publicado_hoje ? "erva" : capa.situacao === "RASCUNHO" ? "alerta" : "neutro"}>
              {capa.publicado_hoje
                ? "no ar"
                : capa.situacao === "ATIVO"
                  ? "ativo, fora do período"
                  : cat.ROTULO_SITUACAO[capa.situacao].toLowerCase()}
            </Etiqueta>
            <Link href="/catalogos" className="btn btn-secundario">
              ← catálogos
            </Link>
          </span>
        }
      />

      {/* ⚠️ **O rascunho não está no ar**, e dizer isto aqui evita a casa montar o
          cardápio inteiro e achar que publicou. O botão leva aonde se publica. */}
      {capa.situacao !== "ATIVO" && aba !== "publicacao" && (
        <Aviso tipo="info">
          Este catálogo está como <b>{cat.ROTULO_SITUACAO[capa.situacao]}</b> — o cliente
          ainda não o vê.{" "}
          <button type="button" className="text-erva underline underline-offset-2"
                  onClick={() => setAba("publicacao")}>
            Publicar
          </button>{" "}
          quando ele estiver pronto.
        </Aviso>
      )}

      <div className="flex gap-1 overflow-x-auto border-b border-linha" role="tablist" aria-label="partes do catálogo">
        {abas.map((o) => (
          <button key={o.v} type="button" role="tab" aria-selected={aba === o.v}
                  onClick={() => setAba(o.v)}
                  className={`-mb-px shrink-0 border-b-2 px-4 py-2 text-[14px] font-semibold ${
                    aba === o.v ? "border-erva text-tinta" : "border-transparent text-suave hover:text-tinta"}`}>
            {o.r}
          </button>
        ))}
      </div>

      {aba === "publicacao" ? (
        <AbaPublicacao capa={capa} podeEditar={podeEditar} aoMudar={recarregarCapa} />
      ) : aba === "pedidos" ? (
        <PedidosDoCatalogo idCatalogo={idCatalogo} podeEditar={podeEditar} />
      ) : aba === "idiomas" ? (
        <TraducoesDoCatalogo idCatalogo={idCatalogo} podeEditar={podeEditar} />
      ) : aba === "previa" ? (
        <AbaPrevia capa={capa} />
      ) : aba === "arquivo" ? (
        <AbaArquivo capa={capa} podeEditar={podeEditar} aoMudar={recarregarCapa} />
      ) : (
        <AbaCardapio idCatalogo={idCatalogo} podeEditar={podeEditar} vivo={capa.cardapio_vivo}
                     aoIdiomas={() => setAba("idiomas")} />
      )}
    </div>
  );
}
