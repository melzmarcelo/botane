"use client";

/**
 * O cartão do que é da CASA: a aparência (cores, fonte, logo), a tela de entrada, esconder
 * esgotado e a retenção.
 *
 * 🔑 **Desde a 117, qual cardápio, o modo, o horário do pedido e o garçom são de CADA
 * Cardápio Vivo** (cartão "Os Cardápios Vivos"). A aparência ficou aqui, uma só: decisão
 * do dono — um layout só para o site inteiro.
 */

import { useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Cartao } from "@/components/ui";
import { CardapioVivoService, type ConfigCardapio, type RespostaConfig } from "@/lib/cardapio-vivo";
import { urlArquivo } from "@/lib/api";

// ⚠️ "a do site" é a FRAUNCES (o protótipo): a Newsreader levava esse rótulo sem ser (118).
const NOMES_FONTE: Record<string, string> = {
  FRAUNCES: "Fraunces (a do site)", NEWSREADER: "Newsreader", PLAYFAIR: "Playfair Display", LORA: "Lora",
  CORMORANT: "Cormorant Garamond",
};

type Props = { dados: RespostaConfig; podeEditar: boolean; aoMudar: (r: RespostaConfig) => void };

export default function Configuracao({ dados, podeEditar, aoMudar }: Props) {
  const aviso = useAviso();
  const [cfg, setCfg] = useState<ConfigCardapio>(dados.config);
  const [gravando, setGravando] = useState(false);
  const mudar = <K extends keyof ConfigCardapio>(k: K, v: ConfigCardapio[K]) => setCfg((c) => ({ ...c, [k]: v }));

  async function gravar() {
    setGravando(true);
    try {
      const { id_unidade: _u, logo_url: _l, id_catalogo: _c, ...corpo } = cfg;
      const r = await CardapioVivoService.salvarConfig(corpo);
      aoMudar(r);
      setCfg(r.config);
      aviso.sucesso(r.message ?? "Configuração gravada.");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar.");
    } finally {
      setGravando(false);
    }
  }

  async function logo(arquivo: File | null) {
    try {
      const r = arquivo ? await CardapioVivoService.enviarLogo(arquivo) : await CardapioVivoService.removerLogo();
      aoMudar(r);
      setCfg((c) => ({ ...c, logo_url: r.config.logo_url }));
      aviso.sucesso(r.message ?? "Logo atualizada.");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível enviar a logo.");
    }
  }

  const desligado = !podeEditar;
  return (
    <Cartao titulo="Aparência e opções da casa"
            descricao="Valem para o site da casa e para todos os Cardápios Vivos, na próxima vez que o cliente abrir — sem publicar nada.">
      <div className="grid gap-4 md:grid-cols-2">
        <label className="flex items-center gap-2 text-[14px]">
          <input type="checkbox" disabled={desligado} checked={cfg.esconder_esgotado}
                 onChange={(e) => mudar("esconder_esgotado", e.target.checked)} />
          Esconder os itens marcados como esgotados (desligado: aparecem marcados)
        </label>
        <Campo rotulo="Eventos guardados por (meses)" dica="LGPD: depois disso, só os totais por dia ficam.">
          <input className="campo mono" type="number" min={1} max={60} disabled={desligado}
                 value={cfg.retencao_meses} onChange={(e) => mudar("retencao_meses", Number(e.target.value))} />
        </Campo>
      </div>

      <h3 className="mt-6 text-[14px] font-bold">Tela de entrada</h3>
      <p className="text-[13px] text-suave">
        Antes do cardápio, a marca da loja e os botões ligados aqui. Sem nenhum ligado (ou sem o dado no
        cadastro da loja), o cliente cai direto no cardápio. O link e o Wi-Fi ficam em Administração ▸ Lojas.
      </p>
      <div className="mt-2 flex flex-wrap gap-6 text-[14px]">
        <label className="flex items-center gap-2">
          <input type="checkbox" disabled={desligado} checked={cfg.hub_avaliacao}
                 onChange={(e) => mudar("hub_avaliacao", e.target.checked)} />
          “Avaliar no Google”
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" disabled={desligado} checked={cfg.hub_wifi}
                 onChange={(e) => mudar("hub_wifi", e.target.checked)} />
          “Wi-Fi” (rede e senha, com botão de copiar)
        </label>
      </div>

      <h3 className="mt-6 text-[14px] font-bold">Identidade visual</h3>
      <div className="mt-2 grid gap-4 md:grid-cols-4">
        {(["cor_principal", "cor_fundo"] as const).map((k) => (
          <Campo key={k} rotulo={k === "cor_principal" ? "Cor principal" : "Cor de fundo"} opcional>
            <div className="flex items-center gap-2">
              <input type="color" disabled={desligado} value={cfg[k] ?? (k === "cor_principal" ? "#3c4a3e" : "#f3efe4")}
                     onChange={(e) => mudar(k, e.target.value)} className="h-9 w-12 cursor-pointer rounded" />
              {cfg[k] && !desligado && (
                <button type="button" className="link-acao text-[13px]" onClick={() => mudar(k, null)}>padrão</button>
              )}
            </div>
          </Campo>
        ))}
        <Campo rotulo="Fonte dos nomes">
          <select className="campo" disabled={desligado} value={cfg.fonte} onChange={(e) => mudar("fonte", e.target.value)}>
            {dados.opcoes.fontes.map((f) => <option key={f} value={f}>{NOMES_FONTE[f] ?? f}</option>)}
          </select>
        </Campo>
        <Campo rotulo="Logo da loja" dica="Sem ela, vale a da empresa.">
          <div className="flex items-center gap-2">
            {cfg.logo_url && <img src={urlArquivo(cfg.logo_url) ?? undefined} alt="" className="h-9 w-9 rounded-full object-contain" />}
            {!desligado && (
              <>
                <label className="btn btn-secundario relative cursor-pointer text-[13px]">
                  Enviar
                  <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only"
                         onChange={(e) => void logo(e.target.files?.[0] ?? null)} />
                </label>
                {cfg.logo_url && <button type="button" className="link-acao text-[13px]" onClick={() => void logo(null)}>tirar</button>}
              </>
            )}
          </div>
        </Campo>
      </div>

      {podeEditar && (
        <div className="mt-5 flex justify-end">
          <button className="btn btn-primario" onClick={() => void gravar()} disabled={gravando} aria-busy={gravando}>
            {gravando ? "Gravando…" : "Gravar"}
          </button>
        </div>
      )}
    </Cartao>
  );
}
