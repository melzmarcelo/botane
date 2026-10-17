"use client";

/**
 * Portal de Clientes → Catálogos → Anúncios (Cardápio Vivo, migração 121, fase 1).
 *
 * 🔑 Pedido do dono (16/10/2026): anúncios no meio do cardápio — da casa ou de outra marca —, com
 * período, dias e links; "nada pesado, algo orgânico"; métricas e um relatório para apresentar ao
 * parceiro. Aqui: as regras de exibição da casa, a lista com a atenção dos últimos 30 dias e o
 * caminho para o relatório de cada um.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import ExplicaTela from "@/components/explica-tela";
import { Aviso, Cartao, Carregando, Etiqueta, Vazio } from "@/components/ui";
import { AnunciosService, porcento, type Anuncio, type RegrasAnuncio, type SituacaoAnuncio } from "@/lib/anuncios";
import { CardapioVivoService } from "@/lib/cardapio-vivo";
import * as cat from "@/lib/catalogos";
import { useSessao } from "@/lib/sessao";
import JanelaAnuncio, { type Opcoes } from "./janela-anuncio";

const SITUACAO: Record<SituacaoAnuncio, [string, "erva" | "alerta" | "neutro"]> = {
  NO_AR: ["no ar", "erva"], AGENDADO: ["agendado", "neutro"], ENCERRADO: ["encerrado", "neutro"], DESLIGADO: ["desligado", "alerta"],
  COM_PROBLEMA: ["com problema", "alerta"],
};

export default function PaginaAnuncios() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const editar = pode("catalogos.editar");
  const [dados, setDados] = useState<{ anuncios: Anuncio[]; regras: RegrasAnuncio } | null>(null);
  const [regras, setRegras] = useState<RegrasAnuncio | null>(null);
  const [opcoes, setOpcoes] = useState<Opcoes>({ vivos: [], catalogos: [], pratos: [] });
  const [abrindo, setAbrindo] = useState<Anuncio | null | "novo">(null);
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    try {
      const r = await AnunciosService.listar();
      setDados(r);
      setRegras((x) => x ?? r.regras);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar os anúncios");
    }
  }, []);

  useEffect(() => {
    void carregar();
    // As escolhas da janela: os Cardápios Vivos, os catálogos da casa e os pratos de cada vivo.
    void (async () => {
      try {
        const [cfg, lista] = await Promise.all([CardapioVivoService.config(), cat.listar()]);
        const pratos = (await Promise.all(cfg.vivos.map(async (v) => {
          const k = await cat.conteudo(v.id_catalogo);
          return k.categorias.flatMap((c) => [...c.itens, ...c.subcategorias.flatMap((s) => s.itens)])
            .map((i) => ({ id: i.id, nome: i.nome_catalogo || i.produto, cardapio: v.nome }));
        }))).flat();
        setOpcoes({ vivos: cfg.vivos.map((v) => ({ id_catalogo: v.id_catalogo, nome: v.nome })),
                    catalogos: lista.map((c) => ({ id: c.id, nome: c.nome })), pratos });
      } catch {
        /* sem as escolhas, a janela abre com as listas vazias */
      }
    })();
  }, [carregar]);

  async function gravarRegras() {
    if (!regras) return;
    try {
      const r = await AnunciosService.regras(regras);
      setRegras(r);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar as regras");
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados || !regras) return <Carregando />;
  const numero = (campo: keyof RegrasAnuncio, rotulo: string, min: number) => (
    <label className="flex flex-col gap-1 text-[13.5px]">
      <span className="text-suave">{rotulo}</span>
      <input type="number" min={min} max={50} className="campo mono !w-24" disabled={!editar} value={regras[campo]}
             id={`regra-${campo}`} onChange={(e) => setRegras({ ...regras, [campo]: Number(e.target.value) })} />
    </label>
  );

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Portal de Clientes · Catálogos</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Anúncios</h1>
        <ExplicaTela>
          Anúncios no meio do Cardápio Vivo: um catálogo ou prato da casa (“Da casa”) ou outra marca
          (“Patrocinado”). Cada um tem o seu período; o ritmo é o da casa, abaixo — para não pesar para quem
          está escolhendo o prato. O relatório de cada anúncio mostra quantas pessoas viram e tocaram.
        </ExplicaTela>
      </header>

      <Cartao titulo="O ritmo dos anúncios"
              descricao="Vale para todos. Com filtro de restrição ligado, nenhum anúncio aparece; e nunca o mesmo duas vezes na mesma visita."
              acao={editar ? <button type="button" className="btn btn-secundario" id="regras-gravar" onClick={() => void gravarRegras()}>Gravar</button> : undefined}>
        <div className="flex flex-wrap gap-5">
          {numero("anuncio_depois_de", "O 1º depois do prato nº", 1)}
          {numero("anuncio_intervalo", "Pratos entre um e outro", 2)}
          {numero("anuncio_maximo", "No máximo, por visita", 0)}
          {numero("anuncio_maximo_mesa", "No máximo, na mesa", 0)}
        </div>
      </Cartao>

      <Cartao titulo="Os anúncios" descricao="A atenção é dos últimos 30 dias. “Pularam” = passou em menos de 1,5 s, sem parar."
              acao={editar ? <button type="button" className="btn btn-primario" id="anuncio-novo" onClick={() => setAbrindo("novo")}>+ anúncio</button> : undefined}>
        {dados.anuncios.length === 0 ? (
          <Vazio>Nenhum anúncio ainda. Comece por um da casa — o catálogo de uma data especial, por exemplo.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela w-full">
              <thead>
                <tr><th>Anúncio</th><th>Situação</th><th className="text-right">Pessoas</th><th className="text-right">Pularam</th>
                    <th className="text-right">Tocaram</th><th /></tr>
              </thead>
              <tbody>
                {dados.anuncios.map((a) => {
                  const [rotulo, cor] = SITUACAO[a.situacao ?? "NO_AR"];
                  return (
                    <tr key={a.id} data-anuncio-linha={a.id}>
                      <td>
                        <button type="button" className="link-acao text-left font-semibold" onClick={() => setAbrindo(a)}>{a.nome}</button>
                        <span className="block text-[12.5px] text-suave">
                          {a.origem === "EXTERNO" ? `Patrocinado · ${a.anunciante ?? ""}` : "Da casa"}
                          {a.inicio || a.fim ? ` · ${a.inicio ?? "…"} a ${a.fim ?? "…"}` : ""}
                        </span>
                        {(a.avisos ?? []).map((t) => (
                          <span key={t} className="block text-[12.5px] text-alerta" data-anuncio-aviso>⚠ {t}</span>
                        ))}
                      </td>
                      <td>
                        <Etiqueta cor={cor}>{rotulo}</Etiqueta>
                        {a.fora_do_horario_agora && <span className="block text-[12px] text-suave">fora do horário agora</span>}
                      </td>
                      <td className="mono text-right">{a.sessoes ?? 0}</td>
                      <td className="mono text-right">{porcento(a.aparicoes ? (a.pulados ?? 0) / a.aparicoes : null)}</td>
                      <td className="mono text-right">{porcento(a.sessoes ? (a.sessoes_tocaram ?? 0) / a.sessoes : null)}</td>
                      <td className="text-right">
                        <Link className="link-acao" href={`/cardapio-vivo/anuncios/${a.id}/relatorio`}>relatório</Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>

      {abrindo && (
        <JanelaAnuncio atual={abrindo === "novo" ? null : abrindo} opcoes={opcoes} podeEditar={editar}
                       aoFechar={() => setAbrindo(null)} aoMudar={carregar} />
      )}
    </div>
  );
}
