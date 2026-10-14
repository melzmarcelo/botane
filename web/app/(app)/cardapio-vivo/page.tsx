"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ExplicaTela from "@/components/explica-tela";
import { Aviso, Carregando, Cartao } from "@/components/ui";
import { CardapioVivoService, type RespostaConfig } from "@/lib/cardapio-vivo";
import { useSessao } from "@/lib/sessao";
import AcessoMesas from "./acesso-mesas";
import Configuracao from "./configuracao";

/**
 * Portal de Clientes → Catálogos → Cardápio Vivo.
 *
 * 🔑 **Pedido do dono (14/10/2026)**: o cardápio da mesa como feed, e a atenção que cada
 * prato recebe. Estudo em `docs/cardapio-vivo-estudo.md`. Aqui mora o que é da LOJA (qual
 * cardápio, modo, identidade, retenção) e o acesso das mesas; o que é do prato (vídeo,
 * restrições, adicionais) fica no produto, e destaque/esgotado/horário no catálogo.
 */
export default function PaginaCardapioVivo() {
  const { pode } = useSessao();
  const [dados, setDados] = useState<RespostaConfig | null>(null);
  const [erro, setErro] = useState("");
  const [previa, setPrevia] = useState(false);

  useEffect(() => {
    CardapioVivoService.config().then(setDados)
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar o Cardápio Vivo"));
  }, []);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;
  const id = dados.config.id_catalogo;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Portal de Clientes · Catálogos</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Cardápio Vivo</h1>
        <ExplicaTela>
          O cardápio da mesa no celular do cliente: um prato por tela, com vídeo ou foto. Abre pelo
          QR code ou pela etiqueta NFC da mesa, sem app e sem login. Vídeo, restrições e adicionais
          ficam no cadastro do produto (aba Catálogo); destaque, esgotado e o horário das seções,
          no <Link href={id ? `/catalogos/${id}` : "/catalogos"} className="link-acao">catálogo</Link>.
        </ExplicaTela>
      </header>

      <Configuracao dados={dados} podeEditar={pode("catalogos.editar")} aoMudar={setDados} />

      {id && dados.sem_midia.length > 0 && (
        <Cartao titulo={`${dados.sem_midia.length} prato(s) publicado(s) sem foto e sem vídeo`}
                descricao="No feed, eles aparecem com a foto da seção — ou com a cor de fundo, se a seção também não tiver.">
          <ul className="columns-1 gap-6 text-[14px] sm:columns-2">
            {dados.sem_midia.map((i) => (
              <li key={i.id} className="break-inside-avoid py-0.5">
                <Link href={`/produtos/${i.id_produto}`} className="link-acao">{i.nome}</Link>
                <span className="text-suave"> · {i.categoria}</span>
              </li>
            ))}
          </ul>
        </Cartao>
      )}

      {id && (
        <Cartao titulo="Pré-visualização"
                descricao="O feed como o cliente vê — inclusive as seções fora do dia ou do horário, marcadas."
                acao={<button className="btn btn-secundario" onClick={() => setPrevia((v) => !v)}>
                  {previa ? "Fechar" : "Abrir"}</button>}>
          {previa ? (
            <div className="flex justify-center">
              <iframe src={`/c/previa/${id}`} title="Pré-visualização do cardápio"
                      className="h-[720px] w-[360px] rounded-[28px] border-[6px] border-[var(--color-linha)]" />
            </div>
          ) : null}
        </Cartao>
      )}

      {pode("reservas.configurar") && <AcessoMesas />}
    </div>
  );
}
