"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Fornecedor, mascaraCnpj } from "@/lib/cadastros";
import { Aviso, Campo, Cartao } from "@/components/ui";

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
  /**
   * Esta pessoa VENDE para a casa?
   *
   * 🔑 A tabela passou a guardar gente que não vende nada — funcionário, sócio.
   * O seletor de fornecedor da nota e do produto filtra por isto; sem a marca,
   * aquele seletor viraria uma lista de funcionários.
   */
  fornecedor: boolean;
  /** VENDA ou CUSTO — a base do cupom quando esta pessoa é informada na venda. */
  cupom_base: "VENDA" | "CUSTO";
  cupom_desconto_pct: string;
};

export const VAZIO: Form = {
  nome: "", nome_fantasia: "", cnpj: "", contato: "", telefone: "", whatsapp: "",
  email: "", cidade: "", uf: "", prazo_entrega_dias: "", dias_entrega: "",
  pedido_minimo: "", observacao: "",
  // ⚠️ Quem cadastra pela tela de Pessoas quase sempre está cadastrando um
  // fornecedor — é a origem histórica desta tela. Quem não for, desmarca.
  fornecedor: true, cupom_base: "VENDA", cupom_desconto_pct: "",
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
    // ⚠️ `?? true`: cadastro antigo não tem o campo, e ele É fornecedor.
    fornecedor: x.fornecedor ?? true,
    cupom_base: x.cupom_base ?? "VENDA",
    cupom_desconto_pct: x.cupom_desconto_pct ? String(x.cupom_desconto_pct) : "",
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
      fornecedor: f.fornecedor,
      cupom_base: f.cupom_base,
      // ⚠️ Vazio vira ZERO, não nulo: a coluna é NOT NULL, e "sem desconto" é
      // zero por cento, que é uma resposta.
      cupom_desconto_pct: num(f.cupom_desconto_pct) ?? 0,
    };
    try {
      if (id) {
        await api.put(`/fornecedores/${id}`, corpo);
        aviso.sucesso("Pessoa atualizada.");
        aoGravar(id);
      } else {
        const r = await api.post<{ id: number }>("/fornecedores", corpo);
        aviso.sucesso("Pessoa criada.");
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

      {/* 🔑 **A pessoa pode não vender nada para a casa** (04/09/2026, pedido do
          dono). A tabela passou a guardar funcionário e sócio, e o seletor de
          fornecedor da nota e do produto filtra por esta marca — sem ela,
          aquele seletor viraria uma lista de gente da casa. */}
      <Cartao
        titulo="O que esta pessoa é para a casa"
        descricao="Só quem vende para a casa aparece nos seletores de fornecedor da nota e do produto."
      >
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-1 h-4 w-4 accent-erva"
            checked={f.fornecedor}
            onChange={(e) => setF({ ...f, fornecedor: e.target.checked })}
          />
          <span>
            <span className="text-[14.5px] font-semibold">É fornecedor</span>
            <span className="block text-[12.5px] leading-snug text-suave">
              Desmarcado, a pessoa continua aqui e some dos seletores de compra — é o caso do
              funcionário e do sócio.
            </span>
          </span>
        </label>
      </Cartao>

      {/* 🔑 **A política do cupom** (pedido do dono). A venda lançada à mão
          sempre puxa o preço de venda; informando esta pessoa, o item passa a
          valer o CUSTO ou o preço com desconto. É o desconto de funcionário e o
          consumo do proprietário com a mesma mecânica. */}
      <Cartao
        titulo="No cupom desta pessoa"
        descricao="Vale só na venda lançada à mão. O cupom que vem do PDV traz os valores cobrados de verdade."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo rotulo="O item vale" dica="o que entra no lugar do preço">
            <select
              className="campo"
              value={f.cupom_base}
              onChange={(e) =>
                setF({ ...f, cupom_base: e.target.value as "VENDA" | "CUSTO" })}
            >
              <option value="VENDA">o preço de venda</option>
              <option value="CUSTO">o custo</option>
            </select>
          </Campo>
          <Campo rotulo="Desconto (%)" dica="em branco é sem desconto">
            <input
              className="campo mono"
              type="number"
              step="0.01"
              min="0"
              max="100"
              value={f.cupom_desconto_pct}
              onChange={(e) => setF({ ...f, cupom_desconto_pct: e.target.value })}
            />
          </Campo>
        </div>
        {/* ⚠️ A consequência dita antes de acontecer: quem lança pelo custo com
            desconto vai ver margem negativa no painel, e isso é o que aconteceu
            — não um defeito. */}
        {(f.cupom_base === "CUSTO" || Number(f.cupom_desconto_pct) > 0) && (
          <div className="mt-3">
            <Aviso tipo="info">
              A venda lançada para esta pessoa{" "}
              {f.cupom_base === "CUSTO" ? (
                <>sai pelo <b>custo</b></>
              ) : (
                <>sai pelo preço de venda</>
              )}
              {Number(f.cupom_desconto_pct) > 0 && (
                <>, com <b>{f.cupom_desconto_pct}% de desconto</b></>
              )}
              . Ela <b>baixa estoque e entra no CMV</b> como qualquer venda — com margem menor,
              ou negativa se o desconto for sobre o custo.
            </Aviso>
          </div>
        )}
      </Cartao>

      <div className="flex flex-wrap gap-2">
        <button className="btn btn-primario" type="submit" disabled={salvando}>
          {salvando ? "Salvando…" : id ? "Salvar" : "Criar pessoa"}
        </button>
        <Link href="/fornecedores" className="btn btn-secundario">
          Cancelar
        </Link>
      </div>
    </form>
  );
}
