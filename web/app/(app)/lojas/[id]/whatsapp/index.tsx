"use client";

import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando } from "@/components/ui";
import {
  gravarWhatsapp,
  obterWhatsapp,
  type GravarWhatsapp,
  type WhatsappDaLoja,
} from "@/lib/whatsapp";

import AvisosDoWhatsapp from "./avisos";
import ConexaoDoWhatsapp from "./conexao";
import HistoricoDoWhatsapp from "./historico";

/**
 * A aba WhatsApp da loja: conexão com a Meta, avisos, teste e histórico.
 *
 * 🔑 **Pedido do dono (28/09/2026):** *"API da Meta direto, com o número atual … tudo
 * configurável, numa aba nova dentro da loja: a loja faz toda a validação com a Meta e só
 * informa como vamos usar — fica configurável para outros clientes."*
 * ⚠️ **Modo simulado** até a loja dizer "real": as mensagens vão só para o histórico. É o
 * que deixa montar e testar tudo antes de a conta na Meta ficar pronta.
 */
export default function WhatsappDaLojaAba({
  idLoja,
  podeEditar,
}: {
  idLoja: number;
  podeEditar: boolean;
}) {
  const aviso = useAviso();
  const [dados, setDados] = useState<WhatsappDaLoja | null>(null);
  const [form, setForm] = useState<GravarWhatsapp | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [versao, setVersao] = useState(0);

  function montar(d: WhatsappDaLoja) {
    setDados(d);
    setForm({
      ativa: d.ativa, modo: d.modo, phone_number_id: d.phone_number_id, waba_id: d.waba_id,
      numero: d.numero, api_versao: d.api_versao, token: "", app_secret: "",
      avisos: d.avisos.map((a) => ({
        evento: a.evento, ativo: a.ativo, modelo: a.modelo, idioma: a.idioma,
        antecedencia: a.antecedencia,
      })),
    });
  }

  useEffect(() => {
    obterWhatsapp(idLoja)
      .then(montar)
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar o WhatsApp"));
  }, [idLoja]);

  async function salvar() {
    if (!form) return;
    setOcupado(true);
    try {
      const r = await gravarWhatsapp(idLoja, form);
      montar(r);
      setVersao((v) => v + 1);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados || !form) return <Carregando />;

  return (
    <div className="flex flex-col gap-6">
      <ConexaoDoWhatsapp dados={dados} form={form} aoMudar={setForm} podeEditar={podeEditar} />
      <AvisosDoWhatsapp
        dados={dados}
        form={form}
        aoMudar={setForm}
        podeEditar={podeEditar}
        idLoja={idLoja}
        aoTestar={() => setVersao((v) => v + 1)}
      />
      {podeEditar && (
        <div className="sticky bottom-3 z-10 flex justify-end">
          <button className="btn btn-primario shadow-lg" onClick={() => void salvar()}
                  aria-busy={ocupado} disabled={ocupado}>
            {ocupado ? "…" : "Salvar WhatsApp"}
          </button>
        </div>
      )}
      <HistoricoDoWhatsapp idLoja={idLoja} versao={versao} />
    </div>
  );
}
