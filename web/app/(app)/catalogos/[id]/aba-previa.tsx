"use client";

/**
 * A aba Pré-visualização: o catálogo como vai ao ar, em qualquer situação.
 *
 * 🔑 **Pedido do dono (30/10/2026):** *"no cadastro de catálogos, uma aba pré-visualização, onde
 * podemos ver como este será exibido online, com as funcionalidades de teste"*.
 * - Catálogo que é **Cardápio Vivo** → o feed (`/c/previa/{id}`, a prévia que já existia).
 * - Catálogo **simples** → o SITE (`/portal?previa={id}`): a mesma página do cliente, aberta pela
 *   rota de dentro (rascunho e fora do período também), com o carrinho e a cesta funcionando e o
 *   "enviar" virando TESTE — o servidor confere e responde o total, sem gravar pedido.
 * ⚠️ O iframe é do MESMO endereço do sistema: o login (localStorage) vale lá dentro.
 */

import { useState } from "react";
import type { Catalogo } from "@/lib/catalogos";

const TELAS = { celular: 390, computador: 1100 } as const;

export default function AbaPrevia({ capa }: { capa: Catalogo }) {
  const [tela, setTela] = useState<keyof typeof TELAS>("celular");
  const [versao, setVersao] = useState(0);
  const vivo = capa.cardapio_vivo;
  const endereco = vivo ? `/c/previa/${capa.id}` : `/portal?previa=${capa.id}`;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <p className="min-w-0 flex-1 text-[13.5px] text-suave">
          {vivo
            ? "É o Cardápio Vivo: o feed como a mesa vê, mesmo fora do horário das seções."
            : "Como o site mostra este catálogo, mesmo em rascunho ou fora do período. Pedidos aqui são teste: o servidor confere e nada é gravado."}
        </p>
        <span className="flex gap-1" role="group" aria-label="tamanho da tela">
          {(Object.keys(TELAS) as (keyof typeof TELAS)[]).map((k) => (
            <button key={k} type="button" aria-pressed={tela === k} onClick={() => setTela(k)}
                    className={`rounded-md border px-3 py-1.5 text-[13px] ${tela === k
                      ? "border-erva bg-erva text-white" : "border-linha hover:border-erva"}`}>
              {k === "celular" ? "Celular" : "Computador"}
            </button>
          ))}
        </span>
        <button type="button" className="link-acao" onClick={() => setVersao((v) => v + 1)}>recarregar</button>
        <a href={endereco} target="_blank" rel="noreferrer" className="link-acao">abrir em outra aba ↗</a>
      </div>
      <div className="overflow-x-auto rounded-lg border border-linha bg-superficie2 p-3">
        <iframe key={`${tela}-${versao}`} src={endereco} title="pré-visualização do catálogo" id="previa-catalogo"
                className="mx-auto block rounded-md border border-linha bg-white"
                style={{ width: TELAS[tela], maxWidth: "none", height: 760 }} />
      </div>
    </div>
  );
}
