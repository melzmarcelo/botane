"use client";

/**
 * Portal de Clientes → Catálogos → Atenção × Vendas.
 *
 * 🔑 **Pedido do dono (14/10/2026)**: a atenção que cada prato recebe no Cardápio Vivo,
 * cruzada com o que o PDV vendeu e com a margem da ficha — e a sugestão do que fazer.
 * Filtros numa linha só: período, salão, dia da semana e faixa de horário.
 * ⚠️ Os números por prato usam só as sessões ENGAJADAS; a tela diz o que cada um quer dizer.
 */

import { useCallback, useEffect, useState } from "react";
import CabecalhoTela from "@/components/cabecalho-tela";
import { Aviso, Carregando } from "@/components/ui";
import { AtencaoService, CardapioVivoService, type PainelAtencao } from "@/lib/cardapio-vivo";
import Indicadores from "./indicadores";
import Mapa from "./mapa";
import TabelaItens from "./tabela-itens";

const DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
const iso = (d: Date) => d.toISOString().slice(0, 10);

export default function PaginaAtencao() {
  const hoje = new Date();
  const [de, setDe] = useState(iso(new Date(hoje.getTime() - 29 * 86400_000)));
  const [ate, setAte] = useState(iso(hoje));
  const [salao, setSalao] = useState<number | null>(null);
  const [dias, setDias] = useState<number[]>([]);
  const [horaDe, setHoraDe] = useState("");
  const [horaAte, setHoraAte] = useState("");
  const [saloes, setSaloes] = useState<[number, string][]>([]);
  const [idCatalogo, setIdCatalogo] = useState<number | null>(null);
  const [dados, setDados] = useState<PainelAtencao | null>(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  useEffect(() => {
    CardapioVivoService.config().then((r) => setIdCatalogo(r.config.id_catalogo)).catch(() => {});
    // Os salões saem das mesas; sem permissão de salão, o filtro simplesmente não aparece.
    CardapioVivoService.mesas()
      .then((r) => setSaloes([...new Map(r.mesas.map((m) => [m.id_salao, m.salao])).entries()]))
      .catch(() => setSaloes([]));
  }, []);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      setDados(await AtencaoService.painel({ de, ate, id_salao: salao, dias,
                                              hora_de: horaDe || undefined, hora_ate: horaAte || undefined }));
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar o painel");
    } finally {
      setCarregando(false);
    }
  }, [de, ate, salao, dias, horaDe, horaAte]);

  useEffect(() => { void carregar(); }, [carregar]);

  return (
    <div className="flex flex-col gap-5">
      <CabecalhoTela
        caminho="Portal de Clientes · Catálogos"
        titulo="Atenção × Vendas"
        explica="Quanto cada prato do Cardápio Vivo prende a atenção de quem está na mesa, quanto o PDV vendeu dele e quanto ele deixa — com a sugestão do que fazer."
      />

      <div className="flex flex-wrap items-end gap-3 text-[14px]" role="group" aria-label="Filtros">
        <label className="flex flex-col gap-1"><span className="text-[12.5px] text-suave">De</span>
          <input type="date" className="campo mono !w-auto" value={de} onChange={(e) => setDe(e.target.value)} /></label>
        <label className="flex flex-col gap-1"><span className="text-[12.5px] text-suave">Até</span>
          <input type="date" className="campo mono !w-auto" value={ate} onChange={(e) => setAte(e.target.value)} /></label>
        {saloes.length > 0 && (
          <label className="flex flex-col gap-1"><span className="text-[12.5px] text-suave">Salão</span>
            <select className="campo !w-auto" value={salao ?? ""} onChange={(e) => setSalao(e.target.value ? Number(e.target.value) : null)}>
              <option value="">todos</option>
              {saloes.map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}
            </select></label>
        )}
        <div className="flex flex-col gap-1">
          <span className="text-[12.5px] text-suave">Dias da semana</span>
          <div className="flex gap-1">
            {DIAS.map((n, i) => {
              const d = i + 1, on = dias.includes(d);
              return (
                <button key={d} type="button" aria-pressed={on}
                        onClick={() => setDias((x) => (on ? x.filter((y) => y !== d) : [...x, d].sort()))}
                        className={`rounded-full border px-2.5 py-1 text-[12.5px] ${on ? "border-[var(--color-erva)] bg-[var(--color-erva)] text-white" : "border-linha"}`}>
                  {n}
                </button>
              );
            })}
          </div>
        </div>
        <label className="flex flex-col gap-1"><span className="text-[12.5px] text-suave">Das</span>
          <input type="time" className="campo mono !w-auto" value={horaDe} onChange={(e) => setHoraDe(e.target.value)} /></label>
        <label className="flex flex-col gap-1"><span className="text-[12.5px] text-suave">Às</span>
          <input type="time" className="campo mono !w-auto" value={horaAte} onChange={(e) => setHoraAte(e.target.value)} /></label>
        {carregando && <span className="pb-2 text-[13px] text-suave">atualizando…</span>}
      </div>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {(horaDe === "") !== (horaAte === "") && <Aviso tipo="info">Informe as duas pontas do horário.</Aviso>}
      {!dados ? (!erro && <Carregando />) : (
        <>
          {dados.avisos.map((a) => <Aviso key={a} tipo="info">{a}</Aviso>)}
          {dados.bruto_desde && de < dados.bruto_desde && (
            <Aviso tipo="info">Os eventos guardados começam em {dados.bruto_desde.split("-").reverse().join("/")} — antes disso não há dado para este painel.</Aviso>
          )}
          <Indicadores p={dados} />
          <TabelaItens itens={dados.itens} idCatalogo={idCatalogo} />
          <Mapa mapa={dados.mapa} />
        </>
      )}
    </div>
  );
}
