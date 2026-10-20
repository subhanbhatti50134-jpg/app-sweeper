#!/usr/bin/env bash
# Uninstaller for the Linux Uninstaller itself.
set -euo pipefail

BIN_NAME="uninstaller"
GUI_NAME="uninstaller-gui"
INSTALL_DIR="${HOME}/.local/bin"
APP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/256x256/apps"

GREEN='\033[0;32m'; NC='\033[0m'

echo -e "${GREEN}Removing Linux Uninstaller...${NC}"

for f in "${INSTALL_DIR}/${BIN_NAME}" "${INSTALL_DIR}/${GUI_NAME}"; do
    if [ -e "$f" ]; then rm -f "$f"; echo "  Removed $f"; fi
done

DESKTOP="${APP_DIR}/linux-uninstaller.desktop"
if [ -e "$DESKTOP" ]; then rm -f "$DESKTOP"; echo "  Removed desktop entry"; fi

ICON="${ICON_DIR}/linux-uninstaller.png"
if [ -e "$ICON" ]; then rm -f "$ICON"; echo "  Removed icon"; fi

echo -e "${GREEN}Done. (The project source folder was not touched.)${NC}"
