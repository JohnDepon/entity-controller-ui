#!/bin/sh
# Install or update Entity Controller from a self-hosted source.
#
#   sh install.sh SOURCE [CONFIG_DIR]
#
# SOURCE is one of:
#   * an http(s) URL of a .tar.gz/.tgz/.zip archive of this repository, e.g.
#       Gitea/Forgejo: https://git.example.lan/me/entity-controller-ui/archive/v10.0.0.tar.gz
#       GitLab:        https://gitlab.example.lan/me/entity-controller-ui/-/archive/v10.0.0/entity-controller-ui-v10.0.0.tar.gz
#   * a local archive file
#   * a local directory (e.g. a git clone of this repository)
# CONFIG_DIR defaults to /config (Home Assistant OS / Container).
# For private repositories set an extra HTTP header, e.g.
#   EC_HEADER="Authorization: token <gitea-token>"   (Gitea/Forgejo)
#   EC_HEADER="PRIVATE-TOKEN: <gitlab-token>"        (GitLab)
#
# The previous version is kept in CONFIG_DIR/entity_controller.backup (outside
# custom_components, so Home Assistant does not load it twice).
# Restart Home Assistant afterwards.
set -eu

SOURCE="${1:-}"
CONFIG_DIR="${2:-/config}"
DOMAIN="entity_controller"

if [ -z "$SOURCE" ]; then
    sed -n '2,19p' "$0"
    exit 1
fi
if [ ! -d "$CONFIG_DIR" ]; then
    echo "Config directory $CONFIG_DIR does not exist" >&2
    exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

extract() {
    case "$1" in
        *.zip|*.ZIP)
            if command -v unzip >/dev/null 2>&1; then
                unzip -q "$1" -d "$WORK/src"
            else
                python3 -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$1" "$WORK/src"
            fi
            ;;
        *)
            tar -xzf "$1" -C "$WORK/src"
            ;;
    esac
}

mkdir -p "$WORK/src"
case "$SOURCE" in
    http://*|https://*)
        name="$(basename "${SOURCE%%\?*}")"
        case "$name" in *.zip|*.ZIP|*.tar.gz|*.tgz) ;; *) name="source.tar.gz" ;; esac
        echo "Downloading $SOURCE"
        if command -v curl >/dev/null 2>&1; then
            if [ -n "${EC_HEADER:-}" ]; then
                curl -fsSL -H "$EC_HEADER" "$SOURCE" -o "$WORK/$name"
            else
                curl -fsSL "$SOURCE" -o "$WORK/$name"
            fi
        elif [ -n "${EC_HEADER:-}" ]; then
            wget -q --header="$EC_HEADER" -O "$WORK/$name" "$SOURCE"
        else
            wget -q -O "$WORK/$name" "$SOURCE"
        fi
        extract "$WORK/$name"
        ;;
    *)
        if [ -d "$SOURCE" ]; then
            cp -R "$SOURCE" "$WORK/src/"
        elif [ -f "$SOURCE" ]; then
            extract "$SOURCE"
        else
            echo "Source $SOURCE not found" >&2
            exit 1
        fi
        ;;
esac

NEW="$(find "$WORK/src" -type f -path "*/custom_components/$DOMAIN/manifest.json" | head -n 1)"
if [ -z "$NEW" ]; then
    echo "custom_components/$DOMAIN not found in $SOURCE" >&2
    exit 1
fi
NEW="$(dirname "$NEW")"
VERSION="$(sed -n 's/.*"version"[^"]*"\([^"]*\)".*/\1/p' "$NEW/manifest.json")"

TARGET="$CONFIG_DIR/custom_components/$DOMAIN"
BACKUP="$CONFIG_DIR/$DOMAIN.backup"
mkdir -p "$CONFIG_DIR/custom_components"
if [ -d "$TARGET" ]; then
    rm -rf "$BACKUP"
    mv "$TARGET" "$BACKUP"
    echo "Previous version saved in $BACKUP"
fi
cp -R "$NEW" "$TARGET"
find "$TARGET" -name "__pycache__" -type d -prune -exec rm -rf {} +

echo "Installed Entity Controller $VERSION in $TARGET"
echo "Restart Home Assistant to load it. To roll back: rm -rf $TARGET && mv $BACKUP $TARGET"
