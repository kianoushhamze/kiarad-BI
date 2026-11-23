#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 3 || $EUID != 0 ]]; then
    echo 'usage (as root): deploy-traccar-nginx.sh hostname wireguard-source-ip traccar-peer-ip' >&2
    exit 1
fi

host=$1
source_ip=$2
peer_ip=$3
ipv4='^([0-9]{1,3}\.){3}[0-9]{1,3}$'
if [[ ! $host =~ ^[a-z0-9][a-z0-9.-]*[a-z0-9]$ || ! $source_ip =~ $ipv4 || ! $peer_ip =~ $ipv4 ]]; then
    echo 'expected a DNS hostname and two IPv4 addresses' >&2
    exit 1
fi

site=/etc/nginx/sites-available/$host
link=/etc/nginx/sites-enabled/$host
webroot=/var/www/kiarad-gps-acme

code=$(curl --noproxy '*' --interface "$source_ip" --silent --show-error --max-time 8 \
    --output /dev/null --write-out '%{http_code}' "http://$peer_ip:5055/")
if [[ $code != 400 ]]; then
    printf 'unexpected traccar wireguard response: %s\n' "$code" >&2
    exit 1
fi
if [[ -e $site || -L $site || -e $link || -L $link ]]; then
    echo 'nginx site already exists' >&2
    exit 1
fi
nginx -t
install -d -m 755 "$webroot"
tmp=$(mktemp)
cleanup() {
    local result=$?
    trap - exit
    if ((result != 0)); then
        rm -f -- "$link" "$site"
        nginx -t && systemctl reload nginx || true
    fi
    rm -f -- "$tmp"
    exit "$result"
}
trap cleanup exit

cat > "$tmp" <<nginx_http
server {
    listen 80;
    server_name $host;
    access_log off;
    error_log /var/log/nginx/kiarad-gps-error.log crit;

    location ^~ /.well-known/acme-challenge/ {
        root $webroot;
        try_files \$uri =404;
    }
    location / { return 404; }
}
nginx_http
install -m 644 "$tmp" "$site"
ln -s "$site" "$link"
nginx -t
systemctl reload nginx

certbot certonly --webroot -w "$webroot" -d "$host" --cert-name "$host" \
    --non-interactive --keep-until-expiring \
    --deploy-hook 'nginx -t && systemctl reload nginx'

cat >> "$tmp" <<nginx_https
limit_req_zone \$binary_remote_addr zone=kiarad_gps:10m rate=5r/s;
server {
    listen 443 ssl;
    server_name $host;
    ssl_certificate /etc/letsencrypt/live/$host/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$host/privkey.pem;
    access_log off;
    error_log /var/log/nginx/kiarad-gps-error.log crit;
    client_max_body_size 8k;

    location / {
        limit_req zone=kiarad_gps burst=20 nodelay;
        proxy_bind $source_ip;
        proxy_pass http://$peer_ip:5055;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 5s;
        proxy_read_timeout 15s;
    }
}
nginx_https
install -m 644 "$tmp" "$site"
nginx -t
systemctl reload nginx

code=$(curl --noproxy '*' --resolve "$host:443:127.0.0.1" --silent --show-error \
    --max-time 12 --output /dev/null --write-out '%{http_code}' "https://$host/")
if [[ $code != 400 ]]; then
    printf 'unexpected traccar https response: %s\n' "$code" >&2
    exit 1
fi
printf 'gps_https_ready=%s\n' "$code"
