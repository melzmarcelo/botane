"use client";

/**
 * O cartão da configuração da loja: qual cardápio a mesa abre, o modo, as opções e a
 * identidade visual (cores, fonte, logo).
 *
 * ⚠️ O modo PEDIDO aparece desabilitado com "fase 2": quem vê a especificação procura a
 * opção, e escondê-la faria parecer esquecida. Quem recusa de verdade é o servidor.
 */

import { useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Cartao } from "@/components/ui";
import { CardapioVivoService, type ConfigCardapio, type RespostaConfig } from "@/lib/cardapio-vivo";
import { urlArquivo } from "@/lib/api";

const NOMES_FONTE: Record<string, string> = {
  NEWSREADER: "Newsreader (a do site)", PLAYFAIR: "Playfair Display", LORA: "Lora",
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
      const { id_unidade: _u, logo_url: _l, ...corpo } = cfg;
      const r = await CardapioVivoService.salvarConfig({
        ...corpo,
        pedido_hora_de: corpo.pedido_hora_de || null,
        pedido_hora_ate: corpo.pedido_hora_ate || null,
      });
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
    <Cartao titulo="Configuração da loja"
            descricao="Vale na próxima vez que o cliente abrir o cardápio — sem publicar nada.">
      <div className="grid gap-4 md:grid-cols-2">
        <Campo rotulo="Cardápio que a mesa abre" dica="Só catálogos de origem Produtos.">
          <select className="campo" disabled={desligado} value={cfg.id_catalogo ?? ""}
                  onChange={(e) => mudar("id_catalogo", e.target.value ? Number(e.target.value) : null)}>
            <option value="">— desligado —</option>
            {dados.catalogos.map((c) => (
              <option key={c.id} value={c.id}>{c.nome}{c.situacao !== "ATIVO" ? ` (${c.situacao.toLowerCase()})` : ""}</option>
            ))}
          </select>
        </Campo>
        <Campo rotulo="Modo">
          <select className="campo" disabled={desligado} value={cfg.modo}
                  onChange={(e) => mudar("modo", e.target.value as ConfigCardapio["modo"])}>
            {dados.opcoes.modos.map((m) => (
              <option key={m} value={m} disabled={!dados.opcoes.modos_liberados.includes(m)}>
                {m === "VITRINE" ? "Vitrine — só consulta, com “minha seleção”" : "Pedido — carrinho que vai ao painel"}
              </option>
            ))}
          </select>
        </Campo>
        {/* 🔑 As opções do PEDIDO (fase 2, 115). Valem também como padrão das exceções. */}
        {cfg.modo === "PEDIDO" && (
          <div className="flex flex-col gap-2 rounded-lg border border-linha p-3 text-[14px] md:col-span-2">
            <label className="flex items-center gap-2">
              <input type="checkbox" disabled={desligado} checked={cfg.exige_confirmacao}
                     onChange={(e) => mudar("exige_confirmacao", e.target.checked)} />
              A equipe confirma o pedido antes de ir para a cozinha (desligado: nasce confirmado)
            </label>
            <div className="flex flex-wrap items-center gap-2">
              Aceita pedido pela mesa das
              <input type="time" className="campo mono !w-auto" disabled={desligado} value={cfg.pedido_hora_de?.slice(0, 5) ?? ""}
                     onChange={(e) => mudar("pedido_hora_de", e.target.value || null)} />
              às
              <input type="time" className="campo mono !w-auto" disabled={desligado} value={cfg.pedido_hora_ate?.slice(0, 5) ?? ""}
                     onChange={(e) => mudar("pedido_hora_ate", e.target.value || null)} />
              <span className="text-[13px] text-suave">vazio = o dia todo; fora do horário, o cardápio vira vitrine com “pedidos com o garçom”</span>
            </div>
            <p className="text-[13px] text-suave">
              O pedido aparece no Painel de pedidos, coluna Mesas. Lançar no PDV continua com a casa; o pagamento, no caixa.
            </p>
          </div>
        )}
        <label className="flex items-center gap-2 text-[14px]">
          <input type="checkbox" disabled={desligado} checked={cfg.chamar_garcom}
                 onChange={(e) => mudar("chamar_garcom", e.target.checked)} />
          Botões “chamar o garçom” e “pedir a conta” (avisam no Painel de pedidos, com som)
        </label>
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
