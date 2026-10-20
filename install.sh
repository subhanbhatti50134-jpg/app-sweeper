#!/usr/bin/env bash
# ============================================================
#  Linux Uninstaller — installer script (GUI + CLI)
# ============================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_NAME="uninstaller"
GUI_NAME="uninstaller-gui"
INSTALL_DIR="${HOME}/.local/bin"
DATA_DIR="${HOME}/.local/share"
APP_DIR="${DATA_DIR}/applications"
ICON_DIR="${DATA_DIR}/icons/hicolor/256x256/apps"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()  { echo -e "${RED}[WARN]${NC} $*"; }

echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD}   Linux Uninstaller — Installer${NC}"
echo -e "${BOLD}============================================${NC}"
echo

# --- 1. Check python3 -------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 not found. Please install Python 3.8+ first."
    exit 1
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "Found Python ${PY_VER}"

# --- 2. Check for a browser (web GUI) + tkinter (Tk fallback) ------------
HAS_WEBGUI=1
if command -v xdg-open >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1 \
   || command -v chromium >/dev/null 2>&1 || command -v firefox >/dev/null 2>&1 \
   || command -v google-chrome >/dev/null 2>&1; then
    info "Browser found — premium web GUI will be installed"
else
    HAS_WEBGUI=0
    warn "No browser found — installing CLI only."
fi
if python3 -c 'import tkinter' >/dev/null 2>&1; then
    info "tkinter found — classic Tk GUI available via 'uninstaller tk'"
fi

# --- 3. Create install dirs -------------------------------------------
mkdir -p "${INSTALL_DIR}" "${APP_DIR}" "${ICON_DIR}"

# --- 4. CLI launcher ----------------------------------------------------
LAUNCHER="${INSTALL_DIR}/${BIN_NAME}"
cat > "${LAUNCHER}" <<EOF
#!/usr/bin/env bash
exec python3 -c "
import sys
sys.path.insert(0, r'${PROJECT_DIR}')
from uninstaller.cli import main
sys.exit(main())
" "\$@"
EOF
chmod +x "${LAUNCHER}"
ok "CLI launcher installed → ${LAUNCHER}"

# --- 5. GUI launcher (premium web app) --------------------------------
if [ "${HAS_WEBGUI}" = "1" ]; then
    GUI_LAUNCHER="${INSTALL_DIR}/${GUI_NAME}"
    cat > "${GUI_LAUNCHER}" <<EOF
#!/usr/bin/env bash
exec python3 -c "
import sys
sys.path.insert(0, r'${PROJECT_DIR}')
from uninstaller.webapp import main
sys.exit(main())
" "\$@"
EOF
    chmod +x "${GUI_LAUNCHER}"
    ok "GUI launcher installed → ${GUI_LAUNCHER}"

    # --- 6. Icon ---------------------------------------------------------
    if [ -f "${PROJECT_DIR}/assets/icon.png" ]; then
        # 512px source → 256px install size
        python3 - "${PROJECT_DIR}/assets/icon.png" "${ICON_DIR}/linux-uninstaller.png" <<'PYEOF'
import sys
from PIL import Image
Image.open(sys.argv[1]).resize((256, 256), Image.LANCZOS).save(sys.argv[2])
PYEOF
        ok "Icon installed → ${ICON_DIR}/linux-uninstaller.png"
    fi

    # --- 7. Desktop entry (GUI, no terminal) ------------------------------
    DESKTOP_FILE="${APP_DIR}/linux-uninstaller.desktop"
    cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Linux Uninstaller
GenericName=App Uninstaller
Comment=Uninstall apps and clean leftover cache, config, and temp files
Exec=${GUI_LAUNCHER}
Icon=linux-uninstaller
Terminal=false
Categories=System;Settings;
Keywords=uninstall;remove;clean;cache;purge;
StartupNotify=true
EOF
    chmod +x "${DESKTOP_FILE}"
    ok "Desktop entry installed → ${DESKTOP_FILE}"
else
    # Terminal-only desktop entry
    DESKTOP_FILE="${APP_DIR}/linux-uninstaller.desktop"
    cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Linux Uninstaller (Terminal)
GenericName=App Uninstaller
Comment=Uninstall apps and clean leftover cache, config, and temp files
Exec=${LAUNCHER}
Icon=edit-delete
Terminal=true
Categories=System;Settings;
Keywords=uninstall;remove;clean;cache;purge;
StartupNotify=false
EOF
    chmod +x "${DESKTOP_FILE}"
    ok "Terminal desktop entry installed → ${DESKTOP_FILE}"
fi

# --- 8. PATH hint --------------------------------------------------------
if ! echo "$PATH" | grep -q "${INSTALL_DIR}"; then
    info "Add to your shell profile to use 'uninstaller' anywhere:"
    echo -e "      export PATH=\"${INSTALL_DIR}:\$PATH\""
fi

# Refresh desktop database if possible
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APP_DIR}" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f "${DATA_DIR}/icons/hicolor" >/dev/null 2>&1 || true
fi

echo
ok "Installation complete!"
echo
echo -e "  ${BOLD}Launch:${NC}"
if [ "${HAS_WEBGUI}" = "1" ]; then
    echo "    ${GUI_NAME}                  # open the premium app window"
    echo "    ${BIN_NAME}                  # same (auto-detects GUI)"
fi
echo
echo -e "  ${BOLD}CLI:${NC}"
echo "    ${BIN_NAME} list            # list installed apps"
echo "    ${BIN_NAME} uninstall APP   # uninstall + clean leftovers"
echo "    ${BIN_NAME} scan            # find orphaned data"
echo "    ${BIN_NAME} clean all       # clean cache/temp/trash"
echo "    ${BIN_NAME} gui             # launch the web app"
echo "    ${BIN_NAME} tk              # classic Tk GUI (if tkinter present)"
echo
