"""O termo de consentimento (LGPD) que o cliente aceita ao se cadastrar pelo site.

🔑 **Pedido do dono (24/09/2026):** *"no cadastro de cliente, adicionar o item Estou
de acordo com o termo de consentimento. O termo pode abrir em um popup"* — com a
estrutura do termo que ele usa hoje em outra plataforma (o que se coleta, para
quê, com quem se compartilha, segurança, guarda, direitos do titular, contato).
O texto abaixo é da casa, escrito para o que ESTE sistema de fato coleta.

⚠️ **O texto mora AQUI, e não no site**, porque o aceite grava a `VERSAO`: o que o
cliente leu e o que o cadastro diz que ele aceitou têm de sair do mesmo lugar.
🔑 **Mudou o texto, muda a `VERSAO`.** Os cadastros antigos continuam apontando
para a versão a que disseram sim.
"""

# 🔑 Histórico: "2026-09-24" (cadastro, reservas, cardápios); "2026-09-24.2" acrescenta
# o programa de fidelidade (check-in por visita, migração 091) — finalidade nova, e
# por isso quem aceitou a anterior aceita de novo antes do primeiro check-in.
VERSAO = "2026-09-24.2"


def termo(casa: str, razao_social: str | None, email: str | None,
          whatsapp: str | None) -> dict:
    """O termo pronto para o site desenhar, com o nome e o contato da casa."""
    controlador = casa + (f" ({razao_social})" if razao_social and razao_social != casa else "")
    contato = " ou ".join(
        c for c in (f"pelo e-mail {email}" if email else None,
                    f"pelo WhatsApp {whatsapp}" if whatsapp else None) if c
    ) or "pelos canais de atendimento da casa"
    return {
        "versao": VERSAO,
        "titulo": "Termo de consentimento para tratamento de dados pessoais",
        "secoes": [
            {"paragrafos": [
                f"Este termo explica como {controlador} coleta, usa e guarda os seus dados "
                "pessoais, de acordo com a Lei Geral de Proteção de Dados Pessoais "
                "(Lei nº 13.709/2018 — LGPD). Ao marcar que está de acordo, você autoriza o "
                "tratamento descrito abaixo.",
            ]},
            {"titulo": "Que dados coletamos", "itens": [
                "Os que você informa no cadastro: nome, telefone, gênero, cidade e data de "
                "nascimento.",
                "Os das suas reservas: dia, horário, número de pessoas, observações e o "
                "histórico de comparecimento e cancelamento.",
                "As suas visitas registradas no programa de fidelidade (dia e casa de cada "
                "check-in) e os prêmios ganhos e usados.",
                "O registro das conversas com a nossa equipe, por WhatsApp, telefone ou "
                "outro meio.",
            ]},
            {"titulo": "Para que usamos", "itens": [
                "Reconhecer você nas próximas visitas, sem pedir tudo de novo.",
                "Marcar, confirmar, remarcar e cancelar reservas, e falar com você sobre "
                "elas.",
                "Liberar o acesso a cardápios e catálogos que pedem cadastro.",
                "Manter o seu cartão fidelidade: contar as visitas, emitir e conferir os "
                "prêmios.",
                "Enviar novidades, eventos, ofertas e datas especiais (como o seu "
                "aniversário) por WhatsApp ou SMS. Você pode pedir para não receber a "
                "qualquer momento.",
            ]},
            {"titulo": "Com quem compartilhamos", "paragrafos": [
                "Seus dados ficam com a casa e não são vendidos nem cedidos a terceiros. Só "
                "são repassados quando a lei exigir — a autoridades, ao Judiciário ou por "
                "obrigação fiscal — ou quando você autorizar expressamente.",
            ]},
            {"titulo": "Segurança", "paragrafos": [
                "Os dados ficam em servidores protegidos, acessados apenas por quem precisa "
                "deles para atender você. Adotamos medidas técnicas e administrativas para "
                "evitar acesso não autorizado, perda ou uso indevido; nenhum sistema, porém, "
                "é totalmente inviolável.",
            ]},
            {"titulo": "Por quanto tempo guardamos", "paragrafos": [
                "Enquanto você mantiver o cadastro. Se pedir a exclusão, deixamos de usar "
                "seus dados na hora; guardamos apenas o que a lei nos obrigar a manter, e "
                "só pelo prazo exigido.",
            ]},
            {"titulo": "Seus direitos", "paragrafos": [
                "A qualquer momento, você pode pedir: confirmação de que tratamos seus "
                "dados; acesso a eles; correção do que estiver incompleto ou errado; "
                "anonimização, bloqueio ou eliminação do que for desnecessário; "
                "portabilidade; eliminação dos dados tratados com o seu consentimento; "
                "informação sobre com quem foram compartilhados; e a revogação deste "
                "consentimento. Sem o consentimento não conseguimos manter o cadastro "
                "nem as reservas pelo site — mas você pode reservar falando direto com a "
                "casa.",
            ]},
            {"titulo": "Como falar conosco", "paragrafos": [
                f"Para qualquer pedido sobre os seus dados, fale com {casa} {contato}.",
            ]},
            {"titulo": "Mudanças neste termo", "paragrafos": [
                "Este termo pode ser atualizado. A versão em vigor fica sempre disponível no "
                f"site, e a data da versão que você aceitou fica registrada. Versão: {VERSAO}.",
            ]},
        ],
    }
