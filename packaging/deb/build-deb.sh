#!/bin/bash
# build-deb.sh: Build a .deb package for eLibrary Manager.
#
# Usage: ./packaging/deb/build-deb.sh
# Output: build/elibrary-manager_<version>_amd64.deb

set -euo pipefail

# --- Configuration ---
PKG_NAME="elibrary-manager"
PKG_VERSION="${1:-0.1.0}"
PKG_ARCH="amd64"
PKG_MAINTAINER="eLibrary Manager <noreply@elibrary-manager.local>"
PKG_DESCRIPTION="Lightweight ebook collection manager with AI-powered chapter summarization.
 Reads EPUB, PDF, and MOBI files. Provides a web-based reader with
 bookmarking, note-taking, and text-to-speech support."
PKG_DEPENDS="python3.12, libgl1, libglib2.0-0, xdg-utils"
PKG_SECTION="web"
PKG_PRIORITY="optional"

# --- Paths ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
PKG_DIR="$BUILD_DIR/${PKG_NAME}_${PKG_VERSION}_${PKG_ARCH}"
INSTALL_ROOT="$PKG_DIR/opt/elibrary-manager"

echo "=== Building ${PKG_NAME}_${PKG_VERSION}_${PKG_ARCH}.deb ==="
echo "Project root: $PROJECT_ROOT"
echo ""

# --- Step 1: Clean build directory ---
echo "[1/12] Cleaning build directory..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# --- Step 2: Create directory structure ---
echo "[2/12] Creating directory structure..."
mkdir -p "$INSTALL_ROOT/app"
mkdir -p "$INSTALL_ROOT/frontend"
mkdir -p "$INSTALL_ROOT/.venv"
mkdir -p "$PKG_DIR/var/lib/elibrary-manager/dawnstar_data"
mkdir -p "$PKG_DIR/var/lib/elibrary-manager/static_covers"
mkdir -p "$PKG_DIR/var/lib/elibrary-manager/static_book_images"
mkdir -p "$PKG_DIR/var/lib/elibrary-manager/library"
mkdir -p "$PKG_DIR/var/log/elibrary-manager"
mkdir -p "$PKG_DIR/etc/elibrary-manager"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$PKG_DIR/usr/lib/systemd/system"

# --- Step 3: Create clean venv ---
echo "[3/12] Creating clean virtual environment..."
cd "$PROJECT_ROOT"
# Build a fresh venv with only production dependencies
uv venv "$INSTALL_ROOT/.venv" --python 3.12 --clear

# Export production-only requirements (no dev deps, no hashes)
REQUIREMENTS_FILE=$(mktemp)
if uv export --no-dev --no-hashes > "$REQUIREMENTS_FILE" 2>/dev/null && [ -s "$REQUIREMENTS_FILE" ]; then
    echo "  Installing from uv export..."
    uv pip install --python "$INSTALL_ROOT/.venv/bin/python" -r "$REQUIREMENTS_FILE"
else
    echo "  uv export failed, falling back to direct install..."
    uv pip install --python "$INSTALL_ROOT/.venv/bin/python" \
        "fastapi[standard]>=0.104.0" \
        "uvicorn[standard]>=0.24.0" \
        "sqlalchemy[exts]>=2.0.23" \
        "aiosqlite>=0.19.0" \
        "ebooklib>=0.18" \
        "beautifulsoup4>=4.12.2" \
        "jinja2>=3.1.2" \
        "google-genai>=0.3.0" \
        "openai>=1.0.0" \
        "httpx>=0.25.2" \
        "pillow>=10.1.0" \
        "pydantic>=2.5.0" \
        "pydantic-settings>=2.1.0" \
        "pymupdf>=1.24.0" \
        "pymobi>=0.1.3" \
        "gtts>=2.5.0" \
        "edge-tts>=6.1.0" \
        "cryptography>=42.0.0" \
        "passlib[bcrypt]>=1.7.4" \
        "nh3>=0.3.5" \
        "alembic>=1.18.4" \
        "cachetools>=5.3.0"
fi
rm -f "$REQUIREMENTS_FILE"

# --- Step 4: Copy backend code ---
echo "[4/12] Copying backend code..."
cp -r "$PROJECT_ROOT/backend/app/." "$INSTALL_ROOT/app/"

# --- Step 5: Copy frontend ---
echo "[5/12] Copying frontend..."
cp -r "$PROJECT_ROOT/frontend/." "$INSTALL_ROOT/frontend/"

# --- Step 6: Copy alembic ---
echo "[6/12] Copying alembic migrations..."
cp -r "$PROJECT_ROOT/alembic" "$INSTALL_ROOT/"
cp "$PROJECT_ROOT/alembic.ini" "$INSTALL_ROOT/"

# --- Step 7: Copy pyproject.toml (needed for metadata) ---
echo "[7/12] Copying project metadata..."
cp "$PROJECT_ROOT/pyproject.toml" "$INSTALL_ROOT/"

# --- Step 8: Fix venv python symlinks ---
echo "[8/12] Fixing venv python symlinks..."
VENV_BIN="$INSTALL_ROOT/.venv/bin"
# Point symlinks to system python3.12 (will exist on target)
if [ -L "$VENV_BIN/python" ]; then
    rm -f "$VENV_BIN/python"
    ln -s /usr/bin/python3.12 "$VENV_BIN/python"
fi
if [ -L "$VENV_BIN/python3" ]; then
    rm -f "$VENV_BIN/python3"
    ln -s /usr/bin/python3.12 "$VENV_BIN/python3"
fi
if [ -L "$VENV_BIN/python3.12" ]; then
    rm -f "$VENV_BIN/python3.12"
    ln -s /usr/bin/python3.12 "$VENV_BIN/python3.12"
fi

# --- Step 9: Strip unnecessary files ---
echo "[9/12] Stripping __pycache__, .pyc, tests..."
find "$INSTALL_ROOT" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "$INSTALL_ROOT" -type f -name '*.pyc' -delete 2>/dev/null || true
find "$INSTALL_ROOT" -type f -name '*.pyo' -delete 2>/dev/null || true
find "$INSTALL_ROOT" -type d -name tests -exec rm -rf {} + 2>/dev/null || true
find "$INSTALL_ROOT" -type d -name '.pytest_cache' -exec rm -rf {} + 2>/dev/null || true
find "$INSTALL_ROOT" -type f -name '.coverage' -delete 2>/dev/null || true
find "$INSTALL_ROOT" -type d -name 'htmlcov' -exec rm -rf {} + 2>/dev/null || true

# --- Step 10: Generate DEBIAN/control ---
echo "[10/12] Generating DEBIAN/control..."
# Compute installed size in KB
INSTALLED_SIZE=$(du -sk "$PKG_DIR" | cut -f1)

cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${PKG_VERSION}
Architecture: ${PKG_ARCH}
Maintainer: ${PKG_MAINTAINER}
Description: ${PKG_DESCRIPTION}
Depends: ${PKG_DEPENDS}
Section: ${PKG_SECTION}
Priority: ${PKG_PRIORITY}
Installed-Size: ${INSTALLED_SIZE}
Homepage: https://github.com/elibrary-manager
EOF

# --- Step 11: Copy maintainer scripts, service, desktop, icon ---
echo "[11/12] Copying maintainer scripts and assets..."
cp "$SCRIPT_DIR/preinst" "$PKG_DIR/DEBIAN/preinst"
cp "$SCRIPT_DIR/postinst" "$PKG_DIR/DEBIAN/postinst"
cp "$SCRIPT_DIR/prerm" "$PKG_DIR/DEBIAN/prerm"
cp "$SCRIPT_DIR/postrm" "$PKG_DIR/DEBIAN/postrm"

# Service
cp "$SCRIPT_DIR/elibrary-manager.service" "$PKG_DIR/usr/lib/systemd/system/"

# Desktop entry
cp "$SCRIPT_DIR/elibrary-manager.desktop" "$PKG_DIR/usr/share/applications/"

# Icon
cp "$SCRIPT_DIR/elibrary-manager.svg" "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/"

# --- Step 12: Set permissions ---
echo "[12/12] Setting permissions..."
# Maintainer scripts must be executable
chmod 755 "$PKG_DIR/DEBIAN/preinst"
chmod 755 "$PKG_DIR/DEBIAN/postinst"
chmod 755 "$PKG_DIR/DEBIAN/prerm"
chmod 755 "$PKG_DIR/DEBIAN/postrm"

# Application files: root:root (only if running as root; --root-owner-group
# handles ownership mapping for non-root builds)
if [ "$(id -u)" -eq 0 ]; then
    chown -R root:root "$PKG_DIR/opt"
    chown -R root:root "$PKG_DIR/usr"
    chown -R root:root "$PKG_DIR/var"
    chown -R root:root "$PKG_DIR/etc"
fi

# Make venv binaries executable
find "$INSTALL_ROOT/.venv/bin" -type f -executable -exec chmod 755 {} + 2>/dev/null || true

# --- Build the package ---
echo ""
echo "Building package..."
dpkg-deb --build --root-owner-group "$PKG_DIR"

DEB_FILE="$BUILD_DIR/${PKG_NAME}_${PKG_VERSION}_${PKG_ARCH}.deb"
echo ""
echo "=== Build complete ==="
echo "Package: $DEB_FILE"
echo "Size: $(du -sh "$DEB_FILE" | cut -f1)"
echo ""
echo "Verify with:"
echo "  dpkg-deb --info $DEB_FILE"
echo "  dpkg-deb --contents $DEB_FILE"
echo "  sudo dpkg -i $DEB_FILE"
