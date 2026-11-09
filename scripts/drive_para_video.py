#!/usr/bin/env python3
"""Converte o download do Google Drive (JSON com base64) no arquivo de vídeo original.

Uso: python scripts/drive_para_video.py <arquivo-json-do-download> <pasta-destino>
"""
import base64, json, os, sys

origem, destino = sys.argv[1], sys.argv[2]
with open(origem) as f:
    d = json.load(f)
os.makedirs(destino, exist_ok=True)
nome = os.path.basename(d.get("title") or d["id"]).strip() or d["id"]
caminho = os.path.join(destino, nome)
with open(caminho, "wb") as f:
    f.write(base64.b64decode(d["content"]))
print(caminho, os.path.getsize(caminho), "bytes")
