# Kaio Camuri — Edição de Vídeo

Ambiente para editar vídeos por linha de comando e Python.

## Instalação

```bash
sudo bash scripts/setup-video.sh
```

## O que é instalado

| Ferramenta | Para que serve |
|---|---|
| **ffmpeg / ffprobe** | Cortar, juntar, converter, comprimir, legendas, áudio |
| **mediainfo** | Ver detalhes técnicos de um arquivo (codec, bitrate, fps) |
| **sox** | Processar áudio (normalizar, remover ruído) |
| **mkvtoolnix** | Manipular arquivos MKV (faixas, legendas) |
| **ImageMagick** | Thumbnails, imagens, sobreposições |
| **MoviePy** | Edição em Python (cortes, textos, transições, composições) |
| **OpenCV** | Processamento de imagem/frames, detecção de rostos, efeitos |
| **PySceneDetect** | Detectar cortes de cena automaticamente |
| **pydub** | Edição de áudio em Python |
| **Whisper** | Transcrição automática e geração de legendas (.srt) |
| **yt-dlp** | Baixar vídeos de referência |

## Exemplos rápidos

```bash
# Cortar do segundo 10 ao 30 sem reencodar
ffmpeg -ss 10 -to 30 -i entrada.mp4 -c copy corte.mp4

# Converter para vertical 9:16 (Reels/TikTok/Shorts)
ffmpeg -i entrada.mp4 -vf "crop=ih*9/16:ih,scale=1080:1920" -c:a copy vertical.mp4

# Comprimir para web
ffmpeg -i entrada.mp4 -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k web.mp4

# Extrair o áudio
ffmpeg -i entrada.mp4 -vn -c:a libmp3lame -q:a 2 audio.mp3

# Gerar legendas automáticas em português
whisper entrada.mp4 --language pt --model small --output_format srt

# Queimar legendas no vídeo
ffmpeg -i entrada.mp4 -vf subtitles=entrada.srt legendado.mp4

# Detectar cenas e dividir o vídeo
scenedetect -i entrada.mp4 detect-content split-video
```

```python
from moviepy import VideoFileClip, TextClip, CompositeVideoClip

clip = VideoFileClip("entrada.mp4").subclipped(0, 10)
texto = (TextClip(text="Kaio Camuri", font_size=70, color="white")
         .with_duration(10).with_position("center"))
CompositeVideoClip([clip, texto]).write_videofile("saida.mp4")
```

## IA e efeitos (rodam na CPU)

| Ferramenta | Para que serve |
|---|---|
| **Blender** | 3D: modelos, simulação de fogo/fumaça, rastreamento de câmera, composição |
| **rembg** | IA que recorta a pessoa/objeto do fundo |
| **MediaPipe** | IA que rastreia rosto, mãos e corpo |

### Texto pegando fogo no chão

```bash
# Demonstração com chão sintético
python efeitos/fogo_no_chao.py --texto "KAIO" --saida fogo.mp4

# No seu vídeo (câmera parada): cantos da área do chão em pixels,
# na ordem sup-esq, sup-dir, inf-dir, inf-esq
python efeitos/fogo_no_chao.py --entrada chao.mp4 --texto "KAIO" \
    --cantos "420,560 860,560 1100,700 180,700" --saida fogo.mp4
```

Opções: `--inicio` (segundo em que acende), `--acender` (tempo para percorrer o texto),
`--altura-chama`, `--duracao`, `--sem-som`. Um vídeo de 6 s em 720p leva cerca de 2 min.

## Enviar vídeos grandes (acima de 30 MB)

O app do Claude limita anexos a 30 MB. Para vídeos maiores, use um link do Google Drive:

1. Envie o vídeo para o Google Drive.
2. Clique com o botão direito → **Compartilhar** → em "Acesso geral" escolha
   **Qualquer pessoa com o link** → **Copiar link**.
3. Cole o link no chat.

```bash
python scripts/baixar_drive.py "https://drive.google.com/file/d/XXXX/view" midia
```

Arquivos de até 10 MB também podem vir pelo conector do Drive; `scripts/drive_para_video.py`
converte esse download no arquivo original.

## Tour de imóvel (padrão House Brokers)

Une os vídeos, acelera 10x enquanto anda e freia bruscamente para 1x nas paradas,
legenda os cômodos, aplica o logo branco a 20%, cartela final e trilha de blues.

```bash
python efeitos/tour_imovel.py analisar sala.mov cozinha.mov quintal.mov --saida tour.json
# veja tour_paradas.jpg, edite "legendas" (e "cartela_mascote") no tour.json
python efeitos/tour_imovel.py renderizar tour.json --saida tour.mp4   # --previa = rápido
```

A trilha é composta automaticamente por `efeitos/musica_blues.py` (ou use `"musica"` no json).
Cores e fontes seguem o manual da marca: laranja #F68B1F, azul #001827, Montserrat.
