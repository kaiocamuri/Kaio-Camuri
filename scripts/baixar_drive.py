#!/usr/bin/env python3
"""Baixa um arquivo (vídeo, foto...) de um link compartilhado do Google Drive.

O arquivo precisa estar compartilhado como "Qualquer pessoa com o link".
Sem limite de tamanho (o download é feito em partes, direto para o disco).

Uso: python scripts/baixar_drive.py "<link do Drive>" [pasta-destino]
"""
import os, re, sys, urllib.parse, urllib.request

def id_do_link(link):
    for padrao in (r"/d/([\w-]{20,})", r"[?&]id=([\w-]{20,})", r"^([\w-]{20,})$"):
        m = re.search(padrao, link.strip())
        if m:
            return m.group(1)
    sys.exit("Não achei o ID do arquivo nesse link.")

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    fid = id_do_link(sys.argv[1])
    destino = sys.argv[2] if len(sys.argv) > 2 else "midia"
    os.makedirs(destino, exist_ok=True)
    url = ("https://drive.usercontent.google.com/download?"
           + urllib.parse.urlencode({"id": fid, "export": "download", "confirm": "t"}))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        tipo = r.headers.get("Content-Type", "")
        if "text/html" in tipo:
            sys.exit("O Drive devolveu uma página em vez do arquivo. Verifique se o compartilhamento "
                     "está como 'Qualquer pessoa com o link'.")
        disp = r.headers.get("Content-Disposition", "")
        m = re.search(r"filename\*=UTF-8''([^;]+)", disp) or re.search(r'filename="([^"]+)"', disp)
        nome = os.path.basename(urllib.parse.unquote(m.group(1))) if m else fid
        total = int(r.headers.get("Content-Length") or 0)
        caminho = os.path.join(destino, nome)
        feito, proximo = 0, 0
        with open(caminho, "wb") as f:
            while bloco := r.read(1 << 20):
                f.write(bloco)
                feito += len(bloco)
                if feito >= proximo:
                    pct = f" ({feito * 100 // total}%)" if total else ""
                    print(f"  {feito / 1e6:.0f} MB{pct}", flush=True)
                    proximo += 50 << 20
    print(f"Pronto: {caminho} ({feito / 1e6:.1f} MB)")

if __name__ == "__main__":
    main()
