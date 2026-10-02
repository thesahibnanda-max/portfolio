#!/usr/bin/env bash
set -euo pipefail

DOMAIN="portfolio-sahib-nanda.duckdns.org"
API_DOMAIN="api.${DOMAIN}"
DEPLOY_USER="ubuntu"

echo "== swap"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
fi
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
cat > /etc/sysctl.d/99-portfolio-swap.conf <<'EOF'
vm.swappiness=10
vm.vfs_cache_pressure=50
EOF
sysctl -q --system

echo "== packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq rsync curl ca-certificates gnupg debian-keyring debian-archive-keyring apt-transport-https >/dev/null
if [ ! -f /usr/share/keyrings/caddy-stable-archive-keyring.gpg ]; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' -o /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
fi
apt-get install -y -qq caddy >/dev/null

echo "== uv and free-threaded python"
install -m 755 "/home/${DEPLOY_USER}/.local/bin/uv" /usr/local/bin/uv
install -d -m 755 /opt/portfolio /opt/portfolio/python
UV_PYTHON_INSTALL_DIR=/opt/portfolio/python /usr/local/bin/uv python install 3.14.8t >/dev/null 2>&1 || true
chmod -R a+rX /opt/portfolio/python

echo "== users and directories"
id portfolio >/dev/null 2>&1 || useradd --system --home-dir /var/lib/portfolio --shell /usr/sbin/nologin portfolio
install -d -m 750 -o portfolio -g portfolio /var/lib/portfolio
install -d -m 755 -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" /opt/portfolio/releases /opt/portfolio/frontend-releases
install -d -m 750 /etc/portfolio
[ -f /etc/portfolio/backend.env ] || install -m 600 /dev/null /etc/portfolio/backend.env

echo "== systemd service"
cat > /etc/systemd/system/portfolio-backend.service <<'EOF'
[Unit]
Description=Portfolio backend (FastAPI on free-threaded Python 3.14t)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=portfolio
Group=portfolio
WorkingDirectory=/var/lib/portfolio
Environment=HOME=/var/lib/portfolio
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/etc/portfolio/backend.env
ExecStart=/opt/portfolio/current/venv/bin/gunicorn -c /opt/portfolio/current/src/gunicorn.conf.py --bind 127.0.0.1:8080
Restart=always
RestartSec=3
TimeoutStopSec=40
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
ReadWritePaths=/var/lib/portfolio

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable portfolio-backend.service >/dev/null 2>&1

echo "== activation script"
cat > /usr/local/bin/portfolio-activate <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
kind="${1:-}"
release="${2:-}"
keep=3

wait_healthy() {
  for _ in $(seq 1 45); do
    curl --silent --fail --max-time 3 http://127.0.0.1:8080/health >/dev/null && return 0
    sleep 2
  done
  return 1
}

prune() {
  local dir="$1" current
  current="$(readlink -f "$2" || true)"
  ls -1dt "$dir"/*/ 2>/dev/null | tail -n +"$((keep + 1))" | while read -r old; do
    [ "$(readlink -f "$old")" = "$current" ] || rm -rf "$old"
  done
}

case "$kind" in
  backend)
    target="/opt/portfolio/releases/$release"
    [ -x "$target/venv/bin/gunicorn" ] || { echo "release $release is not built" >&2; exit 1; }
    previous="$(readlink -f /opt/portfolio/current || true)"
    ln -sfn "$target" /opt/portfolio/current.next && mv -Tf /opt/portfolio/current.next /opt/portfolio/current
    systemctl restart portfolio-backend.service
    if wait_healthy; then
      echo "backend $release is healthy"
      prune /opt/portfolio/releases /opt/portfolio/current
    else
      echo "backend $release failed its health check; rolling back" >&2
      journalctl -u portfolio-backend.service -n 40 --no-pager >&2 || true
      if [ -n "$previous" ] && [ -d "$previous" ]; then
        ln -sfn "$previous" /opt/portfolio/current.next && mv -Tf /opt/portfolio/current.next /opt/portfolio/current
        systemctl restart portfolio-backend.service
        wait_healthy && echo "rolled back to $(basename "$previous")" >&2
      fi
      exit 1
    fi
    ;;
  env)
    tmp="$(mktemp)"
    cat > "$tmp"
    if ! grep -qE '^[A-Z0-9_]+=.+' "$tmp"; then rm -f "$tmp"; echo "refusing to install an empty environment" >&2; exit 1; fi
    install -m 600 -o root -g root "$tmp" /etc/portfolio/backend.env
    rm -f "$tmp"
    echo "environment updated ($(grep -cE '^[A-Z0-9_]+=' /etc/portfolio/backend.env) variables)"
    ;;
  frontend)
    target="/opt/portfolio/frontend-releases/$release"
    [ -f "$target/index.html" ] || { echo "frontend $release has no index.html" >&2; exit 1; }
    ln -sfn "$target" /opt/portfolio/frontend.next && mv -Tf /opt/portfolio/frontend.next /opt/portfolio/frontend
    echo "frontend $release is live"
    prune /opt/portfolio/frontend-releases /opt/portfolio/frontend
    ;;
  *)
    echo "usage: portfolio-activate backend <release> | frontend <release> | env < file" >&2
    exit 2
    ;;
esac
EOF
chmod 755 /usr/local/bin/portfolio-activate

echo "== caddy"
cat > /etc/caddy/Caddyfile <<EOF
${DOMAIN} {
	root * /opt/portfolio/frontend
	encode zstd gzip
	@hashed path /_astro/*
	header @hashed Cache-Control "public, max-age=31536000, immutable"
	header ?Cache-Control "public, max-age=300"
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
		Referrer-Policy "strict-origin-when-cross-origin"
		-Server
	}
	try_files {path} {path}/ /index.html
	file_server
}

${API_DOMAIN} {
	request_body {
		max_size 256KB
	}
	header {
		Strict-Transport-Security "max-age=31536000"
		-Server
	}
	reverse_proxy 127.0.0.1:8080 {
		flush_interval -1
	}
}
EOF
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
systemctl enable caddy >/dev/null 2>&1
systemctl reload caddy 2>/dev/null || systemctl restart caddy

echo "== done"
free -h | head -3
swapon --show
caddy version
"$(UV_PYTHON_INSTALL_DIR=/opt/portfolio/python /usr/local/bin/uv python find 3.14.8t)" -c "import sys; print('python', sys.version.split()[0], 'GIL', sys._is_gil_enabled())"
