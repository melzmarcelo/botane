"use client";

import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Cartao } from "@/components/ui";
import {
  impressoras as pedirImpressoras, lembrarModo, obterConfig, salvarConfig,
  type ConfigEtiqueta, type ImpressoraDeEtiqueta,
} from "@/lib/etiquetas";

/**
 * O modelo da etiqueta desta loja: a impressora, o rolo e o que aparece.
 *
 * 🔑 **O PDF sai no tamanho do rolo, uma página por etiqueta**: com o driver da
 * impressora térmica no mesmo tamanho, cada página é uma etiqueta. A4 é a reserva
 * (folha de adesivos 3×7 de 60×40).
 * 🔑 **Impressora e rolo vêm de um catálogo do servidor** (22/10/2026, pedido do dono:
 * *"podemos colocar qual impressora vamos utilizar com seleção … e a seleção do tipo de
 * rolo também, isto facilita para futuras impressoras"*): impressora nova não mexe aqui.
 */
const CAMPOS: { k: keyof ConfigEtiqueta; r: string }[] = [
  { k: "mostrar_qr", r: "QR code (abre a etiqueta no celular)" },
  { k: "mostrar_lote", r: "Lote" },
  { k: "mostrar_quantidade", r: "Quantidade" },
  { k: "mostrar_alergenos", r: "Alergênicos (da ficha técnica)" },
];

export default function ModeloDaEtiqueta({ podeEditar }: { podeEditar: boolean }) {
  const aviso = useAviso();
  const [cfg, setCfg] = useState<ConfigEtiqueta | null>(null);
  const [catalogo, setCatalogo] = useState<ImpressoraDeEtiqueta[]>([]);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    Promise.all([obterConfig(), pedirImpressoras()])
      .then(([c, i]) => { setCfg(c); setCatalogo(i); })
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
  }, []);

  const impressora = catalogo.find((i) => i.codigo === cfg?.impressora);
  // Na PDF o "rolo" é o `tamanho` de sempre; nas outras, o `rolo`.
  const codigoRolo = cfg ? (cfg.impressora === "PDF" ? cfg.tamanho : cfg.rolo) : null;
  const rolo = impressora?.rolos.find((r) => r.codigo === codigoRolo);

  function trocarImpressora(codigo: ConfigEtiqueta["impressora"]) {
    if (!cfg) return;
    const nova = catalogo.find((i) => i.codigo === codigo);
    setCfg(codigo === "PDF"
      ? { ...cfg, impressora: codigo, rolo: null, comprimento_mm: null }
      : { ...cfg, impressora: codigo, rolo: nova?.rolos[0]?.codigo ?? null,
          comprimento_mm: nova?.rolos[0]?.continuo ? (cfg.comprimento_mm ?? 40) : null });
  }

  function trocarRolo(codigo: string) {
    if (!cfg) return;
    if (cfg.impressora === "PDF") {
      setCfg({ ...cfg, tamanho: codigo as ConfigEtiqueta["tamanho"] });
      return;
    }
    const novo = impressora?.rolos.find((r) => r.codigo === codigo);
    setCfg({ ...cfg, rolo: codigo, comprimento_mm: novo?.continuo ? (cfg.comprimento_mm ?? 40) : null });
  }

  async function salvar() {
    if (!cfg) return;
    setOcupado(true);
    try {
      const r = await salvarConfig(cfg);
      setCfg(r);
      lembrarModo(!!r.direta);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setOcupado(false);
    }
  }

  const medida = rolo
    ? `${rolo.largura} × ${rolo.continuo ? (cfg?.comprimento_mm ?? 40) : rolo.altura} mm`
    : "";

  return (
    <Cartao titulo="Modelo da etiqueta" descricao="Vale para esta loja — cada casa tem a sua impressora.">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!cfg || !catalogo.length ? (!erro && <Carregando />) : (
        <fieldset disabled={!podeEditar} className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo rotulo="Impressora">
              <select id="etiqueta-impressora" className="campo" value={cfg.impressora}
                      onChange={(e) => trocarImpressora(e.target.value as ConfigEtiqueta["impressora"])}>
                {catalogo.map((i) => <option key={i.codigo} value={i.codigo}>{i.nome}</option>)}
              </select>
            </Campo>
            <Campo rotulo={cfg.impressora === "PDF" ? "Tamanho" : "Rolo"}
                   dica={rolo && cfg.impressora !== "PDF" && rolo.codigo !== "A4" ? `cada etiqueta: ${medida}` : undefined}>
              <select id="etiqueta-rolo" className="campo" value={codigoRolo ?? ""}
                      onChange={(e) => trocarRolo(e.target.value)}>
                {impressora?.rolos.map((r) => <option key={r.codigo} value={r.codigo}>{r.nome}</option>)}
              </select>
            </Campo>
            {rolo?.continuo && cfg.impressora !== "PDF" && (
              <Campo rotulo="Comprimento de cada etiqueta (mm)" dica="o rolo contínuo corta no tamanho que o sistema mandar">
                <input id="etiqueta-comprimento" className="campo" type="number" min={20} max={200}
                       value={cfg.comprimento_mm ?? 40}
                       onChange={(e) => setCfg({ ...cfg, comprimento_mm: Number(e.target.value) || null })} />
              </Campo>
            )}
            <Campo rotulo="Texto no rodapé" opcional dica="ex.: nome da casa, telefone">
              <input className="campo" maxLength={80} value={cfg.texto_extra ?? ""}
                     onChange={(e) => setCfg({ ...cfg, texto_extra: e.target.value })} />
            </Campo>
          </div>
          {impressora?.direta && (
            <Aviso tipo="info">
              <span id="etiqueta-direta">
                <strong>Imprime direto:</strong> o botão Imprimir manda a etiqueta para a impressora,
                sem abrir o PDF. Para não aparecer nem a janela de impressão, no computador da
                bancada: deixe a impressora como <strong>padrão do Windows</strong>, com o papel do
                driver no rolo escolhido ({medida}), e abra o sistema pelo atalho do Chrome com{" "}
                <code>--kiosk-printing</code>. O passo a passo está no manual (Etiquetas).
              </span>
            </Aviso>
          )}
          <div className="grid gap-2 sm:grid-cols-2">
            {CAMPOS.map((c) => (
              <label key={c.k} className="flex items-center gap-2 text-[14px]">
                <input type="checkbox" checked={!!cfg[c.k]}
                       onChange={(e) => setCfg({ ...cfg, [c.k]: e.target.checked })} />
                {c.r}
              </label>
            ))}
          </div>
          <p className="text-[13px] text-suave">
            Sempre saem: produto, o que aconteceu e quando, conservação, validade e responsável.
            Na impressora térmica, configure o papel no mesmo tamanho e a escala em 100%.
          </p>
          {podeEditar && (
            <div className="flex justify-end">
              <button className="btn btn-primario" aria-busy={ocupado} onClick={() => void salvar()}>
                {ocupado ? "…" : "Salvar modelo"}
              </button>
            </div>
          )}
        </fieldset>
      )}
    </Cartao>
  );
}
