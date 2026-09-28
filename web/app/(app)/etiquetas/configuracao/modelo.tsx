"use client";

import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Cartao } from "@/components/ui";
import { obterConfig, salvarConfig, type ConfigEtiqueta } from "@/lib/etiquetas";

/**
 * O modelo da etiqueta desta loja: o tamanho do rolo e o que aparece.
 *
 * 🔑 **O PDF sai no tamanho do rolo, uma página por etiqueta**: com o driver da
 * impressora térmica no mesmo tamanho, cada página é uma etiqueta. A4 é a reserva
 * (folha de adesivos 3×7 de 60×40).
 */
const TAMANHOS: { v: ConfigEtiqueta["tamanho"]; r: string }[] = [
  { v: "60x40", r: "60 × 40 mm (recomendado)" },
  { v: "50x30", r: "50 × 30 mm" },
  { v: "40x40", r: "40 × 40 mm" },
  { v: "100x50", r: "100 × 50 mm" },
  { v: "A4", r: "Folha A4 (21 por folha)" },
];
const CAMPOS: { k: keyof ConfigEtiqueta; r: string }[] = [
  { k: "mostrar_qr", r: "QR code (abre a etiqueta no celular)" },
  { k: "mostrar_lote", r: "Lote" },
  { k: "mostrar_quantidade", r: "Quantidade" },
  { k: "mostrar_alergenos", r: "Alergênicos (da ficha técnica)" },
];

export default function ModeloDaEtiqueta({ podeEditar }: { podeEditar: boolean }) {
  const aviso = useAviso();
  const [cfg, setCfg] = useState<ConfigEtiqueta | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    obterConfig().then(setCfg).catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
  }, []);

  async function salvar() {
    if (!cfg) return;
    setOcupado(true);
    try {
      const r = await salvarConfig(cfg);
      setCfg(r);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Cartao titulo="Modelo da etiqueta" descricao="Vale para esta loja — cada casa tem a sua impressora.">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!cfg ? <Carregando /> : (
        <fieldset disabled={!podeEditar} className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo rotulo="Tamanho">
              <select className="campo" value={cfg.tamanho}
                      onChange={(e) => setCfg({ ...cfg, tamanho: e.target.value as ConfigEtiqueta["tamanho"] })}>
                {TAMANHOS.map((t) => <option key={t.v} value={t.v}>{t.r}</option>)}
              </select>
            </Campo>
            <Campo rotulo="Texto no rodapé" opcional dica="ex.: nome da casa, telefone">
              <input className="campo" maxLength={80} value={cfg.texto_extra ?? ""}
                     onChange={(e) => setCfg({ ...cfg, texto_extra: e.target.value })} />
            </Campo>
          </div>
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
