#!/usr/bin/env python3
"""Compõe e renderiza uma trilha de blues suave (shuffle lento, clima aconchegante).

Piano elétrico, contrabaixo caminhante, bateria com vassourinha e uma guitarra
limpa com frases curtas. 100% gerada aqui, sem direitos autorais de terceiros.

Uso: python efeitos/musica_blues.py --duracao 60 --saida blues.wav [--bpm 76] [--tom A]
"""
import argparse
import os
import random
import subprocess
import tempfile

from midiutil import MIDIFile

SF2 = "/usr/share/sounds/sf2/FluidR3_GM.sf2"
TONS = {"C": 48, "D": 50, "E": 52, "F": 53, "G": 55, "A": 45, "Bb": 46}

# 12 compassos: graus I, IV, V
FORMA = [0, 5, 0, 0, 5, 5, 0, 0, 7, 5, 0, 7]


def acorde7(raiz):  # voicing de 9ª para piano (sem a fundamental)
    return [raiz + 4, raiz + 10, raiz + 14, raiz + 19]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duracao", type=float, default=60)
    ap.add_argument("--saida", default="blues.wav")
    ap.add_argument("--bpm", type=int, default=76)
    ap.add_argument("--tom", default="A", choices=TONS)
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()
    rnd = random.Random(a.seed)

    base = TONS[a.tom]
    seg_compasso = 4 * 60 / a.bpm
    n_compassos = max(4, int(a.duracao / seg_compasso + 0.999))

    m = MIDIFile(5, deinterleave=False)
    PIANO, BAIXO, BAT, GUIT, ORG = range(5)
    for t, (canal, prog, vol) in enumerate([(0, 4, 92), (1, 32, 105), (9, 0, 80), (2, 26, 78), (3, 18, 40)]):
        m.addTempo(t, 0, a.bpm)
        if canal != 9:
            m.addProgramChange(t, canal, 0, prog)
        m.addControllerEvent(t, canal, 0, 7, vol)
        m.addControllerEvent(t, canal, 0, 91, 50)  # reverb

    sw = 2 / 3  # swing: colcheia "longa-curta"
    escala = [0, 3, 5, 6, 7, 10, 12, 15]  # pentatônica menor + blue note

    for c in range(n_compassos):
        grau = FORMA[c % 12]
        raiz = base + grau
        ini = c * 4
        ultimo = c == n_compassos - 1
        intro = c < 2

        if ultimo:  # final: acorde de I sustentado
            for n in acorde7(base + 12):
                m.addNote(PIANO, 0, n, ini, 4, 70)
            m.addNote(BAIXO, 1, base - 12, ini, 4, 95)
            m.addNote(BAT, 9, 49, ini, 4, 70)  # prato
            m.addNote(BAT, 9, 36, ini, 1, 90)
            m.addNote(GUIT, 2, base + 24 + 7, ini + 0.5, 3.5, 70)
            m.addNote(ORG, 3, base + 12, ini, 4, 50)
            break

        # piano: comping no 2 e no "e" do 3
        for tempo, dur in [(1, 0.6), (2 + sw, 0.9)]:
            vel = rnd.randint(52, 66)
            for n in acorde7(raiz + 12):
                m.addNote(PIANO, 0, n, ini + tempo, dur, vel)
        # órgão bem baixinho segurando a harmonia
        if not intro:
            for n in [raiz + 12, raiz + 16, raiz + 22]:
                m.addNote(ORG, 3, n, ini, 4, 38)

        # baixo caminhante (shuffle)
        prox = base + FORMA[(c + 1) % 12]
        linha = [raiz, raiz + 4, raiz + 7, raiz + 9 if rnd.random() < .5 else raiz + 10]
        if prox != raiz:
            linha[3] = prox - 1 if rnd.random() < .6 else prox + 1
        for i, n in enumerate(linha):
            m.addNote(BAIXO, 1, n - 12, ini + i, 0.9, 92 if i % 2 == 0 else 80)

        # bateria: ride em shuffle, vassourinha no 2 e 4, bumbo leve
        if not intro or c == 1:
            for b in range(4):
                m.addNote(BAT, 9, 51, ini + b, 0.3, 58)
                m.addNote(BAT, 9, 51, ini + b + sw, 0.2, 40)
                if b in (1, 3):
                    m.addNote(BAT, 9, 38, ini + b, 0.3, 46)  # caixa leve
                    m.addNote(BAT, 9, 44, ini + b, 0.2, 50)  # chimbal no pé
            m.addNote(BAT, 9, 36, ini, 0.5, 70)
            m.addNote(BAT, 9, 36, ini + 2, 0.5, 58)

        # guitarra: frase curta a cada 2 compassos, respirando
        if not intro and c % 2 == 0:
            t = ini + rnd.choice([0, 0.5 + sw / 2, 1])
            nota = rnd.choice([3, 4, 5])
            for _ in range(rnd.randint(3, 6)):
                nota = max(0, min(len(escala) - 1, nota + rnd.choice([-2, -1, -1, 1, 2])))
                d = rnd.choice([sw, 1 - sw, 1, 0.5])
                m.addNote(GUIT, 2, base + 24 + escala[nota], t, d * 0.95, rnd.randint(62, 80))
                t += d
                if t > ini + 7:
                    break
            # termina a frase em nota do acorde, com bend implícito (blue note -> 3ª)
            m.addNote(GUIT, 2, base + 24 + rnd.choice([0, 7, 12]), t, 1.2, 74)

    with tempfile.TemporaryDirectory() as tmp:
        mid = os.path.join(tmp, "blues.mid")
        bruto = os.path.join(tmp, "bruto.wav")
        with open(mid, "wb") as f:
            m.writeFile(f)
        subprocess.run(["fluidsynth", "-ni", "-g", "0.8", "-r", "44100", "-F", bruto, SF2, mid],
                       check=True, capture_output=True)
        # corta na duração, fade-out e normaliza loudness para fundo de vídeo
        dur = n_compassos * seg_compasso + 2
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", bruto, "-af",
                        f"atrim=0:{dur},afade=t=out:st={dur - 3}:d=3,loudnorm=I=-18:TP=-1.5",
                        "-ar", "44100", a.saida], check=True)
    print(f"Pronto: {a.saida} ({n_compassos} compassos, {a.bpm} bpm, tom de {a.tom})")


if __name__ == "__main__":
    main()
