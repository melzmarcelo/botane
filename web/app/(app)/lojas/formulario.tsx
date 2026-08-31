"use client";

import { FormEvent, useEffect, useState } from "react";

import { Campo, Cartao } from "@/components/ui";
import { mascaraCnpj } from "@/lib/cadastros";

/**
 * O cadastro de uma loja — o mesmo formulário para criar e para corrigir.
 *
 * 🔑 **Empresa e loja são coisas diferentes, e as duas existem.** A empresa é a
 * marca e a identidade do grupo (razão social, CNPJ do grupo, a logo do timbre);
 * a LOJA é cada ponto, com **CNPJ próprio**, endereço e telefone. Todo movimento
 * do sistema nasce carimbado com a loja — razão, nota, venda, inventário e
 * fechamento —, e é por isso que ela precisa de cadastro de verdade, não de um
 * nome solto.
 *
 * ⚠️ **A mesma forma nas duas telas**, para o olho reconhecer: criar e corrigir
 * uma loja não são momentos diferentes o bastante para justificar dois desenhos.
 */

export type LojaForm = {
  nome: string;
  apelido: string;
  cnpj: string;
  inscricao_estadual: string;
  matriz: boolean;
  ativo: boolean;
  cep: string;
  logradouro: string;
  numero: string;
  complemento: string;
  bairro: string;
  cidade: string;
  uf: string;
  telefone: string;
  email: string;
  mesas: string;
};

export const LOJA_VAZIA: LojaForm = {
  nome: "",
  apelido: "",
  cnpj: "",
  inscricao_estadual: "",
  matriz: false,
  ativo: true,
  cep: "",
  logradouro: "",
  numero: "",
  complemento: "",
  bairro: "",
  cidade: "",
  uf: "",
  telefone: "",
  email: "",
  mesas: "",
};

/** O que vai para a API: campo vazio vira nulo, e `mesas` vira número. */
export function corpoDaLoja(f: LojaForm) {
  const texto = (v: string) => v.trim() || null;
  return {
    nome: f.nome.trim(),
    apelido: texto(f.apelido),
    cnpj: texto(f.cnpj),
    inscricao_estadual: texto(f.inscricao_estadual),
    matriz: f.matriz,
    ativo: f.ativo,
    cep: texto(f.cep),
    logradouro: texto(f.logradouro),
    numero: texto(f.numero),
    complemento: texto(f.complemento),
    bairro: texto(f.bairro),
    cidade: texto(f.cidade),
    uf: texto(f.uf)?.toUpperCase() ?? null,
    telefone: texto(f.telefone),
    email: texto(f.email),
    mesas: f.mesas.trim() ? Number(f.mesas) : null,
  };
}

export default function FormularioLoja({
  valor,
  aoTrocar,
  aoSalvar,
  ocupado,
  rotuloSalvar,
  podeEditar,
  eraMatriz,
}: {
  valor: LojaForm;
  aoTrocar: (f: LojaForm) => void;
  aoSalvar: () => void;
  ocupado: boolean;
  rotuloSalvar: string;
  podeEditar: boolean;
  /** Já é a matriz hoje — e aí a caixinha não se desmarca sozinha. */
  eraMatriz?: boolean;
}) {
  const [avisoCnpj, setAvisoCnpj] = useState("");
  const troca = (campo: keyof LojaForm, v: string | boolean) =>
    aoTrocar({ ...valor, [campo]: v } as LojaForm);

  // ⚠️ O CNPJ é o que separa uma loja da outra na integração com o PDV, e a
  // conferência por lote compara só os DÍGITOS. Avisa, não trava: cadastro pela
  // metade é o estado normal no primeiro dia.
  useEffect(() => {
    const so = valor.cnpj.replace(/\D/g, "");
    setAvisoCnpj(so && so.length !== 14 ? "O CNPJ tem 14 dígitos." : "");
  }, [valor.cnpj]);

  function enviar(e: FormEvent) {
    e.preventDefault();
    aoSalvar();
  }

  return (
    <form className="flex flex-col gap-6" onSubmit={enviar}>
      <Cartao
        titulo="Identificação"
        descricao="Como a loja se chama e por qual CNPJ ela responde."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo rotulo="Nome" className="sm:col-span-2">
            <input
              className="campo"
              required
              minLength={2}
              maxLength={120}
              disabled={!podeEditar}
              value={valor.nome}
              onChange={(e) => troca("nome", e.target.value)}
            />
          </Campo>
          <Campo
            rotulo="Apelido"
            dica="O nome curto: é ele que aparece no seletor de loja e na visão da rede."
          >
            <input
              className="campo"
              maxLength={40}
              disabled={!podeEditar}
              placeholder="Matriz"
              value={valor.apelido}
              onChange={(e) => troca("apelido", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Mesas" dica="Opcional.">
            <input
              className="campo mono"
              type="number"
              min={0}
              disabled={!podeEditar}
              value={valor.mesas}
              onChange={(e) => troca("mesas", e.target.value)}
            />
          </Campo>
          <Campo
            rotulo="CNPJ"
            dica={avisoCnpj || "É por ele que o envio ao PDV confere de quem é a conta."}
          >
            <input
              className="campo mono"
              disabled={!podeEditar}
              value={valor.cnpj}
              onChange={(e) => troca("cnpj", mascaraCnpj(e.target.value))}
            />
          </Campo>
          <Campo rotulo="Inscrição estadual">
            <input
              className="campo mono"
              disabled={!podeEditar}
              value={valor.inscricao_estadual}
              onChange={(e) => troca("inscricao_estadual", e.target.value)}
            />
          </Campo>
        </div>

        <div className="mt-4 flex flex-col gap-3 border-t border-linha pt-4">
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-erva"
              disabled={!podeEditar || eraMatriz}
              checked={valor.matriz}
              onChange={(e) => troca("matriz", e.target.checked)}
            />
            <span className="text-[14px] leading-snug">
              é a matriz
              {/* ⚠️ Só UMA é matriz: marcar esta desmarca a outra, e quem faz
                  isso é o servidor. Desmarcar a atual deixaria a casa sem
                  nenhuma — e a matriz é a resposta padrão de quem não escolheu
                  loja. */}
              <span className="block text-[12.5px] text-suave">
                {eraMatriz
                  ? "Esta já é a matriz. Para trocar, marque a caixa na outra loja."
                  : "Marcar aqui tira a marca da loja que é matriz hoje."}
              </span>
            </span>
          </label>
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-erva"
              disabled={!podeEditar}
              checked={valor.ativo}
              onChange={(e) => troca("ativo", e.target.checked)}
            />
            <span className="text-[14px] leading-snug">
              ativa
              <span className="block text-[12.5px] text-suave">
                Loja inativa sai do seletor e da visão da rede. O que ela já movimentou fica.
              </span>
            </span>
          </label>
        </div>
      </Cartao>

      <Cartao titulo="Endereço e contato" descricao="Sai no cabeçalho dos PDFs desta loja.">
        <div className="grid gap-4 sm:grid-cols-6">
          <Campo rotulo="CEP" className="sm:col-span-2">
            <input
              className="campo mono"
              maxLength={9}
              disabled={!podeEditar}
              value={valor.cep}
              onChange={(e) => troca("cep", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Logradouro" className="sm:col-span-4">
            <input
              className="campo"
              disabled={!podeEditar}
              value={valor.logradouro}
              onChange={(e) => troca("logradouro", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Número" className="sm:col-span-1">
            <input
              className="campo"
              disabled={!podeEditar}
              value={valor.numero}
              onChange={(e) => troca("numero", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Complemento" className="sm:col-span-2">
            <input
              className="campo"
              disabled={!podeEditar}
              value={valor.complemento}
              onChange={(e) => troca("complemento", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Bairro" className="sm:col-span-3">
            <input
              className="campo"
              disabled={!podeEditar}
              value={valor.bairro}
              onChange={(e) => troca("bairro", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Cidade" className="sm:col-span-4">
            <input
              className="campo"
              disabled={!podeEditar}
              value={valor.cidade}
              onChange={(e) => troca("cidade", e.target.value)}
            />
          </Campo>
          {/* ⚠️ A UF só aparece ATRÁS da cidade no timbre — sozinha, viraria uma
              linha de endereço escrita "SC". */}
          <Campo rotulo="UF" className="sm:col-span-2">
            <input
              className="campo mono uppercase"
              maxLength={2}
              disabled={!podeEditar}
              value={valor.uf}
              onChange={(e) => troca("uf", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Telefone" className="sm:col-span-3">
            <input
              className="campo mono"
              disabled={!podeEditar}
              value={valor.telefone}
              onChange={(e) => troca("telefone", e.target.value)}
            />
          </Campo>
          <Campo rotulo="E-mail" className="sm:col-span-3">
            <input
              className="campo"
              type="email"
              disabled={!podeEditar}
              value={valor.email}
              onChange={(e) => troca("email", e.target.value)}
            />
          </Campo>
        </div>
      </Cartao>

      {podeEditar && (
        <div className="flex justify-end">
          <button className="btn btn-primario" disabled={ocupado}>
            {ocupado ? "Salvando…" : rotuloSalvar}
          </button>
        </div>
      )}
    </form>
  );
}
