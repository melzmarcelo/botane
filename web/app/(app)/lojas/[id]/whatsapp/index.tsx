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
import HistoricoDoWhatsapp from "./historico";
import NumerosDoWhatsapp from "./numeros";

/**
 * A aba WhatsApp da loja: os números (cada um com a sua conexão com a Meta), avisos, teste e
 * histórico.
 *
 * 🔑 **Pedido do dono (28/09/2026):** *"API da Meta direto, com o número atual … tudo
 * configurável, numa aba nova dentro da loja: a loja faz toda a validação com a Meta e só
 * informa como vamos usar — fica configurável para outros clientes."*
 * 🔑 **146 (30/10/2026):** a conexão passou a ser de cada número, e cada aviso diz por qual
 * número sai. A lista de números, que estava no cadastro da loja, mora aqui.
 * ⚠️ **Modo simulado** até o número dizer "real": as mensagens vão só para o histórico. É o
 * que deixa montar e testar tudo antes de a conta na Meta ficar pronta.
 */
function paraForm(d: WhatsappDaLoja): GravarWhatsapp {
  return {
    numeros: d.numeros.map((n) => ({
      id: n.id, chave: String(n.id), rotulo: n.rotulo, numero: n.numero, principal: n.principal,
      conectado: n.conectado, modo: n.modo, phone_number_id: n.phone_number_id ?? "",
      waba_id: n.waba_id ?? "", api_versao: n.api_versao, token: "", app_secret: "",
      conta_do_principal: n.conta_do_principal,
    })),
    avisos: d.avisos.map((a) => ({
      evento: a.evento, ativo: a.ativo, modelo: a.modelo, idioma: a.idioma,
      antecedencia: a.antecedencia, whatsapp: a.id_whatsapp ? String(a.id_whatsapp) : null,
    })),
  };
}

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
    setForm(paraForm(d));
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
      const chaves = new Set(form.numeros.map((n) => n.chave));
      const r = await gravarWhatsapp(idLoja, {
        // Linha em branco (nem número, nem conexão) não vai.
        numeros: form.numeros.filter((n) => n.numero.trim() || n.phone_number_id.trim()),
        // Aviso apontando para um número removido volta ao principal.
        avisos: form.avisos.map((a) => ({ ...a, whatsapp: a.whatsapp && chaves.has(a.whatsapp) ? a.whatsapp : null })),
      });
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
      <NumerosDoWhatsapp lista={form.numeros} gravados={dados.numeros} webhookUrl={dados.webhook_url}
                         podeEditar={podeEditar} aoTrocar={(numeros) => setForm({ ...form, numeros })} />
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
