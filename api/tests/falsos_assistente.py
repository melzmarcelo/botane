"""A Meta (mídia) e o serviço de transcrição FALSOS, para a suíte do áudio do assistente (153).

🔑 Como a `AnthropicFalsa`: a API, em outro processo, é apontada para cá pela configuração do
assistente (`url_meta`, `url_transcricao`), que SÓ vale com DEBUG.

- `MetaFalsa`: `GET /v21.0/<id>` devolve a URL da mídia; `GET /midia/<id>` devolve os bytes.
  O id `expirada` dá 404; o id `longa` diz ter 50 MB; `silencio` transcreve vazio. Os bytes de um id são `AUDIO:<id>`.
- `TranscricaoFalsa`: `POST /audio/transcriptions` devolve como texto o que vem depois de
  `AUDIO:` nos bytes (com `_` virando espaço). `ocupado = True` responde 503.
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _servir(tratar):
    class Tratador(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _responder(self, status, corpo, tipo="application/json"):
            bruto = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(bruto)))
            self.end_headers()
            self.wfile.write(bruto)

        def do_GET(self):  # noqa: N802
            tratar(self, None)

        def do_POST(self):  # noqa: N802
            tratar(self, self.rfile.read(int(self.headers.get("Content-Length") or 0)))

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Tratador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, f"http://127.0.0.1:{servidor.server_address[1]}"


class MetaFalsa:
    def __init__(self):
        self.pedidos: list[dict] = []
        self.servidor, self.url = _servir(self._tratar)

    def fechar(self):
        self.servidor.shutdown()

    def _tratar(self, h, _corpo):
        self.pedidos.append({"caminho": h.path, "auth": h.headers.get("Authorization")})
        m = re.fullmatch(r"/v[\d.]+/([\w.-]+)", h.path)
        if m:
            mid = m.group(1)
            if mid == "expirada":
                return h._responder(404, {"error": {"message": "not found"}})
            tamanho = 50 * 1024 * 1024 if mid == "longa" else 100
            return h._responder(200, {"url": f"{self.url}/midia/{mid}", "mime_type": "audio/ogg; codecs=opus",
                                      "file_size": tamanho, "id": mid})
        m = re.fullmatch(r"/midia/([\w.-]+)", h.path)
        if m:
            return h._responder(200, f"AUDIO:{m.group(1)}".encode(), "audio/ogg")
        h._responder(404, {"error": "?"})


class TranscricaoFalsa:
    def __init__(self):
        self.pedidos: list[dict] = []
        self.ocupado = False
        self.servidor, base = _servir(self._tratar)
        self.url = base + "/v1"

    def fechar(self):
        self.servidor.shutdown()

    def _tratar(self, h, corpo):
        bruto = corpo or b""
        self.pedidos.append({"caminho": h.path, "auth": h.headers.get("Authorization"),
                             "tipo": h.headers.get("Content-Type", ""), "corpo": bruto})
        if self.ocupado:
            return h._responder(503, {"error": {"message": "ocupado"}})
        m = re.search(rb"AUDIO:([\w.-]*)", bruto)
        texto = (m.group(1).decode() if m else "").replace("_", " ")
        if texto == "silencio":   # o áudio em que ninguém fala nada
            texto = ""
        h._responder(200, {"text": texto})
