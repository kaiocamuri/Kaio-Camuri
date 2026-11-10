#!/usr/bin/env python3
"""Tour de imóvel no padrão House Brokers.

- Une vários vídeos como se fosse um só passeio (transição suave entre eles).
- Enquanto você anda: acelera para 10x (arrancada rápida).
- Quando você para para mostrar o ambiente: freia bruscamente para 1x.
- Legenda de cada cômodo nas paradas, título de abertura, logo branco a 20%
  no canto, cartela final com logo + mascote e trilha de blues ao fundo.

Fluxo em 2 passos:
  1) python efeitos/tour_imovel.py analisar  video1.mov video2.mov --saida tour.json
     -> detecta trechos andando/parado e gera uma folha com 1 quadro por parada
        (tour_paradas.jpg) para identificar cada cômodo.
  2) edite "legendas" no tour.json e rode:
     python efeitos/tour_imovel.py renderizar tour.json --saida tour.mp4
"""
import argparse
import json
import math
import os
import subprocess
import sys
from collections import deque

import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FF = imageio_ffmpeg.get_ffmpeg_exe()
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
MARCA = os.path.join(RAIZ, "midia", "marca")
F_BLACK = "/usr/share/fonts/opentype/montserrat/Montserrat-Black.otf"
F_MEDIUM = "/usr/share/fonts/opentype/montserrat/Montserrat-Medium.otf"
LARANJA = (246, 139, 31)
AZUL = (0, 24, 39)


# ------------------------------------------------------------------ leitura
def info_video(caminho):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:stream_side_data=rotation:format=duration",
                          "-of", "json", caminho], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    s = d["streams"][0]
    num, den = map(int, s["r_frame_rate"].split("/"))
    w, h = s["width"], s["height"]
    rot = 0
    for sd in s.get("side_data_list", []) or []:
        rot = int(sd.get("rotation", 0) or 0)
    if abs(rot) in (90, 270):
        w, h = h, w
    return {"w": w, "h": h, "fps": num / den, "duracao": float(d["format"]["duration"])}


def ler_quadros(caminho, w, h, fps=None, cinza=False):
    """Gera quadros (numpy) já redimensionados, preenchendo w x h (corte central)."""
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    if fps:
        vf += f",fps={fps}"
    fmt, canais = ("gray", 1) if cinza else ("rgb24", 3)
    p = subprocess.Popen([FF, "-v", "error", "-i", caminho, "-vf", vf, "-f", "rawvideo",
                          "-pix_fmt", fmt, "-"], stdout=subprocess.PIPE, bufsize=10 ** 8)
    tam = w * h * canais
    try:
        while True:
            b = p.stdout.read(tam)
            if len(b) < tam:
                break
            q = np.frombuffer(b, np.uint8).reshape(h, w, canais) if canais > 1 else np.frombuffer(b, np.uint8).reshape(h, w)
            yield q
    finally:
        p.stdout.close()
        p.wait()


# ---------------------------------------------------------------- análise
def analisar(args):
    clipes = []
    for caminho in args.videos:
        inf = info_video(caminho)
        fps_a = 10  # análise a 10 quadros/s é suficiente
        w = 160
        h = int(round(w * inf["h"] / inf["w"] / 2) * 2)
        movimento, anterior = [], None
        for q in ler_quadros(caminho, w, h, fps=fps_a, cinza=True):
            if anterior is not None:
                fluxo = cv2.calcOpticalFlowFarneback(anterior, q, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                movimento.append(float(np.median(np.linalg.norm(fluxo, axis=2))))
            anterior = q
        mov = np.array(movimento or [0.0])
        k = max(1, int(fps_a * 0.8))
        suave = np.convolve(mov, np.ones(k) / k, mode="same")
        clipes.append({"arquivo": os.path.abspath(caminho), **inf, "_mov": suave, "_fps_a": fps_a})
        print(f"  analisado: {os.path.basename(caminho)} ({inf['duracao']:.1f}s, {inf['w']}x{inf['h']})")

    # limiar automático único para todos os clipes (separa "andando" de "parado")
    todos = np.concatenate([c["_mov"] for c in clipes])
    baixo, alto = np.percentile(todos, 15), np.percentile(todos, 85)
    limiar = args.limiar if args.limiar else baixo + (alto - baixo) * 0.35

    n_parada = 0
    for c in clipes:
        andando = c["_mov"] > limiar
        t = np.arange(len(andando)) / c["_fps_a"]
        segs = []
        for i, a in enumerate(andando):
            tipo = "andando" if a else "parado"
            if segs and segs[-1]["tipo"] == tipo:
                segs[-1]["fim"] = float(t[i] + 1 / c["_fps_a"])
            else:
                segs.append({"tipo": tipo, "ini": float(t[i]), "fim": float(t[i] + 1 / c["_fps_a"])})
        # limpa: paradas muito curtas viram caminhada e vice-versa
        mudou = True
        while mudou and len(segs) > 1:
            mudou = False
            for i, s in enumerate(segs):
                minimo = args.parada_minima if s["tipo"] == "parado" else 0.6
                if s["fim"] - s["ini"] < minimo:
                    novo = "andando" if s["tipo"] == "parado" else "parado"
                    s["tipo"] = novo
                    mudou = True
            junt = []
            for s in segs:
                if junt and junt[-1]["tipo"] == s["tipo"]:
                    junt[-1]["fim"] = s["fim"]
                else:
                    junt.append(dict(s))
            segs = junt
        segs[-1]["fim"] = c["duracao"]
        for s in segs:
            if s["tipo"] == "parado":
                s["parada"] = n_parada
                n_parada += 1
            s["ini"], s["fim"] = round(s["ini"], 2), round(s["fim"], 2)
        c["segmentos"] = segs
        del c["_mov"], c["_fps_a"]

    cfg = {
        "clipes": clipes,
        "aceleracao": 10,
        "titulo": "SOBRADO",
        "subtitulo": "Santa Mônica II",
        "legendas": [{"parada": i, "titulo": f"Parada {i}", "sub": ""} for i in range(n_parada)],
        "logo_marca_dagua": os.path.join(MARCA, "logo_branco.png"),
        "opacidade_logo": 0.20,
        "cartela_logo": os.path.join(MARCA, "logo_cor.png"),
        "cartela_mascote": "",
        "cartela_texto": "",
        "musica": "",
        "limiar_movimento": round(float(limiar), 3),
    }
    with open(args.saida, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    folha_paradas(cfg, os.path.splitext(args.saida)[0] + "_paradas.jpg")
    print(f"{n_parada} paradas encontradas. Configuração: {args.saida}")


def folha_paradas(cfg, caminho):
    miniaturas = []
    for c in cfg["clipes"]:
        for s in c["segmentos"]:
            if s["tipo"] != "parado":
                continue
            t = (s["ini"] + s["fim"]) / 2
            w = 360
            h = int(w * c["h"] / c["w"])
            out = subprocess.run([FF, "-v", "error", "-ss", f"{t:.2f}", "-i", c["arquivo"], "-frames:v", "1",
                                  "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                 capture_output=True).stdout
            if len(out) < w * h * 3:
                continue
            img = Image.fromarray(np.frombuffer(out[:w * h * 3], np.uint8).reshape(h, w, 3))
            d = ImageDraw.Draw(img)
            d.rectangle([0, 0, w, 34], fill=(0, 0, 0))
            d.text((8, 4), f"#{s['parada']}  {os.path.basename(c['arquivo'])} {s['ini']:.0f}-{s['fim']:.0f}s",
                   font=ImageFont.truetype(F_MEDIUM, 20), fill=(255, 255, 255))
            miniaturas.append(img)
    if not miniaturas:
        return
    col = 4
    lin = math.ceil(len(miniaturas) / col)
    mw, mh = miniaturas[0].size
    folha = Image.new("RGB", (col * mw, lin * mh), (40, 40, 40))
    for i, m in enumerate(miniaturas):
        folha.paste(m.resize((mw, mh)), ((i % col) * mw, (i // col) * mh))
    folha.save(caminho, quality=85)
    print(f"Folha de paradas: {caminho}")


# ------------------------------------------------------- linha do tempo
def simular(c, fps_out, vmax, acel=20.0, freio=70.0):
    """Velocidade de reprodução quadro a quadro (posição no vídeo original).

    acel: quanto a velocidade sobe por segundo (1x -> 10x em ~0,45 s).
    freio: quanto desce por segundo (10x -> 1x em ~0,13 s: freada brusca).
    """
    segs = c["segmentos"]
    dur = c["duracao"]
    dt = 1 / fps_out
    s, v = 0.0, 1.0 if segs[0]["tipo"] == "parado" else vmax
    pos, paradas = [], {}

    def seg_em(x):
        for sg in segs:
            if sg["ini"] <= x < sg["fim"]:
                return sg
        return segs[-1]

    while s < dur - 1e-3:
        sg = seg_em(s)
        if sg["tipo"] == "parado":
            v = 1.0
            paradas.setdefault(sg["parada"], [len(pos), len(pos)])[1] = len(pos)
        else:
            prox = next((x for x in segs if x["ini"] >= sg["fim"] - 1e-6 and x["tipo"] == "parado"), None)
            dist = (prox["ini"] - s) if prox else 1e9
            dist_freio = (v * v - 1) / (2 * freio)
            if dist <= dist_freio + v * dt:
                v = max(1.0, v - freio * dt)
            else:
                v = min(vmax, v + acel * dt)
        passo = v * dt
        pos.append((s, min(dur, s + passo)))
        s += passo
    return pos, paradas


# ------------------------------------------------------------ gráficos
def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def caixa_legenda(titulo, sub, largura_tela):
    """Lower-third no padrão da marca: barra laranja 3px, caixa azul com cantos 10px."""
    esc = largura_tela / 1080
    ft = ImageFont.truetype(F_BLACK, int(58 * esc))
    fs = ImageFont.truetype(F_MEDIUM, int(32 * esc))
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    titulo = titulo.upper()
    bt = tmp.textbbox((0, 0), titulo, font=ft)
    bs = tmp.textbbox((0, 0), sub, font=fs) if sub else (0, 0, 0, 0)
    pad = int(30 * esc)
    w = max(bt[2], bs[2]) + pad * 2 + int(14 * esc)
    h = (bt[3] - bt[1]) + ((bs[3] - bs[1]) + int(16 * esc) if sub else 0) + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(10 * esc), fill=AZUL + (215,))
    d.rounded_rectangle([0, 0, int(10 * esc), h - 1], radius=int(5 * esc), fill=LARANJA + (255,))
    x = pad + int(10 * esc)
    d.text((x, pad - bt[1]), titulo, font=ft, fill=(255, 255, 255, 255))
    if sub:
        y = pad + (bt[3] - bt[1]) + int(16 * esc)
        d.text((x, y - bs[1]), sub, font=fs, fill=LARANJA + (255,))
    return np.asarray(img)


def carregar_logo(caminho, largura, opacidade=1.0):
    img = Image.open(caminho).convert("RGBA")
    a = largura / img.width
    img = img.resize((int(img.width * a), int(img.height * a)), Image.LANCZOS)
    arr = np.asarray(img).astype(np.float32)
    arr[..., 3] *= opacidade
    return arr.astype(np.uint8)


def colar(fundo, rgba, x, y, alfa=1.0):
    """Cola imagem RGBA (numpy) sobre o quadro (float 0-255)."""
    h, w = rgba.shape[:2]
    H, W = fundo.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    if x0 >= x1 or y0 >= y1 or alfa <= 0:
        return
    rec = rgba[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    a = rec[..., 3:4] / 255.0 * alfa
    fundo[y0:y1, x0:x1] = fundo[y0:y1, x0:x1] * (1 - a) + rec[..., :3] * a


def cartela_final(W, H, cfg, dur, fps):
    """Cartela final: fundo azul da marca, padrão de linhas, logo + mascote."""
    base = Image.new("RGB", (W, H), AZUL)
    d = ImageDraw.Draw(base)
    esc = min(W, H) / 1080
    # padrão de repetição discreto (linhas 3px, cantos 10px, como no manual)
    rng = np.random.default_rng(4)
    for _ in range(14):
        x, y = rng.integers(-100, W), rng.integers(-100, H)
        w, h = rng.integers(120, 380) * esc, rng.integers(120, 380) * esc
        d.rounded_rectangle([x, y, x + w, y + h], radius=int(10 * esc), outline=(18, 48, 66), width=max(2, int(3 * esc)))
    base = np.asarray(base).astype(np.float32)
    vertical = H > W
    logo = carregar_logo(cfg["cartela_logo"], int(W * (0.62 if vertical else 0.36)))
    masc = None
    if cfg.get("cartela_mascote") and os.path.exists(cfg["cartela_mascote"]):
        im = Image.open(cfg["cartela_mascote"]).convert("RGBA")
        alt = int(H * (0.36 if vertical else 0.55))
        im = im.resize((int(im.width * alt / im.height), alt), Image.LANCZOS)
        masc = np.asarray(im)
    texto = cfg.get("cartela_texto", "")
    quadros = int(dur * fps)
    for i in range(quadros):
        t = i / fps
        f = base.copy()
        a_logo = ease(t / 0.6)
        if vertical:
            ly = int(H * 0.22) + int((1 - a_logo) * 40 * esc)
            lx = (W - logo.shape[1]) // 2
            if masc is not None:
                colar(f, masc, (W - masc.shape[1]) // 2, int(H * 0.50) + int((1 - ease((t - 0.3) / 0.6)) * 80 * esc),
                      ease((t - 0.3) / 0.6))
        else:
            lx = int(W * 0.08) if masc is not None else (W - logo.shape[1]) // 2
            ly = (H - logo.shape[0]) // 2 + int((1 - a_logo) * 40 * esc)
            if masc is not None:
                colar(f, masc, int(W * 0.62), (H - masc.shape[0]) // 2 + int((1 - ease((t - 0.3) / 0.6)) * 60 * esc),
                      ease((t - 0.3) / 0.6))
        colar(f, logo, lx, ly, a_logo)
        if texto:
            img = Image.new("RGBA", (W, int(80 * esc)), (0, 0, 0, 0))
            dd = ImageDraw.Draw(img)
            fnt = ImageFont.truetype(F_MEDIUM, int(36 * esc))
            bb = dd.textbbox((0, 0), texto, font=fnt)
            dd.text(((W - bb[2]) // 2, 10), texto, font=fnt, fill=(255, 255, 255, 255))
            colar(f, np.asarray(img), 0, int(H * (0.90 if vertical else 0.85)), ease((t - 0.6) / 0.5))
        yield f


# ------------------------------------------------------------ renderizar
def renderizar(args):
    with open(args.config) as f:
        cfg = json.load(f)
    c0 = cfg["clipes"][0]
    vertical = c0["h"] > c0["w"]
    W, H = (1080, 1920) if vertical else (1920, 1080)
    if args.previa:
        W, H = W // 2, H // 2
    fps = 30
    vmax = float(cfg.get("aceleracao", 10))
    trans = int(0.35 * fps)  # quadros de transição entre vídeos

    # 1) linha do tempo completa (sem decodificar nada ainda)
    planos, paradas_glob, inicio = [], {}, 0
    for k, c in enumerate(cfg["clipes"]):
        pos, paradas = simular(c, fps, vmax)
        if k > 0:
            inicio -= trans
        planos.append((c, pos, inicio))
        for p, (a, b) in paradas.items():
            paradas_glob[p] = (inicio + a, inicio + b)
        inicio += len(pos)
    total_video = inicio
    dur_cartela = 4.0
    total = total_video + int(dur_cartela * fps)
    print(f"Duração final: {total / fps:.1f}s ({len(paradas_glob)} paradas, cartela {dur_cartela:.0f}s)")

    # 2) gráficos
    marca = carregar_logo(cfg["logo_marca_dagua"], int(W * (0.24 if vertical else 0.14)), cfg.get("opacidade_logo", 0.2))
    mx, my = W - marca.shape[1] - int(W * 0.05), int(H * 0.035)
    legendas = []
    for lg in cfg["legendas"]:
        if lg["parada"] in paradas_glob and lg.get("titulo"):
            a, b = paradas_glob[lg["parada"]]
            legendas.append((a, b, caixa_legenda(lg["titulo"], lg.get("sub", ""), W)))
    intro = caixa_legenda(cfg.get("titulo", ""), cfg.get("subtitulo", ""), int(W * 1.25)) if cfg.get("titulo") else None

    def sobrepor(f, i):
        if i < total_video:  # na cartela final o logo grande já aparece
            colar(f, marca, mx, my, 1 - ease((i - (total_video - 12)) / 12))
        if intro is not None and i < 4.0 * fps:
            t = i / fps
            al = ease(t / 0.5) * (1 - ease((t - 3.4) / 0.5))
            colar(f, intro, int(W * 0.06) - int((1 - ease(t / 0.5)) * 60), int(H * 0.56), al)
        for a, b, img in legendas:
            if a - 2 <= i <= b:
                t_in = (i - a) / fps
                t_out = (b - i) / fps
                al = ease((t_in - 0.15) / 0.3) * ease(t_out / 0.3)
                desl = int((1 - ease((t_in - 0.15) / 0.35)) * 50)
                colar(f, img, int(W * 0.06) - desl, int(H * 0.76), al)
        return f

    # 3) quadros de vídeo com borrão de movimento nos trechos acelerados
    def quadros_clipe(c, pos):
        leitor = ler_quadros(c["arquivo"], W, H)
        fps_in = c["fps"]
        buf, idx = deque(), -1
        ultimo = None
        for s0, s1 in pos:
            a, b = int(s0 * fps_in), max(int(s0 * fps_in), int(s1 * fps_in) - 1)
            while idx < b:
                q = next(leitor, None)
                if q is None:
                    break
                idx += 1
                buf.append((idx, q))
            while buf and buf[0][0] < a:
                buf.popleft()
            sel = [q for j, q in buf if a <= j <= b] or ([buf[-1][1]] if buf else [ultimo])
            if len(sel) > 6:
                sel = [sel[int(t)] for t in np.linspace(0, len(sel) - 1, 6)]
            ultimo = sel[-1]
            yield np.mean(np.stack(sel).astype(np.float32), axis=0) if len(sel) > 1 else sel[0].astype(np.float32)

    saida_tmp = args.saida + ".video.mp4"
    enc = subprocess.Popen([FF, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                            "-pix_fmt", "yuv420p", saida_tmp], stdin=subprocess.PIPE)
    i_out = 0

    def emitir(f):
        nonlocal i_out
        enc.stdin.write(np.clip(sobrepor(f, i_out), 0, 255).astype(np.uint8).tobytes())
        i_out += 1
        if i_out % (fps * 5) == 0:
            print(f"  {i_out / fps:5.1f}s / {total / fps:.1f}s", flush=True)

    cauda = deque()
    for k, (c, pos, _) in enumerate(planos):
        gen = quadros_clipe(c, pos)
        if cauda:  # dissolve curto entre o fim de um vídeo e o começo do próximo
            n = len(cauda)
            for j in range(n):
                q = next(gen, None)
                a = (j + 1) / (n + 1)
                f_ant = cauda.popleft()
                emitir(f_ant if q is None else f_ant * (1 - a) + q * a)
        ultimo_clipe = k == len(planos) - 1
        for q in gen:
            if not ultimo_clipe:
                cauda.append(q)
                if len(cauda) > trans:
                    emitir(cauda.popleft())
            else:
                emitir(q)
                ultimo_q = q
    # dissolve do vídeo para a cartela
    cart = list(cartela_final(W, H, cfg, dur_cartela, fps))
    for j, f in enumerate(cart):
        if j < 12:
            a = (j + 1) / 13
            f = ultimo_q * (1 - a) + f * a
        emitir(f)
    enc.stdin.close()
    enc.wait()

    # 4) trilha
    dur_total = i_out / fps
    musica = cfg.get("musica")
    tmp_mus = None
    if not musica or not os.path.exists(musica):
        tmp_mus = args.saida + ".blues.wav"
        subprocess.run([sys.executable, os.path.join(AQUI, "musica_blues.py"), "--duracao", str(dur_total),
                        "--saida", tmp_mus], check=True)
        musica = tmp_mus
    subprocess.run([FF, "-y", "-v", "error", "-i", saida_tmp, "-i", musica, "-filter_complex",
                    f"[1:a]atrim=0:{dur_total},afade=t=in:d=0.5,afade=t=out:st={dur_total - 2.5}:d=2.5[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", "-shortest", args.saida], check=True)
    os.remove(saida_tmp)
    if tmp_mus:
        os.remove(tmp_mus)
    print(f"Pronto: {args.saida} ({dur_total:.1f}s, {W}x{H})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analisar")
    a.add_argument("videos", nargs="+")
    a.add_argument("--saida", default="tour.json")
    a.add_argument("--limiar", type=float, help="força o limiar de movimento (padrão: automático)")
    a.add_argument("--parada-minima", type=float, default=1.5, help="segundos mínimos para contar como parada")
    r = sub.add_parser("renderizar")
    r.add_argument("config")
    r.add_argument("--saida", default="tour.mp4")
    r.add_argument("--previa", action="store_true", help="meia resolução, mais rápido")
    args = ap.parse_args()
    analisar(args) if args.cmd == "analisar" else renderizar(args)


if __name__ == "__main__":
    main()
