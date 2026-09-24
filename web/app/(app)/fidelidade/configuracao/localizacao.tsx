"use client";

import { useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo } from "@/components/ui";
import { definirLocal, type FidelidadeConfig } from "@/lib/fidelidade";

/**
 * A localização do check-in: o cliente só pontua perto da loja (migração 092).
 *
 * 🔑 **Pedido do dono (24/09/2026):** *"validar a localização ao ler o QR code e contar a
 * visita … configurável."* Liga/desliga e o raio são da REDE (salvos com o cartão); as
 * coordenadas são da LOJA ATUAL e gravam na hora, pelo botão.
 *
 * ⚠️ **"Usar minha localização atual" só serve a quem está NA CASA.** Gravado de
 * casa, o raio passaria a ser em volta da casa de quem configurou.
 */
export default function LocalizacaoDoCheckin({
  cfg,
  aoMudar,
  aoGravarLocal,
}: {
  cfg: FidelidadeConfig;
  aoMudar: (exige: boolean, raio: number) => void;
  aoGravarLocal: (c: FidelidadeConfig) => void;
}) {
  const aviso = useAviso();
  const [lat, setLat] = useState(cfg.local ? String(cfg.local.latitude) : "");
  const [lng, setLng] = useState(cfg.local ? String(cfg.local.longitude) : "");
  const [ocupado, setOcupado] = useState(false);

  async function gravar(latitude: number, longitude: number) {
    setOcupado(true);
    try {
      const r = await definirLocal(latitude, longitude);
      setLat(String(r.local?.latitude ?? latitude));
      setLng(String(r.local?.longitude ?? longitude));
      aoGravarLocal(r);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar a localização");
    } finally {
      setOcupado(false);
    }
  }

  function usarAtual() {
    if (!navigator.geolocation) {
      aviso.erro("Este navegador não informa a localização.");
      return;
    }
    setOcupado(true);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        if (p.coords.accuracy > 150) {
          aviso.erro(
            `A localização veio imprecisa (±${Math.round(p.coords.accuracy)} m). ` +
              "Tente pelo celular, com o GPS ligado, dentro da casa.",
          );
          setOcupado(false);
          return;
        }
        void gravar(p.coords.latitude, p.coords.longitude);
      },
      (e) => {
        setOcupado(false);
        aviso.erro(
          e.code === e.PERMISSION_DENIED
            ? "O navegador bloqueou a localização. Permita e tente de novo."
            : "Não foi possível obter a localização agora.",
        );
      },
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 },
    );
  }

  const manual = () => {
    const a = Number(lat.replace(",", "."));
    const b = Number(lng.replace(",", "."));
    if (!lat || !lng || !Number.isFinite(a) || !Number.isFinite(b)) {
      aviso.erro("Informe latitude e longitude em graus (ex.: -26.919 e -49.066).");
      return;
    }
    void gravar(a, b);
  };

  return (
    <div className="flex flex-col gap-3 border-t border-linha pt-4">
      <label className="flex items-start gap-3">
        <input type="checkbox" className="mt-1" checked={cfg.exige_local}
               onChange={(e) => aoMudar(e.target.checked, cfg.raio_m)} />
        <span className="text-[14px]">
          Check-in só com o cliente na casa (localização)
          <span className="block text-[13px] text-suave">
            O site pede a localização do celular e a visita só conta dentro do raio. Impede que
            quem fotografou o QR code faça check-in de casa. Não guardamos a posição do
            cliente, só a distância.
          </span>
        </span>
      </label>

      {cfg.exige_local && (
        <>
          <div className="grid gap-4 sm:grid-cols-[160px_1fr]">
            <Campo rotulo="Raio" dica="metros em volta da loja">
              <input className="campo mono" type="number" min={30} max={5000} step={10}
                     value={cfg.raio_m}
                     onChange={(e) => aoMudar(true, Number(e.target.value))} />
            </Campo>
            <p className="self-end pb-2 text-[13px] text-suave">
              Dentro de prédio o celular erra de 20 a 100 m — por isso 200 m é um bom começo.
              O servidor desconta a margem de erro que o próprio celular informa.
            </p>
          </div>

          {!cfg.local && (
            <Aviso tipo="erro">
              Esta loja ainda não tem localização: com a exigência ligada, o check-in será
              recusado aqui até ela ser gravada.
            </Aviso>
          )}

          <div className="flex flex-col gap-2">
            <span className="rotulo-campo">Localização desta loja</span>
            <div className="flex flex-wrap items-end gap-2">
              <button type="button" className="btn btn-primario" onClick={usarAtual}
                      aria-busy={ocupado} disabled={ocupado}>
                {ocupado ? "…" : "Usar minha localização atual"}
              </button>
              <span className="pb-2 text-[13px] text-suave">— estando dentro da casa — ou:</span>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <input className="campo mono w-[150px]" aria-label="latitude" placeholder="latitude"
                     value={lat} onChange={(e) => setLat(e.target.value)} />
              <input className="campo mono w-[150px]" aria-label="longitude" placeholder="longitude"
                     value={lng} onChange={(e) => setLng(e.target.value)} />
              <button type="button" className="btn btn-secundario" onClick={manual}
                      disabled={ocupado}>
                Gravar
              </button>
              {cfg.local && (
                <a className="link-acao pb-2 text-[13px]" target="_blank" rel="noopener"
                   href={`https://www.google.com/maps?q=${cfg.local.latitude},${cfg.local.longitude}`}>
                  conferir no mapa
                </a>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
