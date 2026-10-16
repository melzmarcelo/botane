"use client";

/**
 * A janela de UM Cardápio Vivo: o nome no link, se é o da mesa e como ele se comporta.
 *
 * 🔑 **Vários Cardápios Vivos por loja** (117, pedido do dono, 15/10/2026: *"no Botané vai
 * ter um que é o da cafeteria, e ela pode configurar outro que é destinado ao Catering"*).
 * O PRINCIPAL é o que o QR da mesa abre; os outros abrem pelo link de cada um.
 * ⚠️ A aparência (cores, fonte, logo) NÃO está aqui: é da casa, uma só para o site inteiro
 * (decisão do dono). Mora na tela do Cardápio Vivo.
 * Serve à tela do Cardápio Vivo e à aba Publicação do catálogo — uma janela só, para as
 * duas não divergirem.
 */

import { useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Modal } from "@/components/ui";
import { CardapioVivoService, type RespostaConfig, type VivoCardapio } from "@/lib/cardapio-vivo";

type Props = {
  idCatalogo: number;
  nomeCatalogo: string;
  /** O Cardápio Vivo gravado; nulo = ligando agora. */
  atual: VivoCardapio | null;
  /** Se a loja já tem outro principal — o primeiro nasce principal sozinho. */
  temOutros: boolean;
  aoFechar: () => void;
  aoGravar: (r: RespostaConfig) => void;
};

export default function JanelaCardapioVivo({ idCatalogo, nomeCatalogo, atual, temOutros, aoFechar, aoGravar }: Props) {
  const aviso = useAviso();
  const [v, setV] = useState({
    slug: atual?.slug ?? "",
    principal: atual?.principal ?? !temOutros,
    modo: atual?.modo ?? "VITRINE",
    exige_confirmacao: atual?.exige_confirmacao ?? true,
    pedido_hora_de: atual?.pedido_hora_de ?? "",
    pedido_hora_ate: atual?.pedido_hora_ate ?? "",
    chamar_garcom: atual?.chamar_garcom ?? false,
    selecao: atual?.selecao ?? true,
    aberturas: atual?.aberturas ?? "AUTOMATICA",
  });
  // 🔑 **Três escolhas, duas colunas** (119): "só consulta" é a vitrine com `selecao` falso.
  // ⚠️ No PEDIDO a seleção volta a valer — é o carrinho, e é o que sobra fora do horário.
  const escolha = v.modo === "PEDIDO" ? "PEDIDO" : v.selecao ? "VITRINE" : "CONSULTA";
  const escolher = (e: string) =>
    mudar(e === "PEDIDO" ? { modo: "PEDIDO", selecao: true }
                         : { modo: "VITRINE", selecao: e === "VITRINE" });
  const [gravando, setGravando] = useState(false);
  const mudar = (m: Partial<typeof v>) => setV((x) => ({ ...x, ...m }));

  async function gravar() {
    setGravando(true);
    try {
      const r = await CardapioVivoService.salvarVivo(idCatalogo, {
        ...v,
        slug: v.slug.trim() || null,
        pedido_hora_de: v.pedido_hora_de || null,
        pedido_hora_ate: v.pedido_hora_ate || null,
      });
      aoGravar(r);
      aviso.sucesso(r.message ?? "Cardápio Vivo gravado.");
      aoFechar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar.");
    } finally {
      setGravando(false);
    }
  }

  return (
    <Modal
      titulo={`Cardápio Vivo — ${nomeCatalogo}`}
      descricao="O cardápio no celular do cliente, prato a prato. A aparência é a da casa, igual para todos."
      aoFechar={aoFechar}
      largura="620px"
      rodape={
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-secundario" onClick={aoFechar}>Cancelar</button>
          <button type="button" className="btn btn-primario" aria-busy={gravando} disabled={gravando}
                  onClick={() => void gravar()}>
            {gravando ? "Gravando…" : atual ? "Gravar" : "Ligar"}
          </button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1" id="vivo-principal" checked={v.principal}
                 disabled={!temOutros}
                 onChange={(e) => mudar({ principal: e.target.checked })} />
          <span className="text-[14px]">
            Principal — é o que o QR code da mesa abre
            <span className="block text-[13px] text-suave">
              {temOutros
                ? "Um por loja: marcar este desmarca o outro."
                : "O primeiro Cardápio Vivo da loja é o principal."}
            </span>
          </span>
        </label>
        <Campo rotulo="Nome no link" opcional
               dica="Para abrir sem mesa (o catering, por exemplo). Em branco, sai do nome do catálogo.">
          <input className="campo mono" id="vivo-slug" maxLength={40} placeholder="catering"
                 value={v.slug} onChange={(e) => mudar({ slug: e.target.value.toLowerCase() })} />
        </Campo>
        <Campo rotulo="Modo na mesa" dica="Sem mesa (pelo link), o pedido não vale: fica a vitrine — ou só consulta, se escolhida.">
          <select className="campo" id="vivo-modo" value={escolha}
                  onChange={(e) => escolher(e.target.value)}>
            <option value="CONSULTA">Só consulta — o cardápio, sem “minha seleção”</option>
            <option value="VITRINE">Vitrine — com “minha seleção” para mostrar ao garçom</option>
            <option value="PEDIDO">Pedido — carrinho que vai ao painel</option>
          </select>
        </Campo>
        {v.modo === "PEDIDO" && (
          <div className="flex flex-col gap-2 rounded-lg border border-linha p-3 text-[14px]">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={v.exige_confirmacao}
                     onChange={(e) => mudar({ exige_confirmacao: e.target.checked })} />
              A equipe confirma o pedido antes de ir para a cozinha
            </label>
            <div className="flex flex-wrap items-center gap-2">
              Aceita pedido das
              <input type="time" className="campo mono !w-auto" value={v.pedido_hora_de.slice(0, 5)}
                     onChange={(e) => mudar({ pedido_hora_de: e.target.value })} />
              às
              <input type="time" className="campo mono !w-auto" value={v.pedido_hora_ate.slice(0, 5)}
                     onChange={(e) => mudar({ pedido_hora_ate: e.target.value })} />
              <span className="text-[13px] text-suave">vazio = o dia todo</span>
            </div>
          </div>
        )}
        {/* 🔑 121 (pedido do dono: "isto poderia ser configurado como vai aparecer"). */}
        <Campo rotulo="Aberturas de seção" dica="A tela com o nome e a descrição da seção, antes dos pratos dela. Cada seção também pode desligar a sua.">
          <select className="campo" id="vivo-aberturas" value={v.aberturas}
                  onChange={(e) => mudar({ aberturas: e.target.value as VivoCardapio["aberturas"] })}>
            <option value="AUTOMATICA">Automática — toda seção com foto ou vídeo abre</option>
            <option value="SO_VIDEO">Só as seções com vídeo</option>
            <option value="NUNCA">Nenhuma — direto aos pratos</option>
          </select>
        </Campo>
        <label className="flex items-center gap-2 text-[14px]">
          <input type="checkbox" checked={v.chamar_garcom} onChange={(e) => mudar({ chamar_garcom: e.target.checked })} />
          Botões “chamar o garçom” e “pedir a conta” (só na mesa)
        </label>
      </div>
    </Modal>
  );
}
