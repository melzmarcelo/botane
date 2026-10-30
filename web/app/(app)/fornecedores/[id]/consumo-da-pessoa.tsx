"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Aviso, Carregando, Cartao, Vazio } from "@/components/ui";
import { ErroApi } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { consumoEmAberto, type ConsumoEmAberto } from "@/lib/consumo";
import { TabelaPorDocumento } from "../../vendas/por-pessoa/tabelas-documento";

import { plural } from "@/lib/numeros";
/**
 * O consumo desta pessoa ainda não cobrado — o que ela está devendo agora.
 *
 * 🔑 **Pedido do dono (26/09/2026):** *"no cadastro da pessoa, incluir um item referente a
 * consumos no período aberto atual."* Desde 22/10/2026 não há período: é o que está EM
 * ABERTO (sem lote de cobrança), e o que já foi mandado em lote aparece ao lado. Os
 * mesmos números do relatório de consumo por pessoa (a rota usa a mesma consulta).
 *
 * ⚠️ **Sem a permissão do relatório, o cartão não aparece** — e isso não é erro: ver a
 * ficha da pessoa não é o mesmo que ver o que ela deve. Por isso o 403 some calado, e
 * só outro erro vira aviso.
 * ⚠️ **Fornecedor que nunca consumiu não ganha cartão vazio**: a ficha de quem vende
 * farinha para a casa não precisa dizer "nenhum consumo". Quem não é só fornecedor vê o
 * cartão mesmo vazio, porque "não deve nada" é informação.
 */
export default function ConsumoDaPessoa({
  id,
  soFornecedor,
}: {
  id: number;
  soFornecedor: boolean;
}) {
  const [dados, setDados] = useState<ConsumoEmAberto | null>(null);
  const [erro, setErro] = useState("");
  const [semPermissao, setSemPermissao] = useState(false);

  useEffect(() => {
    let vivo = true;
    consumoEmAberto(id)
      .then((d) => vivo && setDados(d))
      .catch((e) => {
        if (!vivo) return;
        if (e instanceof ErroApi && e.status === 403) setSemPermissao(true);
        else setErro(e instanceof Error ? e.message : "Falha ao carregar o consumo");
      });
    return () => {
      vivo = false;
    };
  }, [id]);

  if (semPermissao) return null;
  if (dados && soFornecedor && !dados.documentos.length && !dados.lotes_em_cobranca) return null;

  return (
    <Cartao
      titulo="Consumo em aberto"
      descricao="O que esta pessoa consumiu e ainda não foi cobrado."
      acao={
        <Link href="/receber" className="link-acao text-[13px]">
          contas a receber
        </Link>
      }
    >
      {erro ? (
        <Aviso tipo="erro">{erro}</Aviso>
      ) : !dados ? (
        <Carregando />
      ) : !dados.documentos.length && !dados.lotes_em_cobranca ? (
        <Vazio>Nada em aberto nem em cobrança.</Vazio>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-4">
            {[
              { r: "Valor cheio", v: dados.total_cheio },
              { r: "Desconto", v: dados.desconto },
              { r: "A cobrar", v: dados.total },
              { r: `Em cobrança (${plural(dados.lotes_em_cobranca, "lote", "lotes")})`, v: dados.em_cobranca },
            ].map((t) => (
              <div key={t.r} className="rounded-[10px] border border-[var(--color-linha)] px-4 py-3">
                <b className="block text-[22px] tabular-nums">{reais(t.v)}</b>
                <span className="text-[12.5px] text-suave">{t.r}</span>
              </div>
            ))}
          </div>
          {dados.documentos.length > 0 && (
            <TabelaPorDocumento linhas={dados.documentos} comItens />
          )}
        </div>
      )}
    </Cartao>
  );
}
