#!/usr/bin/env bash
set -e

SRC_DIR="/Users/ribo/Desktop/Trading"
RPI_HOST="ribo@192.168.1.130"
RPI_DIR="/home/ribo/day-trader-dashboard"

echo "=== [1/2] Copia della cartella Trading su $RPI_HOST ==="
ssh "$RPI_HOST" "mkdir -p $RPI_DIR"
rsync -avz --exclude "__pycache__" --exclude ".git" "$SRC_DIR/" "$RPI_HOST:$RPI_DIR/"

echo "=== [2/2] Esecuzione configurazione servizi systemd e tunnel Cloudflare ==="
ssh -t "$RPI_HOST" "chmod +x $RPI_DIR/setup_raspberry.sh && $RPI_DIR/setup_raspberry.sh"
