"use client";

/**
 * Os WhatsApps da loja (migração 143): vários, um principal.
 *
 * 🔑 **Pedido do dono (30/10/2026):** *"no cadastro de whatsapp nas lojas, poder configurar mais
 * de um, e tornar um o principal da loja."* O principal é o "Entre em contato" do site; os outros
 * ficam à escolha de cada catálogo (Catálogos ▸ Publicação ▸ WhatsApp deste catálogo).
 * ⚠️ São números para o cliente CHAMAR. A conexão com a Meta, que envia os avisos, é a aba
 * WhatsApp — outra coisa.
 */

export type NumeroZap = { id: number | null; rotulo: string; numero: string; principal: boolean };

export default function WhatsappsDaLoja({
  lista,
  aoTrocar,
  podeEditar,
}: {
  lista: NumeroZap[];
  aoTrocar: (l: NumeroZap[]) => void;
  podeEditar: boolean;
}) {
  const troca = (i: number, campo: keyof NumeroZap, v: string | boolean) =>
    aoTrocar(lista.map((n, j) => (j === i ? { ...n, [campo]: v } : n)));
  const principal = (i: number) => aoTrocar(lista.map((n, j) => ({ ...n, principal: j === i })));
  function remover(i: number) {
    const resto = lista.filter((_, j) => j !== i);
    // Tirou o principal: o primeiro que sobrou assume (loja com número precisa de um).
    if (lista[i].principal && resto.length) resto[0] = { ...resto[0], principal: true };
    aoTrocar(resto);
  }
  const novo = () =>
    aoTrocar([...lista, { id: null, rotulo: lista.length ? "" : "Atendimento", numero: "", principal: !lista.length }]);

  return (
    <div className="flex flex-col gap-2" id="whatsapps-da-loja">
      {lista.length === 0 && (
        <p className="text-[13px] text-suave">Nenhum WhatsApp próprio: o site usa o da empresa.</p>
      )}
      {lista.map((n, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2" data-zap={i}>
          <button type="button" disabled={!podeEditar} onClick={() => principal(i)}
                  aria-pressed={n.principal} title={n.principal ? "Principal da loja" : "Tornar o principal"}
                  aria-label={n.principal ? "principal da loja" : "tornar o principal"}
                  className={`h-9 w-9 shrink-0 rounded-md border text-[17px] ${n.principal
                    ? "border-erva bg-erva text-white" : "border-linha text-suave hover:border-erva"}`}>
            ★
          </button>
          <input className="campo min-w-[140px] flex-1" disabled={!podeEditar} maxLength={60}
                 placeholder="Atendimento, Encomendas…" aria-label="nome do número"
                 value={n.rotulo} onChange={(e) => troca(i, "rotulo", e.target.value)} />
          <input className="campo mono w-[190px]" disabled={!podeEditar} maxLength={30}
                 placeholder="(99) 99999-9999" aria-label="número do WhatsApp"
                 value={n.numero} onChange={(e) => troca(i, "numero", e.target.value)} />
          {n.principal && <span className="text-[12px] text-erva">principal</span>}
          {podeEditar && (
            <button type="button" className="link-acao text-[13px]" onClick={() => remover(i)}
                    aria-label={`remover ${n.rotulo || n.numero || "número"}`}>
              remover
            </button>
          )}
        </div>
      ))}
      {podeEditar && (
        <button type="button" className="link-acao self-start text-[13px]" id="novo-whatsapp" onClick={novo}>
          + número
        </button>
      )}
    </div>
  );
}
