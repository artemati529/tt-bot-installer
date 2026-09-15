#!/usr/bin/env bash
# tt-bot installer — sets up the Telegram admin bot for an ALREADY-INSTALLED
# TrustTunnel endpoint. Does NOT install/configure TrustTunnel itself: run
# the official installer (https://github.com/TrustTunnel/TrustTunnel) first.
# Run as root: sudo ./install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-}")" 2>/dev/null && pwd || true)"
TT_DIR="/opt/trusttunnel"
BOT_DIR="/opt/tt-bot"
TT_BOT_REPO_RAW="${TT_BOT_REPO_RAW:-https://raw.githubusercontent.com/artemati529/tt-bot-installer/main}"

log()  { echo "==> $*"; }
die()  { echo "ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 0. Preconditions
# ---------------------------------------------------------------------------
[[ $EUID -eq 0 ]] || die "Run this script as root (sudo ./install.sh)."

# Piped install (curl | sh) has no sibling files — fetch them from the repo.
if [[ -z "$SCRIPT_DIR" || ! -f "$SCRIPT_DIR/bot.py" || ! -f "$SCRIPT_DIR/requirements.txt" ]]; then
    [[ -n "$TT_BOT_REPO_RAW" ]] || die \
"bot.py/requirements.txt not found next to install.sh. For a piped install set
TT_BOT_REPO_RAW to the repo's raw base URL, e.g.:
  curl -fsSL <raw-url>/install.sh | TT_BOT_REPO_RAW=<raw-url> bash -s -"
    SCRIPT_DIR="$(mktemp -d)"
    log "Fetching bot.py and requirements.txt from $TT_BOT_REPO_RAW..."
    curl -fsSL "$TT_BOT_REPO_RAW/bot.py" -o "$SCRIPT_DIR/bot.py"
    curl -fsSL "$TT_BOT_REPO_RAW/requirements.txt" -o "$SCRIPT_DIR/requirements.txt"
fi

[[ -x "$TT_DIR/trusttunnel_endpoint" ]] || die \
    "TrustTunnel endpoint binary not found at $TT_DIR/trusttunnel_endpoint. \
Install and configure TrustTunnel first: https://github.com/TrustTunnel/TrustTunnel"
[[ -f "$TT_DIR/vpn.toml" && -f "$TT_DIR/hosts.toml" && -f "$TT_DIR/credentials.toml" ]] || die \
    "TrustTunnel config files (vpn.toml/hosts.toml/credentials.toml) not found in $TT_DIR. \
Finish the TrustTunnel setup first — this script only installs the bot."
systemctl is-active --quiet trusttunnel.service || log \
    "WARNING: trusttunnel.service is not active — the bot will start, but VPN management will fail until it is."

echo "============================================================"
echo "  tt-bot installer (Telegram admin bot for TrustTunnel)"
echo "============================================================"
echo

# ---------------------------------------------------------------------------
# 1. Interactive prompts
# ---------------------------------------------------------------------------
read -rp "Telegram BOT_TOKEN (from @BotFather): " BOT_TOKEN < /dev/tty
[[ -n "$BOT_TOKEN" ]] || die "BOT_TOKEN is required."

read -rp "Your Telegram numeric user id (ALLOWED_USER_ID, see @userinfobot): " ALLOWED_USER_ID < /dev/tty
[[ "$ALLOWED_USER_ID" =~ ^[0-9]+$ ]] || die "ALLOWED_USER_ID must be numeric."

HOSTNAME_GUESS="$(grep -oP '^\s*hostname\s*=\s*"\K[^"]+' "$TT_DIR/hosts.toml" 2>/dev/null | head -1)"
PORT_GUESS="$(grep -oP '^\s*listen_address\s*=\s*"[^"]*:\K[0-9]+' "$TT_DIR/vpn.toml" 2>/dev/null | head -1)"
ADDRESS_GUESS=""
[[ -n "$HOSTNAME_GUESS" && -n "$PORT_GUESS" ]] && ADDRESS_GUESS="${HOSTNAME_GUESS}:${PORT_GUESS}"

read -rp "VPN endpoint address, host:port${ADDRESS_GUESS:+ [$ADDRESS_GUESS]}: " ENDPOINT_ADDRESS < /dev/tty
ENDPOINT_ADDRESS="${ENDPOINT_ADDRESS:-$ADDRESS_GUESS}"
[[ -n "$ENDPOINT_ADDRESS" ]] || die "ENDPOINT_ADDRESS is required."

read -rp "Server display name for client configs [trusttunnel]: " SERVER_NAME < /dev/tty
SERVER_NAME="${SERVER_NAME:-trusttunnel}"

read -rp "VPN monitor port (for status checks) [$(echo "$ENDPOINT_ADDRESS" | grep -oP ':\K[0-9]+' || echo 443)]: " VPN_MONITOR_PORT < /dev/tty
VPN_MONITOR_PORT="${VPN_MONITOR_PORT:-$(echo "$ENDPOINT_ADDRESS" | grep -oP ':\K[0-9]+' || echo 443)}"
[[ "$VPN_MONITOR_PORT" =~ ^[0-9]+$ ]] || die "VPN_MONITOR_PORT must be numeric."

# Certbot: many setups have a cert but no auto-renewal wired up (issued
# manually, or by a different ACME client) — the bot's cert card assumes
# certbot.timer exists. Offer to issue/rewire one instead of just guessing.
CERT_ISSUE=n
CERT_DOMAIN=""
CERT_EMAIL=""
echo
read -rp "Already have certbot auto-renewal set up for TrustTunnel's certificate? [Y/n] " CERT_ALREADY_MANAGED < /dev/tty
if [[ "$CERT_ALREADY_MANAGED" =~ ^[nN] ]]; then
    read -rp "Issue a certbot-managed certificate now and point hosts.toml at it? [y/N] " CERT_ISSUE < /dev/tty
    if [[ "$CERT_ISSUE" =~ ^[yY] ]]; then
        read -rp "Domain for the certificate${HOSTNAME_GUESS:+ [$HOSTNAME_GUESS]}: " CERT_DOMAIN < /dev/tty
        CERT_DOMAIN="${CERT_DOMAIN:-$HOSTNAME_GUESS}"
        [[ -n "$CERT_DOMAIN" ]] || die "No domain given and none found in hosts.toml."
        read -rp "Contact e-mail for Let's Encrypt (blank = --register-unsafely-without-email): " CERT_EMAIL < /dev/tty
    else
        log "Skipping certificate issuance — the bot's cert card may show incomplete data."
    fi
fi

echo
log "BotUser=$ALLOWED_USER_ID Endpoint=$ENDPOINT_ADDRESS ServerName=$SERVER_NAME"
read -rp "Proceed with installation? [y/N] " CONFIRM < /dev/tty
[[ "$CONFIRM" =~ ^[yY] ]] || die "Aborted by user."

# ---------------------------------------------------------------------------
# 2. Base packages
# ---------------------------------------------------------------------------
log "Installing base packages (python3, venv, pip, certbot)..."
apt-get update -y -qq
apt-get install -y -qq python3 python3-pip python3-venv certbot

# bot.py needs 3.11+ (dt.UTC).
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || die \
    "python3 is $(python3 -c 'import platform; print(platform.python_version())'), but the bot needs 3.11+. \
Install a newer python3 (e.g. the deadsnakes PPA on Ubuntu: \
add-apt-repository ppa:deadsnakes/ppa && apt-get install python3.11 python3.11-venv) and re-run."

# ---------------------------------------------------------------------------
# 2b. Certificate issuance (only if requested above)
# ---------------------------------------------------------------------------
if [[ "$CERT_ISSUE" =~ ^[yY] ]]; then
    log "Requesting Let's Encrypt certificate for $CERT_DOMAIN..."
    if ss -tlnH "sport = :80" | grep -q .; then
        die "Port 80 is already in use — certbot --standalone needs it free. Stop whatever is listening on 80 and re-run."
    fi
    CERTBOT_EMAIL_ARGS=(--register-unsafely-without-email)
    [[ -n "$CERT_EMAIL" ]] && CERTBOT_EMAIL_ARGS=(-m "$CERT_EMAIL")
    certbot certonly --standalone --non-interactive --agree-tos "${CERTBOT_EMAIL_ARGS[@]}" -d "$CERT_DOMAIN"

    LE_LIVE_DIR="/etc/letsencrypt/live/$CERT_DOMAIN"
    [[ -f "$LE_LIVE_DIR/fullchain.pem" && -f "$LE_LIVE_DIR/privkey.pem" ]] || die \
        "Certificate files not found at $LE_LIVE_DIR after certbot run."

    HOSTS_BACKUP="$TT_DIR/hosts.toml.bak-$(date +%Y%m%d-%H%M%S)"
    cp "$TT_DIR/hosts.toml" "$HOSTS_BACKUP"
    sed -i -E \
        -e "s#^([[:space:]]*cert_chain_path[[:space:]]*=[[:space:]]*).*#\1\"${LE_LIVE_DIR}/fullchain.pem\"#" \
        -e "s#^([[:space:]]*private_key_path[[:space:]]*=[[:space:]]*).*#\1\"${LE_LIVE_DIR}/privkey.pem\"#" \
        "$TT_DIR/hosts.toml"
    # sed no-ops on non-matching lines — verify before claiming success.
    if ! grep -qF "${LE_LIVE_DIR}/fullchain.pem" "$TT_DIR/hosts.toml" || \
       ! grep -qF "${LE_LIVE_DIR}/privkey.pem" "$TT_DIR/hosts.toml"; then
        cp "$HOSTS_BACKUP" "$TT_DIR/hosts.toml"
        die "hosts.toml has no cert_chain_path/private_key_path lines to update \
(restored from backup, nothing changed) — edit hosts.toml manually to point at $LE_LIVE_DIR."
    fi
    log "hosts.toml updated (backup saved next to it): cert_chain_path/private_key_path -> $LE_LIVE_DIR"

    mkdir -p /etc/letsencrypt/renewal-hooks/deploy
    cat > /etc/letsencrypt/renewal-hooks/deploy/trusttunnel-reload.sh <<'EOF'
#!/usr/bin/env bash
# Reloads TrustTunnel after certbot renewal (manual or via certbot.timer).
systemctl kill -s HUP trusttunnel.service 2>/dev/null || true
EOF
    chmod 750 /etc/letsencrypt/renewal-hooks/deploy/trusttunnel-reload.sh

    systemctl kill -s HUP trusttunnel.service 2>/dev/null || systemctl restart trusttunnel.service || true
    log "TrustTunnel signaled to reload the new certificate."
fi

# ---------------------------------------------------------------------------
# 3. Bot: venv, deps, source, .env
# ---------------------------------------------------------------------------
log "Setting up the Telegram bot (venv, deps, service)..."
mkdir -p "$BOT_DIR"
python3 -m venv "$BOT_DIR/.venv"
"$BOT_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$BOT_DIR/.venv/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"

cp "$SCRIPT_DIR/bot.py" "$BOT_DIR/bot.py"
chmod 700 "$BOT_DIR/bot.py"

cat > "$BOT_DIR/.env" <<EOF
BOT_TOKEN=${BOT_TOKEN}
ALLOWED_USER_ID=${ALLOWED_USER_ID}
ENDPOINT_ADDRESS=${ENDPOINT_ADDRESS}
SERVER_NAME=${SERVER_NAME}
VPN_MONITOR_PORT=${VPN_MONITOR_PORT}
EOF
chmod 600 "$BOT_DIR/.env"

# ---------------------------------------------------------------------------
# 4. systemd — tt-bot.service
# ---------------------------------------------------------------------------
log "Installing tt-bot.service..."
cat > /etc/systemd/system/tt-bot.service <<EOF
[Unit]
Description=TrustTunnel Telegram Bot
After=network-online.target trusttunnel.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${BOT_DIR}
ExecStart=${BOT_DIR}/.venv/bin/python3 ${BOT_DIR}/bot.py
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now tt-bot.service

sleep 2
systemctl is-active --quiet tt-bot.service || die "tt-bot.service failed to start — check: journalctl -u tt-bot -n 50"

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
echo
echo "============================================================"
echo "  Done"
echo "============================================================"
echo "Bot installed at ${BOT_DIR}, running as tt-bot.service."
echo "Follow logs: journalctl -u tt-bot -f"
echo "Open the bot in Telegram and use /start."
