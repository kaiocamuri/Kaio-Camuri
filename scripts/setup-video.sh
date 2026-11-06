#!/usr/bin/env bash
# Instala as ferramentas de edição de vídeo (Ubuntu/Debian).
# Uso: sudo bash scripts/setup-video.sh   (ou como root)
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  ffmpeg sox mediainfo mkvtoolnix imagemagick \
  fonts-dejavu fonts-liberation

pip install -q -r "$(dirname "$0")/../requirements.txt"

echo "Ferramentas de vídeo instaladas."
