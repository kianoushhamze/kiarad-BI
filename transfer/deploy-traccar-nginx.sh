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
cert_dir=/etc/letsencrypt/live/$host

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
nginx -t -q
install -d -m 755 "$webroot"
tmp=$(mktemp)
cleanup() {
    local result=$?
    trap - exit
    if ((result != 0)); then
        rm -f -- "$link" "$site"
        nginx -t -q && systemctl reload nginx || true
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
if [[ -s $cert_dir/fullchain.pem && -s $cert_dir/privkey.pem ]] &&
    openssl x509 -in "$cert_dir/fullchain.pem" -checkend 0 -noout >/dev/null; then
    echo 'using existing gps certificate'
else
    install -m 644 "$tmp" "$site"
    ln -s "$site" "$link"
    nginx -t -q
    systemctl reload nginx

    certbot certonly --webroot -w "$webroot" -d "$host" --cert-name "$host" \
        --non-interactive --keep-until-expiring \
        --deploy-hook 'nginx -t -q && systemctl reload nginx'
fi

cat >> "$tmp" <<nginx_https
limit_req_zone \$binary_remote_addr zone=kiarad_gps:10m rate=5r/s;
server {
    listen 443 ssl;
    server_name $host;
    ssl_certificate $cert_dir/fullchain.pem;
    ssl_certificate_key $cert_dir/privkey.pem;
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
if [[ ! -L $link ]]; then
    ln -s "$site" "$link"
fi
nginx -t -q
systemctl reload nginx

for attempt in {1..8}; do
    if probe=$(curl --noproxy '*' --resolve "$host:443:127.0.0.1" --silent --show-error \
        --connect-timeout 2 --max-time 5 --output /dev/null --write-out '%{http_code}' \
        "https://$host/" 2>&1) && [[ $probe == 400 ]]; then
        printf 'gps_https_ready=%s\n' "$probe"
        exit 0
    fi
    if ((attempt < 8)); then
        sleep 1
    fi
done
printf 'traccar https verification failed: %s\n' "$probe" >&2
printf 'certificate loaded from disk: ' >&2
openssl x509 -in "$cert_dir/fullchain.pem" -noout -ext subjectAltName >&2 || true
printf 'certificate served on 127.0.0.1:443: ' >&2
timeout 5 openssl s_client -connect 127.0.0.1:443 -servername "$host" </dev/null 2>/dev/null |
    openssl x509 -noout -ext subjectAltName >&2 || true
exit 1
