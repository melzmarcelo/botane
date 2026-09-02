"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Fornecedor, mascaraCnpj } from "@/lib/cadastros";
import { Campo, Cartao } from "@/components/ui";

/**
 * O cadastro do fornecedor — a mesma forma para criar e para corrigir.
 *
 * ⚠️ **Saiu da coluna da direita da lista.** Espremido em 360 px, o formulário
 * tinha treze campos em uma coluna só: quem cadastrava rolava a tela inteira
 * para chegar no botão, e a lista — que é o assunto da página — ficava
 * empurrada para o lado. Mesmo corte de Compras e de Vendas: consultar e
 * cadastrar são telas diferentes.
 *
 * ⚠️ **UF em maiúsculas na hora**, porque é sigla de dois caracteres e não tem
 * outra forma certa. Nome de fornecedor NÃO: ao contrário do produto, ele é
 * razão social — "Cia. Brasileira de Distribuição" escrito em caixa alta perde
 * a leitura sem ganhar nada, e não vem de três integrações diferentes.
 */

type Form = {
  nome: string;
  nome_fantasia: string;
  cnpj: string;
  contato: string;
  telefone: string;
  whatsapp: string;
  email: string;
  cidade: string;
  uf: string;
  prazo_entrega_dias: string;
  dias_entrega: string;
  pedido_minimo: string;
  observacao: string;
};

export const VAZIO: Form = {
  nome: "", nome_fantasia: "", cnpj: "", contato: "", telefone: "", whatsapp: "",
  email: "", cidade: "", uf: "", prazo_entrega_dias: "", dias_entrega: "",
  pedido_minimo: "", observacao: "",
};

export function doFornecedor(x: Fornecedor): Form {
  return {
    nome: x.nome ?? "",
    nome_fantasia: x.nome_fantasia ?? "",
    cnpj: x.cnpj ? mascaraCnpj(x.cnpj) : "",
    contato: x.contato ?? "",
    telefone: x.telefone ?? "",
    whatsapp: x.whatsapp ?? "",
    email: x.email ?? "",
    cidade: x.cidade ?? "",
    uf: x.uf ?? "",
    prazo_entrega_dias: x.prazo_entrega_dias?.toString() ?? "",
    dias_entrega: x.dias_entrega ?? "",
    pedido_minimo: x.pedido_minimo?.toString() ?? "",
    observacao: x.observacao ?? "",
  };
}

const texto = (v: string) => (v.trim() === "" ? null : v.trim());
const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));

export default function FormularioFornecedor({
  inicial,
  id,
  aoGravar,
}: {
  inicial: Form;
  id?: number;
  aoGravar: (id: number) => void;
}) {
  const aviso = useAviso();
  const [f, setF] = useState<Form>(inicial);
  const [salvando, setSalvando] = useState(false);

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    const corpo = {
      nome: f.nome.trim(),
      nome_fantasia: texto(f.nome_fantasia),
      cnpj: texto(f.cnpj),
      contato: texto(f.contato),
      telefone: texto(f.telefone),
      whatsapp: texto(f.whatsapp),
      email: texto(f.email),
      cidade: texto(f.cidade),
      uf: texto(f.uf),
      prazo_entrega_dias: num(f.prazo_entrega_dias),
      dias_entrega: texto(f.dias_entrega),
      pedido_minimo: num(f.pedido_minimo),
      observacao: texto(f.observacao),
    };
    try {
      if (id) {
        await api.put(`/fornecedores/${id}`, corpo);
        aviso.sucesso("Fornecedor atualizado.");
        aoGravar(id);
      } else {
        const r = await api.post<{ id: number }>("/fornecedores", corpo);
        aviso.sucesso("Fornecedor criado.");
        aoGravar(r.id);
      }
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <form onSubmit={salvar} className="flex flex-col gap-6">
      <Cartao titulo="Identificação">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* ⚠️ `uppercase` é só CSS, e é de propósito: o valor gravado é
              normalizado pelo BANCO (gatilho da migração 050). A classe existe
              para quem digita ver o que vai ser gravado, em vez de descobrir
              depois — mesma dica que o cadastro de produto tem. */}
          <Campo rotulo="Razão social / nome" className="sm:col-span-2">
            <input
              className="campo uppercase"
              required
              minLength={2}
              value={f.nome}
              onChange={(e) => setF({ ...f, nome: e.target.value })}
            />
          </Campo>
          <Campo rotulo="Nome fantasia">
            <input
              className="campo uppercase"
              value={f.nome_fantasia}
              onChange={(e) => setF({ ...f, nome_fantasia: e.target.value })}
            />
          </Campo>
          {/* ⚠️ O CNPJ é o que liga a nota que vem do Omie ao fornecedor certo —
              sem ele a conciliação vira trabalho manual. */}
          <Campo rotulo="CNPJ" dica="é ele que casa a nota do Omie">
            <input
              className="campo mono"
              placeholder="00.000.000/0000-00"
              value={f.cnpj}
              onChange={(e) => setF({ ...f, cnpj: mascaraCnpj(e.target.value) })}
            />
          </Campo>
          <Campo rotulo="Cidade">
            <input
              className="campo"
              value={f.cidade}
              onChange={(e) => setF({ ...f, cidade: e.target.value })}
            />
          </Campo>
          <Campo rotulo="UF">
            <input
              className="campo uppercase"
              maxLength={2}
              value={f.uf}
              onChange={(e) => setF({ ...f, uf: e.target.value.toUpperCase() })}
            />
          </Campo>
        </div>
      </Cartao>

      <Cartao titulo="Contato">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Campo rotulo="Contato">
            <input
              className="campo"
              value={f.contato}
              onChange={(e) => setF({ ...f, contato: e.target.value })}
            />
          </Campo>
          <Campo rotulo="Telefone">
            <input
              className="campo"
              value={f.telefone}
              onChange={(e) => setF({ ...f, telefone: e.target.value })}
            />
          </Campo>
          <Campo rotulo="WhatsApp">
            <input
              className="campo"
              value={f.whatsapp}
              onChange={(e) => setF({ ...f, whatsapp: e.target.value })}
            />
          </Campo>
          <Campo rotulo="E-mail">
            <input
              className="campo"
              type="email"
              value={f.email}
              onChange={(e) => setF({ ...f, email: e.target.value })}
            />
          </Campo>
        </div>
      </Cartao>

      <Cartao titulo="Entrega" descricao="O que a compra precisa saber antes de pedir.">
        <div className="grid gap-4 sm:grid-cols-3">
          <Campo rotulo="Prazo (dias)">
            <input
              className="campo mono"
              type="number"
              min="0"
              value={f.prazo_entrega_dias}
              onChange={(e) => setF({ ...f, prazo_entrega_dias: e.target.value })}
            />
          </Campo>
          <Campo rotulo="Dias de entrega" dica="seg,qua,sex">
            <input
              className="campo"
              value={f.dias_entrega}
              onChange={(e) => setF({ ...f, dias_entrega: e.target.value })}
            />
          </Campo>
          <Campo rotulo="Pedido mínimo (R$)">
            <input
              className="campo mono"
              type="number"
              step="0.01"
              min="0"
              value={f.pedido_minimo}
              onChange={(e) => setF({ ...f, pedido_minimo: e.target.value })}
            />
          </Campo>
        </div>
        <div className="mt-4">
          <Campo rotulo="Observação">
            <textarea
              className="campo min-h-[80px]"
              value={f.observacao}
              onChange={(e) => setF({ ...f, observacao: e.target.value })}
            />
          </Campo>
        </div>
      </Cartao>

      <div className="flex flex-wrap gap-2">
        <button className="btn btn-primario" type="submit" disabled={salvando}>
          {salvando ? "Salvando…" : id ? "Salvar" : "Criar fornecedor"}
        </button>
        <Link href="/fornecedores" className="btn btn-secundario">
          Cancelar
        </Link>
      </div>
    </form>
  );
}
