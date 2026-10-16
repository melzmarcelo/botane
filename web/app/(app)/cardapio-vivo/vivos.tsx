"use client";

/**
 * Os Cardápios Vivos da loja (117): o principal (o da mesa) e os outros, cada um com o link.
 *
 * 🔑 Pedido do dono (15/10/2026): *"hoje podemos ter somente 1 cardápio vivo, poderíamos ter
 * mais de um — a cafeteria e o Catering."* A mesa abre o PRINCIPAL; os outros, pelo link.
 */

import Link from "next/link";
import { useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import JanelaCardapioVivo from "@/components/janela-cardapio-vivo";
import { Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import { CardapioVivoService, type RespostaConfig, type VivoCardapio } from "@/lib/cardapio-vivo";

type Props = { dados: RespostaConfig; podeEditar: boolean; aoMudar: (r: RespostaConfig) => void };

export default function Vivos({ dados, podeEditar, aoMudar }: Props) {
  const aviso = useAviso();
  const [abrindo, setAbrindo] = useState<{ id: number; nome: string; atual: VivoCardapio | null } | null>(null);
  const [tirando, setTirando] = useState<VivoCardapio | null>(null);
  const livres = dados.catalogos.filter((c) => !dados.vivos.some((v) => v.id_catalogo === c.id));

  async function tirar() {
    if (!tirando) return;
    try {
      const r = await CardapioVivoService.removerVivo(tirando.id_catalogo);
      aoMudar(r);
      aviso.sucesso(r.message ?? "Removido.");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível tirar.");
    } finally {
      setTirando(null);
    }
  }

  async function copiar(link: string) {
    try {
      await navigator.clipboard.writeText(link);
      aviso.sucesso("Link copiado.");
    } catch {
      aviso.erro("Não deu para copiar — selecione o link e copie.");
    }
  }

  return (
    <Cartao titulo="Os Cardápios Vivos"
            descricao="O principal é o que o QR code da mesa abre. Os outros (o catering, por exemplo) abrem pelo link de cada um.">
      <div className="flex flex-col gap-3">
        {!dados.vivos.length ? (
          <Vazio>Nenhum ainda. Escolha um catálogo de produtos abaixo para ligar o primeiro — ele vira o da mesa.</Vazio>
        ) : (
          <ul className="flex flex-col gap-px bg-linha" aria-label="cardápios vivos">
            {dados.vivos.map((v) => (
              <li key={v.id_catalogo} className="flex flex-wrap items-center gap-x-3 gap-y-1 bg-superficie py-3"
                  data-vivo={v.slug}>
                <Link href={`/catalogos/${v.id_catalogo}?aba=publicacao`} className="link-registro font-semibold">
                  {v.nome}
                </Link>
                {v.principal && <Etiqueta cor="erva">principal · mesa</Etiqueta>}
                {v.situacao !== "ATIVO" && <Etiqueta cor="alerta">{v.situacao.toLowerCase()} — não abre</Etiqueta>}
                <span className="text-[13px] text-suave">{v.modo === "PEDIDO" ? "pedido na mesa" : v.selecao ? "vitrine" : "só consulta"}</span>
                <span className="basis-full mono text-[12.5px] text-suave break-all">
                  {v.link}{" "}
                  <button type="button" className="link-acao ml-1" onClick={() => void copiar(v.link)}>copiar</button>
                </span>
                {podeEditar && (
                  <span className="basis-full flex gap-2">
                    <button type="button" className="link-acao"
                            onClick={() => setAbrindo({ id: v.id_catalogo, nome: v.nome, atual: v })}>configurar</button>
                    <button type="button" className="link-acao link-acao-erro" onClick={() => setTirando(v)}>deixar de ser</button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        {podeEditar && livres.length > 0 && (
          <label className="flex flex-wrap items-center gap-2 text-[14px]">
            Ligar outro catálogo:
            <span className="block w-[260px]">
              <select className="campo" id="vivo-novo" value=""
                      onChange={(e) => {
                        const c = livres.find((x) => x.id === Number(e.target.value));
                        if (c) setAbrindo({ id: c.id, nome: c.nome, atual: null });
                      }}>
                <option value="">— escolha —</option>
                {livres.map((c) => (
                  <option key={c.id} value={c.id}>{c.nome}{c.situacao !== "ATIVO" ? ` (${c.situacao.toLowerCase()})` : ""}</option>
                ))}
              </select>
            </span>
          </label>
        )}
      </div>
      {abrindo && (
        <JanelaCardapioVivo idCatalogo={abrindo.id} nomeCatalogo={abrindo.nome} atual={abrindo.atual}
                            temOutros={dados.vivos.some((v) => v.id_catalogo !== abrindo.id)}
                            aoFechar={() => setAbrindo(null)} aoGravar={aoMudar} />
      )}
      {tirando && (
        <Confirmacao titulo={`“${tirando.nome}” deixa de ser Cardápio Vivo?`} rotuloConfirmar="Deixar de ser" perigo
                     aoConfirmar={() => void tirar()} aoCancelar={() => setTirando(null)}>
          O catálogo continua; o link deixa de abrir.
          {tirando.principal && <> ⚠️ É o principal: a mesa fica sem cardápio até outro ser marcado.</>}
        </Confirmacao>
      )}
    </Cartao>
  );
}
