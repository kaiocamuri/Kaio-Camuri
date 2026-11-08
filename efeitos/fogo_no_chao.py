#!/usr/bin/env python3
"""Escreve um texto pegando fogo no chão de um vídeo.

O texto acende da esquerda para a direita, como se alguém riscasse o chão
com gasolina e ateasse fogo. Inclui chamas, brasas subindo, luz alaranjada
refletida no chão e marca de queimado nas letras.

Exemplos:
  # Demonstração (gera um chão de concreto sintético)
  python efeitos/fogo_no_chao.py --texto "KAIO" --saida fogo.mp4

  # No seu vídeo (câmera parada). --cantos = área do chão onde vai o texto,
  # em pixels: sup-esq  sup-dir  inf-dir  inf-esq
  python efeitos/fogo_no_chao.py --entrada chao.mp4 --texto "KAIO" \
      --cantos "420,560 860,560 1100,700 180,700" --saida fogo.mp4
"""
import argparse
import subprocess
import wave

import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


# ---------------------------------------------------------------- utilidades
def ruido_suave(h, w, escala, rng):
    """Ruído contínuo (valor entre 0 e 1) do tamanho h x w."""
    pequeno = rng.random((max(2, h // escala), max(2, w // escala))).astype(np.float32)
    return cv2.resize(pequeno, (w, h), interpolation=cv2.INTER_CUBIC).clip(0, 1)


def paleta_fogo():
    """Tabela de 256 cores: preto -> vermelho -> laranja -> amarelo -> branco."""
    pontos = [(0.00, (0, 0, 0)), (0.25, (120, 10, 0)), (0.45, (220, 60, 5)),
              (0.65, (255, 140, 20)), (0.85, (255, 220, 90)), (1.00, (255, 255, 230))]
    x = np.linspace(0, 1, 256)
    tabela = np.zeros((256, 3), np.float32)
    for c in range(3):
        tabela[:, c] = np.interp(x, [p[0] for p in pontos], [p[1][c] for p in pontos])
    return tabela / 255.0


def mascara_texto(texto, largura=2400, altura=600):
    """Desenha o texto (branco no preto) numa imagem plana, vista de cima."""
    img = Image.new("L", (largura, altura), 0)
    d = ImageDraw.Draw(img)
    tamanho = 500
    while True:
        fonte = ImageFont.truetype(FONTE, tamanho)
        x0, y0, x1, y1 = d.textbbox((0, 0), texto, font=fonte, stroke_width=0)
        if x1 - x0 < largura * 0.92 and y1 - y0 < altura * 0.85:
            break
        tamanho -= 10
    d.text(((largura - (x1 - x0)) / 2 - x0, (altura - (y1 - y0)) / 2 - y0), texto,
           font=fonte, fill=255)
    m = np.asarray(img, np.float32) / 255.0
    # A gasolina queima numa faixa: deixa só um contorno grosso das letras
    nucleo = cv2.erode(m, np.ones((25, 25), np.uint8))
    return np.clip(m - 0.65 * nucleo, 0, 1)


def chao_demo(w, h, cantos, rng):
    """Gera um piso de concreto escuro em perspectiva, com vinheta."""
    tw, th = 2400, 1800
    base = 0.18 + 0.10 * ruido_suave(th, tw, 120, rng) + 0.05 * ruido_suave(th, tw, 12, rng)
    base += 0.03 * rng.standard_normal((th, tw)).astype(np.float32)
    for x in range(0, tw, 400):  # juntas de dilatação do concreto
        base[:, x:x + 4] *= 0.6
    for y in range(0, th, 400):
        base[y:y + 4, :] *= 0.6
    textura = np.dstack([base * 0.95, base, base * 1.05]).clip(0, 1)
    # mapeia a textura para a metade de baixo da tela, com o horizonte ao fundo
    origem = np.float32([[0, 0], [tw, 0], [tw, th], [0, th]])
    destino = np.float32([[w * 0.30, h * 0.42], [w * 0.70, h * 0.42],
                          [w * 1.60, h * 1.15], [-w * 0.60, h * 1.15]])
    H = cv2.getPerspectiveTransform(origem, destino)
    chao = cv2.warpPerspective(textura, H, (w, h), borderValue=(0, 0, 0))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ceu = np.clip((h * 0.46 - yy) / (h * 0.46), 0, 1)[..., None]
    chao = chao * (1 - ceu) + ceu * np.array([0.03, 0.03, 0.04], np.float32)
    vinheta = 1 - 0.55 * (((xx - w / 2) / w) ** 2 + ((yy - h * 0.7) / h) ** 2) * 2.2
    return np.clip(chao * vinheta[..., None], 0, 1)


def som_de_fogo(caminho, duracao, inicio, sr=44100, seed=1):
    """Sintetiza um som de fogo (rugido grave + estalos) em WAV."""
    rng = np.random.default_rng(seed)
    n = int(duracao * sr)
    ruido = rng.standard_normal(n).astype(np.float32)
    rugido = np.cumsum(ruido)
    rugido -= cv2.blur(rugido.reshape(1, -1), (2001, 1)).ravel()
    rugido /= np.abs(rugido).max() + 1e-6
    estalos = np.zeros(n, np.float32)
    for pos in rng.integers(int(inicio * sr), n, size=int(duracao * 18)):
        tam = rng.integers(80, 600)
        fim = min(n, pos + tam)
        estalos[pos:fim] += rng.standard_normal(fim - pos) * np.exp(-np.arange(fim - pos) / (tam / 5)) * rng.uniform(0.2, 1)
    t = np.arange(n) / sr
    env = np.clip((t - inicio + 0.3) / 0.6, 0, 1)  # entra junto com o fogo
    sinal = (0.55 * rugido + 0.35 * estalos) * env
    sinal = (sinal / (np.abs(sinal).max() + 1e-6) * 0.8 * 32767).astype(np.int16)
    with wave.open(caminho, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr); f.writeframes(sinal.tobytes())


# ------------------------------------------------------------------- efeito
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--texto", default="KAIO")
    ap.add_argument("--entrada", help="vídeo de fundo (opcional; sem ele gera um chão demo)")
    ap.add_argument("--saida", default="fogo_no_chao.mp4")
    ap.add_argument("--cantos", help='área do texto no chão: "x,y x,y x,y x,y" (sup-esq sup-dir inf-dir inf-esq)')
    ap.add_argument("--duracao", type=float, default=6.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--tamanho", default="1280x720", help="só para o modo demo")
    ap.add_argument("--inicio", type=float, default=0.6, help="segundo em que o fogo acende")
    ap.add_argument("--acender", type=float, default=1.6, help="segundos para o fogo percorrer o texto")
    ap.add_argument("--altura-chama", type=float, default=1.0, help="multiplicador do tamanho das chamas")
    ap.add_argument("--sem-som", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    rng = np.random.default_rng(a.seed)
    cap = None
    if a.entrada:
        cap = cv2.VideoCapture(a.entrada)
        w, h = int(cap.get(3)), int(cap.get(4))
        a.fps = int(round(cap.get(cv2.CAP_PROP_FPS))) or a.fps
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        a.duracao = min(a.duracao, total / a.fps) if total > 0 else a.duracao
    else:
        w, h = map(int, a.tamanho.split("x"))

    if a.cantos:
        cantos = np.float32([list(map(float, p.split(","))) for p in a.cantos.split()])
    else:  # padrão: faixa centralizada no chão, à frente da câmera
        cantos = np.float32([[w * 0.27, h * 0.60], [w * 0.73, h * 0.60],
                             [w * 0.90, h * 0.84], [w * 0.10, h * 0.84]])

    fundo_fixo = None if cap else chao_demo(w, h, cantos, rng)

    # Texto no plano do chão -> tela
    mt = mascara_texto(a.texto)
    th_, tw_ = mt.shape
    Hm = cv2.getPerspectiveTransform(np.float32([[0, 0], [tw_, 0], [tw_, th_], [0, th_]]), cantos)
    coluna = np.tile(np.linspace(0, 1, tw_, dtype=np.float32), (th_, 1))  # posição esq->dir
    tela_txt = cv2.warpPerspective(mt, Hm, (w, h))
    tela_col = cv2.warpPerspective(coluna, Hm, (w, h), borderValue=2)

    # Simulação em meia resolução (mais rápida)
    s = 2
    sw, sh = w // s, h // s
    calor = np.zeros((sh, sw), np.float32)
    yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
    escala_chama = (cantos[3, 1] - cantos[0, 1]) / h  # chamas maiores perto da câmera
    sobe = 2.2 * a.altura_chama * (0.6 + escala_chama * 2)
    paleta = paleta_fogo()

    # ruídos que "rolam" para cima, dão a cara de chama
    rd_grande = ruido_suave(sh * 3, sw, 18, rng)
    rd_fino = ruido_suave(sh * 3, sw, 6, rng)
    faiscas = np.zeros((0, 4), np.float32)  # x, y, vida, velocidade

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    tmp_video = a.saida + ".semsom.mp4"
    enc = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{w}x{h}", "-r", str(a.fps), "-i", "-",
                            "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                            tmp_video], stdin=subprocess.PIPE)

    n_quadros = int(a.duracao * a.fps)
    queimado = np.zeros((h, w), np.float32)
    for i in range(n_quadros):
        t = i / a.fps
        if cap:
            ok, bgr = cap.read()
            if not ok:
                break
            fundo = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        else:
            fundo = fundo_fixo

        # frente do fogo percorrendo o texto da esquerda para a direita
        progresso = np.clip((t - a.inicio) / a.acender, 0, 1.05)
        aceso = np.clip((progresso - tela_col) * 25, 0, 1) * tela_txt
        queimado = np.maximum(queimado, aceso)
        frente = np.exp(-((tela_col - progresso) * 18) ** 2) * tela_txt * (progresso < 1)

        aceso_s = cv2.resize(aceso, (sw, sh), interpolation=cv2.INTER_AREA)
        frente_s = cv2.resize(frente, (sw, sh), interpolation=cv2.INTER_AREA)

        # ruído do quadro (rolando para cima com o tempo)
        off = int(t * 140) % (sh * 2)
        n1 = rd_grande[off:off + sh]
        n2 = rd_fino[(off * 2) % (sh * 2):(off * 2) % (sh * 2) + sh]

        # advecção: o calor sobe e balança de lado
        mapa_y = yy + sobe * (0.6 + 0.9 * n2)
        mapa_x = xx + (n1 - 0.5) * 3.0
        calor = cv2.remap(calor, mapa_x, mapa_y, cv2.INTER_LINEAR, borderValue=0)
        calor *= 0.955 - 0.05 * n2  # esfria enquanto sobe
        cintilar = 0.75 + 0.5 * n1
        calor = np.maximum(calor, (aceso_s * 0.85 + frente_s * 0.6) * cintilar)
        calor = cv2.GaussianBlur(calor, (3, 3), 0)

        fogo_s = paleta[np.clip(calor * 255, 0, 255).astype(np.uint8)]
        fogo = cv2.resize(fogo_s, (w, h), interpolation=cv2.INTER_LINEAR)

        # brasas: nascem nas letras acesas e sobem
        ys, xs = np.nonzero(aceso_s > 0.3)
        if len(xs):
            k = rng.integers(0, len(xs), size=min(len(xs), 6))
            novas = np.column_stack([xs[k] * s, ys[k] * s, np.ones(len(k)), rng.uniform(1.5, 4.5, len(k))])
            faiscas = np.vstack([faiscas, novas.astype(np.float32)])
        if len(faiscas):
            faiscas[:, 1] -= faiscas[:, 3]
            faiscas[:, 0] += rng.normal(0, 1.2, len(faiscas))
            faiscas[:, 2] -= 1 / (a.fps * rng.uniform(0.8, 1.8, len(faiscas)))
            faiscas = faiscas[(faiscas[:, 2] > 0) & (faiscas[:, 1] > 0)]
        camada_brasa = np.zeros((h, w), np.float32)
        for x, y, vida, _ in faiscas:
            cv2.circle(camada_brasa, (int(x), int(y)), 1 if vida < 0.5 else 2, float(vida), -1, cv2.LINE_AA)
        camada_brasa = cv2.GaussianBlur(camada_brasa, (0, 0), 1.2) * 1.6

        # luz do fogo iluminando o chão em volta
        intensidade = float(aceso.mean()) * 60
        luz = cv2.GaussianBlur(aceso, (0, 0), h * 0.08) * (0.9 + 0.2 * np.sin(t * 23) * np.sin(t * 7.3))
        luz = np.clip(luz * 6, 0, 1.2)[..., None] * np.array([1.0, 0.45, 0.12], np.float32)

        # composição
        img = fundo * (1 - 0.55 * queimado[..., None])          # marca de queimado
        img = img * (1 + luz * 1.8) + luz * 0.10                  # chão iluminado
        brilho = cv2.GaussianBlur(fogo, (0, 0), 9) * 0.9          # bloom
        img = 1 - (1 - img) * (1 - fogo) * (1 - brilho * 0.8)     # mistura "tela"
        img += camada_brasa[..., None] * np.array([1.0, 0.6, 0.2], np.float32)
        img *= 1 - 0.06 * min(intensidade, 1) * (1 - n1.mean())   # cintilação geral

        enc.stdin.write((np.clip(img, 0, 1) * 255).astype(np.uint8).tobytes())
        if i % a.fps == 0:
            print(f"  {t:4.1f}s / {a.duracao:.1f}s", flush=True)

    enc.stdin.close(); enc.wait()
    if cap:
        cap.release()

    # áudio: som do fogo (+ áudio original, se houver)
    cmd = [ff, "-y", "-loglevel", "error", "-i", tmp_video]
    if not a.sem_som:
        wav = a.saida + ".fogo.wav"
        som_de_fogo(wav, a.duracao, a.inicio)
        cmd += ["-i", wav]
        if a.entrada:
            cmd += ["-i", a.entrada, "-filter_complex",
                    "[2:a]volume=1[o];[1:a]volume=0.8[f];[o][f]amix=inputs=2:duration=first[a]",
                    "-map", "0:v", "-map", "[a]"]
        else:
            cmd += ["-map", "0:v", "-map", "1:a"]
        cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", a.saida]
    else:
        cmd += ["-c", "copy", a.saida]
    r = subprocess.run(cmd)
    if r.returncode != 0 and a.entrada and not a.sem_som:  # vídeo sem faixa de áudio
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", tmp_video, "-i", wav,
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", a.saida], check=True)
    import os
    os.remove(tmp_video)
    if not a.sem_som:
        os.remove(wav)
    print(f"Pronto: {a.saida}")


if __name__ == "__main__":
    main()
