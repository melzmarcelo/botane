"use client";

import BuscaCadastro from "@/components/busca-cadastro";
import { Campo, CampoMoeda, Cartao } from "@/components/ui";
import { urlArquivo } from "@/lib/api";
import { fonteProdutos } from "@/lib/busca-cadastro";
import type { Local, Setor } from "@/lib/cadastros";
import { hoje } from "@/lib/datas";
import { CRITICIDADES, SITUACOES, TENSOES, dataBr, type BemDetalhe } from "@/lib/patrimonio";

import { somarMeses, type Form, type Muda } from "./form";
import PreviaPlaqueta from "./plaqueta";
import ValorDoBem from "./valor";

const FONTE_PATRIMONIO = fonteProdutos("tipo=PATRIMONIO");

/**
 * Aba Dados do bem: identificação, localização e status, e a compra — com a prévia da
 * plaqueta ao lado (no celular, embaixo).
 * ⚠️ Os ids (`bem-descricao`, `bem-vida-util`, `bem-valor-atual`, `bem-situacao`…) são os
 * que a bateria do navegador usa: o valor atual fica AQUI, ao lado da vida útil que o muda.
 */
export default function AbaDados({ f, setF, muda, travado, bem, setores, locais, produto, aoEscolherProduto }: {
  f: Form; setF: (f: Form) => void; muda: Muda; travado: boolean; bem: BemDetalhe | null;
  setores: Setor[]; locais: Local[]; produto: { id: number; rotulo: string } | null;
  aoEscolherProduto: (item: { id: number; nome: string } | null) => void;
}) {
  // 157: a primeira foto anexada é a capa da ficha.
  const foto = bem?.anexos?.find((a) => a.tipo === "FOTO");
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="flex min-w-0 flex-col gap-6">
        <Cartao titulo="Identificação">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Campo rotulo="Equipamento" className="sm:col-span-2">
              <input className="campo" id="bem-descricao" required maxLength={120} disabled={travado}
                     value={f.descricao ?? ""} onChange={muda("descricao")} />
            </Campo>
            <Campo rotulo="Produto (Patrimônio)" opcional className="sm:col-span-2"
                   dica="do tipo Patrimônio — num bem novo, a última entrada dele preenche a compra">
              <BuscaCadastro fonte={FONTE_PATRIMONIO} selecionado={produto} id="bem-produto"
                             disabled={travado} aoEscolher={aoEscolherProduto} />
            </Campo>
            <Campo rotulo="Código da casa" opcional dica="o da planilha (ex.: BAR-02)">
              <input className="campo mono" id="bem-apelido" maxLength={20} disabled={travado}
                     value={f.apelido ?? ""} onChange={muda("apelido")} />
            </Campo>
            <Campo rotulo="Marca" opcional>
              <input className="campo" maxLength={60} disabled={travado} value={f.marca ?? ""} onChange={muda("marca")} />
            </Campo>
            <Campo rotulo="Modelo" opcional>
              <input className="campo" maxLength={60} disabled={travado} value={f.modelo ?? ""} onChange={muda("modelo")} />
            </Campo>
            <Campo rotulo="Nº de série" opcional>
              <input className="campo mono" maxLength={60} disabled={travado}
                     value={f.numero_serie ?? ""} onChange={muda("numero_serie")} />
            </Campo>
            <Campo rotulo="Tensão" opcional>
              <select className="campo" disabled={travado} value={f.tensao ?? ""} onChange={muda("tensao")}>
                <option value="">—</option>
                {Object.entries(TENSOES).map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </Campo>
          </div>
        </Cartao>

        <Cartao titulo="Localização e status">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Campo rotulo="Setor" opcional>
              <select className="campo" id="bem-setor" disabled={travado} value={f.id_setor ?? ""} onChange={muda("id_setor")}>
                <option value="">—</option>
                {setores.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
              </select>
            </Campo>
            <Campo rotulo="Local" opcional dica="a câmara fria É o local: o estoque dela aparece aqui">
              <select className="campo" id="bem-local" disabled={travado} value={f.id_local ?? ""} onChange={muda("id_local")}>
                <option value="">—</option>
                {locais.map((l) => <option key={l.id} value={l.id}>{l.nome}</option>)}
              </select>
            </Campo>
            <Campo rotulo="Criticidade" opcional
                   dica="Alta: parar o equipamento para a venda ou estraga insumo. Média: atrapalha. Baixa: tem alternativa.">
              <select className="campo" id="bem-criticidade" disabled={travado}
                      value={f.criticidade ?? ""} onChange={muda("criticidade")}>
                <option value="">—</option>
                {Object.entries(CRITICIDADES).map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </Campo>
            <Campo rotulo="Responsável" opcional dica="quem responde pelo bem (texto livre)">
              <input className="campo" id="bem-responsavel" maxLength={120} disabled={travado}
                     value={f.responsavel ?? ""} onChange={muda("responsavel")} />
            </Campo>
            <Campo rotulo="Situação">
              <select className="campo" id="bem-situacao" disabled={travado}
                      value={f.situacao ?? "EM_USO"} onChange={muda("situacao")}>
                {Object.entries(SITUACOES).map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </Campo>
            {f.situacao === "BAIXADO" && (
              <>
                <Campo rotulo="Motivo da baixa" className="sm:col-span-2 lg:col-span-3"
                       dica="venda, descarte, perda, doação — o bem sai da lista, o histórico fica">
                  <input className="campo" id="bem-motivo-baixa" required maxLength={200} disabled={travado}
                         value={f.motivo_baixa ?? ""} onChange={muda("motivo_baixa")} />
                </Campo>
                <Campo rotulo="Data da baixa" opcional dica="vazia, fica hoje — a depreciação para nela">
                  <input type="date" className="campo" id="bem-data-baixa" max={hoje()} disabled={travado}
                         value={f.data_baixa ?? ""} onChange={muda("data_baixa")} />
                </Campo>
              </>
            )}
          </div>
        </Cartao>

        <Cartao titulo="Aquisição">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Campo rotulo="Data de compra" opcional>
              {/* 157: com o prazo em meses, a compra refaz a data final da garantia. */}
              <input type="date" className="campo" id="bem-data-compra" disabled={travado} value={f.data_compra ?? ""}
                     onChange={(e) => setF({
                       ...f, data_compra: e.target.value,
                       garantia_ate: f.garantia_meses ? somarMeses(e.target.value, f.garantia_meses) || f.garantia_ate : f.garantia_ate,
                     })} />
            </Campo>
            <Campo rotulo="Fornecedor da compra" opcional>
              <input className="campo" maxLength={120} disabled={travado} value={f.fornecedor ?? ""} onChange={muda("fornecedor")} />
            </Campo>
            <Campo rotulo="Nota fiscal" opcional>
              <input className="campo mono" maxLength={40} disabled={travado} value={f.nota_fiscal ?? ""} onChange={muda("nota_fiscal")} />
            </Campo>
            <Campo rotulo="Valor de compra" opcional>
              <CampoMoeda valor={f.valor_compra ?? ""} desabilitado={travado} aoMudar={(v) => setF({ ...f, valor_compra: v })} />
            </Campo>
            <Campo rotulo="Vida útil (anos)" opcional dica="vazia, 10 — o padrão da Receita para máquinas e móveis; computador é 5">
              <input type="number" min={1} max={50} className="campo" id="bem-vida-util" disabled={travado}
                     placeholder="10" value={f.vida_util_anos ?? ""} onChange={muda("vida_util_anos")} />
            </Campo>
            {bem && <div className="flex items-end sm:col-span-2 lg:col-span-3"><ValorDoBem bem={bem} id="bem-valor-atual" /></div>}
          </div>
        </Cartao>

        <Cartao titulo="Observações">
          <textarea className="campo min-h-[96px]" id="bem-observacao" maxLength={500} disabled={travado}
                    aria-label="Observações" value={f.observacao ?? ""} onChange={muda("observacao")} />
        </Cartao>
      </div>

      <aside className="flex min-w-0 flex-col gap-6">
        {foto && (
          <Cartao titulo="Foto">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`${urlArquivo(foto.url)}?w=640`} alt={`Foto de ${bem?.descricao ?? "bem"}`} id="bem-foto-capa"
                 className="aspect-[4/3] w-full rounded-lg border border-linha object-cover" />
          </Cartao>
        )}
        <Cartao titulo="Plaqueta">
          {bem ? (
            <>
              <PreviaPlaqueta bem={bem} />
              <p className="mt-3 text-[13px] text-suave" id="bem-conferido">
                {bem.conferido_em ? `Conferido em ${dataBr(bem.conferido_em)}` : "Nunca conferido"}
              </p>
            </>
          ) : (
            <p className="text-[13.5px] text-suave">O código da plaqueta (PAT-…) nasce ao cadastrar.</p>
          )}
        </Cartao>
      </aside>
    </div>
  );
}
