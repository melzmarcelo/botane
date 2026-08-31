"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso } from "@/components/ui";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import FormularioLoja, { corpoDaLoja, LOJA_VAZIA, LojaForm } from "../formulario";

/**
 * Abrir uma loja.
 *
 * ⚠️ **A loja nasce com um LOCAL de estoque principal**, criado pelo servidor.
 * Sem local nada se movimenta — nem entrada, nem produção, nem inventário —, e
 * a mensagem que aparecia era "Local não encontrado", que não diz o que fazer.
 * Quem abre a segunda loja não deveria descobrir isso na primeira nota.
 */
export default function NovaLoja() {
  const aviso = useAviso();
  const router = useRouter();
  const { pode } = useSessao();
  const podeEditar = pode("admin.unidades");
  const [f, setF] = useState<LojaForm>(LOJA_VAZIA);
  const [ocupado, setOcupado] = useState(false);

  async function salvar() {
    setOcupado(true);
    try {
      const r = await api.post<{ id: number }>("/unidades", corpoDaLoja(f));
      aviso.sucesso("Loja criada — ela já nasce com um local de estoque principal.");
      // Leva para a loja recém-criada: o passo seguinte é conferir os
      // parâmetros dela, e voltar à lista para clicar de novo seria atrito bobo.
      router.push(`/lojas/${r.id}`);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível criar a loja");
      setOcupado(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-[860px] flex-col gap-6">
      <header>
        <Link href="/lojas" className="link-voltar">
          Lojas
        </Link>
        <h1 className="mt-2 text-[26px] font-bold tracking-tight sm:text-[30px]">Nova loja</h1>
        <p className="mt-1 max-w-[68ch] text-suave">
          Cada loja tem CNPJ, endereço e estoque próprios. Todo movimento nasce carimbado com
          ela — razão, nota, venda, inventário e fechamento.
        </p>
      </header>

      {!podeEditar ? (
        <Aviso tipo="info">Só quem administra lojas pode abrir uma nova.</Aviso>
      ) : (
        <>
          {/* ⚠️ A integração é POR LOJA, e isso precisa ser dito antes: quem
              abre a filial esperando que ela já converse com o PDV descobriria
              o contrário no primeiro dia de venda. */}
          <Aviso tipo="info">
            As integrações são de cada loja: depois de criar, troque de loja no seletor do topo
            e configure o PDV e o Omie dela em <b>Integrações</b>. A credencial da matriz não
            vale para a filial — e o envio confere o CNPJ antes de escrever.
          </Aviso>
          <FormularioLoja
            valor={f}
            aoTrocar={setF}
            aoSalvar={salvar}
            ocupado={ocupado}
            rotuloSalvar="Criar loja"
            podeEditar={podeEditar}
          />
        </>
      )}
    </div>
  );
}
