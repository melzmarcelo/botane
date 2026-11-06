"""Uma Anthropic falsa para as suítes do assistente (etapa 2, migração 152).

🔑 A API, rodando em outro processo, é apontada para cá pela configuração do assistente
(`url_api`, que SÓ vale com DEBUG). Assim a conversa inteira — webhook, fila, laço de
ferramentas com a credencial do usuário, resposta — roda sem gastar um centavo e sem depender
da internet. Os pedidos ficam em `pedidos` para a suíte conferir o que foi mandado.

O roteiro, pela última fala do usuário:
- tem resultado de ferramenta → responde "RESULTADO: <começo do resultado>";
- "agenda" → pede `agenda_producao`; "gravar" → pede `produzir` (que grava);
- "lance agenda N" → `produzir_da_agenda` da linha N; "produza P Q" → `produzir` do produto P;
- "ocupado" → 529 (sobrecarga); "recuse" → stop_reason refusal;
- o resto → "ok: <a fala>".
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class AnthropicFalsa:
    def __init__(self):
        self.pedidos: list[dict] = []
        self.cabecalhos: list[dict] = []
        dono = self

        class Tratador(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silêncio
                pass

            def do_POST(self):  # noqa: N802
                corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                dono.pedidos.append(corpo)
                dono.cabecalhos.append({k.lower(): v for k, v in self.headers.items()})
                status, resposta = dono.responder(corpo)
                bruto = json.dumps(resposta).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(bruto)))
                self.end_headers()
                self.wfile.write(bruto)

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Tratador)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}/v1/messages"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def fechar(self):
        self.servidor.shutdown()

    @staticmethod
    def _uso():
        return {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0}

    def responder(self, corpo: dict) -> tuple[int, dict]:
        ultima = corpo["messages"][-1]["content"]
        if isinstance(ultima, list):
            res = next((b for b in ultima if b.get("type") == "tool_result"), None)
            if res:
                return 200, self._texto(f"RESULTADO{' (erro)' if res.get('is_error') else ''}: "
                                        f"{str(res.get('content'))[:300]}")
            ultima = " ".join(b.get("text", "") for b in ultima if b.get("type") == "text")
        fala = ultima.lower()
        if "ocupado" in fala:
            return 529, {"type": "error", "error": {"type": "overloaded_error", "message": "x"}}
        if "recuse" in fala:
            return 200, {"content": [], "stop_reason": "refusal", "usage": self._uso()}
        # 154: os lançamentos — "lance agenda 12" e "produza 34 10" (produto 34, 10 unidades).
        m = re.search(r"lance agenda (\d+)", fala)
        if m:
            return 200, self._usar("produzir_da_agenda", {"id_agenda": int(m.group(1))})
        m = re.search(r"produza (\d+) ([\d.]+)", fala)
        if m:
            return 200, self._usar("produzir", {"id_produto": int(m.group(1)),
                                                "quantidade": float(m.group(2))})
        for gatilho, ferramenta in (("agenda", "agenda_producao"), ("gravar", "produzir")):
            if gatilho in fala:
                return 200, {"content": [{"type": "text", "text": "Vou ver."},
                                         {"type": "tool_use", "id": f"tu_{len(self.pedidos)}",
                                          "name": ferramenta, "input": {}}],
                             "stop_reason": "tool_use", "usage": self._uso()}
        return 200, self._texto("ok: " + ultima.split("\n\n", 1)[-1][:200])

    def _usar(self, ferramenta: str, entrada: dict) -> dict:
        return {"content": [{"type": "tool_use", "id": f"tu_{len(self.pedidos)}",
                             "name": ferramenta, "input": entrada}],
                "stop_reason": "tool_use", "usage": self._uso()}

    def _texto(self, t: str) -> dict:
        return {"content": [{"type": "text", "text": t}], "stop_reason": "end_turn",
                "usage": self._uso()}
