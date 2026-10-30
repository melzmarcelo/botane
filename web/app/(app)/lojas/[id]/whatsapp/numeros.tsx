"use client";

import { Cartao, Etiqueta } from "@/components/ui";
import type { NumeroDoWhatsapp, NumeroEmEdicao } from "@/lib/whatsapp";

import ConexaoDoNumero from "./conexao";

/**
 * Os números de WhatsApp da loja, cada um com a sua conexão com a Meta (146).
 *
 * 🔑 **Pedido do dono (30/10/2026):** *"foi realizado o cadastro somente do número; teria que
 * criar uma configuração completa como tem na aba WhatsApp da loja, onde permite enviar
 * mensagem automaticamente e receber os devidos retornos."* A lista saiu do cadastro da loja e
 * mora aqui: ★ principal (o "Entre em contato" do site), e a conexão opcional — número sem
 * conexão só serve para o cliente chamar.
 */
let sequencia = 0;
export const numeroNovo = (primeiro: boolean): NumeroEmEdicao => ({
  id: null, chave: `novo-${++sequencia}`, rotulo: primeiro ? "Atendimento" : "", numero: "",
  principal: primeiro, conectado: false, modo: "simulado", phone_number_id: "", waba_id: "",
  api_versao: "v21.0", token: "", app_secret: "", conta_do_principal: !primeiro,
});

export default function NumerosDoWhatsapp({
  lista,
  gravados,
  webhookUrl,
  aoTrocar,
  podeEditar,
}: {
  lista: NumeroEmEdicao[];
  gravados: NumeroDoWhatsapp[];
  webhookUrl: string;
  aoTrocar: (l: NumeroEmEdicao[]) => void;
  podeEditar: boolean;
}) {
  const troca = (i: number, n: NumeroEmEdicao) => aoTrocar(lista.map((x, j) => (j === i ? n : x)));
  const tornarPrincipal = (i: number) => aoTrocar(lista.map((n, j) => ({ ...n, principal: j === i })));
  function remover(i: number) {
    const resto = lista.filter((_, j) => j !== i);
    // Tirou o principal: o primeiro que sobrou assume (loja com número precisa de um).
    if (lista[i].principal && resto.length) resto[0] = { ...resto[0], principal: true };
    aoTrocar(resto);
  }
  const principal = lista.find((n) => n.principal) ?? null;

  return (
    <Cartao
      titulo="Números"
      descricao="Os números da loja. O ★ principal é o “Entre em contato” do site e, conectado à Meta, envia os avisos; cada catálogo e cada aviso pode escolher outro."
    >
      <div className="flex flex-col gap-3" id="whatsapps-da-loja">
        {lista.length === 0 && (
          <p className="text-[13px] text-suave">Nenhum WhatsApp próprio: o site usa o da empresa e nenhum aviso sai.</p>
        )}
        {lista.map((n, i) => {
          const gravado = gravados.find((g) => g.id === n.id) ?? null;
          return (
            <div key={n.chave} data-zap={i} className="rounded-[10px] border border-[var(--color-linha)] p-3">
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" disabled={!podeEditar} onClick={() => tornarPrincipal(i)}
                        aria-pressed={n.principal} title={n.principal ? "Principal da loja" : "Tornar o principal"}
                        aria-label={n.principal ? "principal da loja" : "tornar o principal"}
                        className={`h-9 w-9 shrink-0 rounded-md border text-[17px] ${n.principal
                          ? "border-erva bg-erva text-white" : "border-linha text-suave hover:border-erva"}`}>
                  ★
                </button>
                <input className="campo min-w-[140px] flex-1" disabled={!podeEditar} maxLength={60}
                       placeholder="Atendimento, Encomendas…" aria-label="nome do número"
                       value={n.rotulo} onChange={(e) => troca(i, { ...n, rotulo: e.target.value })} />
                <input className="campo mono w-[190px]" disabled={!podeEditar} maxLength={30}
                       placeholder="(99) 99999-9999" aria-label="número do WhatsApp"
                       value={n.numero} onChange={(e) => troca(i, { ...n, numero: e.target.value })} />
                {n.conectado ? (
                  <Etiqueta cor={n.modo === "real" ? "erva" : "alerta"}>
                    {n.modo === "real" ? "enviando de verdade" : "modo simulado"}
                  </Etiqueta>
                ) : <Etiqueta>só para o cliente chamar</Etiqueta>}
                {podeEditar && (
                  <button type="button" className="link-acao text-[13px]" onClick={() => remover(i)}
                          aria-label={`remover ${n.rotulo || n.numero || "número"}`}>
                    remover
                  </button>
                )}
              </div>
              <details className="mt-3" open={n.conectado && !gravado}>
                <summary className="cursor-pointer text-[13.5px] font-semibold">Conexão com a Meta</summary>
                <div className="mt-3">
                  <ConexaoDoNumero n={n} gravado={gravado} webhookUrl={webhookUrl}
                                   principal={n.principal ? null : principal}
                                   aoMudar={(x) => troca(i, x)} podeEditar={podeEditar} />
                </div>
              </details>
            </div>
          );
        })}
        {podeEditar && (
          <button type="button" className="link-acao self-start text-[13px]" id="novo-whatsapp"
                  onClick={() => aoTrocar([...lista, numeroNovo(!lista.length)])}>
            + número
          </button>
        )}
        <details className="text-[13px]">
          <summary className="cursor-pointer font-semibold">Passo a passo na Meta</summary>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-suave">
            <li>Em business.facebook.com, use o portfólio empresarial da casa (verifique a empresa, se a Meta pedir).</li>
            <li>Em developers.facebook.com, crie um app do tipo Empresa e adicione o produto WhatsApp.</li>
            <li>Adicione os números da casa ao app (o atual pode ser usado — siga a opção de usar com o app WhatsApp Business, se oferecida).</li>
            <li>Crie um usuário do sistema com acesso ao app e gere um token permanente com as permissões de WhatsApp. Cole no número principal; os outros podem usar a conta dele.</li>
            <li>Copie o Phone number ID de cada número e a App secret (Configurações do app → Básico). Cole em cada número.</li>
            <li>Configure o webhook do app com a URL e o token de verificação mostrados acima.</li>
            <li>Cadastre os modelos de mensagem (em Avisos, cada um traz o texto pronto) e espere a aprovação. ⚠️ Os modelos são da conta (WABA): número em outra conta precisa dos modelos lá também.</li>
            <li>Ligue os avisos, teste, e mude para “Enviar de verdade”.</li>
          </ol>
        </details>
      </div>
    </Cartao>
  );
}
