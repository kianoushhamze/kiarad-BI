#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${RUNNER_TEMP:?Run this script in the isolated CI runner}"
: "${GITHUB_SHA:?Exact source commit required}"
commit="$(git rev-parse HEAD)"
[ "$commit" = "$GITHUB_SHA" ] || { echo 'Checkout SHA mismatch' >&2; exit 1; }
tag="r20261120-${commit:0:12}"
backend="kiarad-transfer-backend:$tag"
frontend="kiarad-transfer-frontend:$tag"
project="kiarad-smoke-${GITHUB_RUN_ID}"
kit="$RUNNER_TEMP/Kiarad-Transfer-20261120-Offline"
[ ! -e .env ] && [ ! -e .transfer-smoke.yml ] || { echo 'CI scratch files already exist' >&2; exit 1; }
created_env=false
cleanup() {
  if [ "$created_env" = true ]; then
    docker compose --env-file .env -p "$project" -f .transfer-smoke.yml --profile traccar down -v --remove-orphans >/dev/null 2>&1 || true
    rm -f .env .transfer-smoke.yml secrets/traccar-forward.xml
  fi
}
trap cleanup EXIT

docker build --platform linux/amd64 --label "org.opencontainers.image.revision=$commit" -f Dockerfile.backend -t "$backend" .
docker build --platform linux/amd64 --label "org.opencontainers.image.revision=$commit" --build-arg KIARAD_API_URL=http://backend:8000 --build-arg NEXT_PUBLIC_API_URL=http://backend:8000 -f kiarad-dashboard/Dockerfile -t "$frontend" .
docker pull --platform linux/amd64 postgres:16
docker pull --platform linux/amd64 node:22-slim
docker pull --platform linux/amd64 traccar/traccar:6.17.0-alpine

cp transfer/compose.transfer.yml .transfer-smoke.yml
cat > .env <<EOF
DB_USER=kiarad
DB_NAME=kiaradbi
POSTGRES_PASSWORD=ci-only-disposable
KIARAD_JWT_SECRET=ci-only-disposable-signing-secret-0123456789
KIARAD_RELEASE_TAG=$tag
HOLO_AUTO_REFRESH_ENABLED=0
KIARAD_AUTOMATIONS_DISABLED=1
KIARAD_REVIEW_DISPOSABLE_DB=1
EOF
created_env=true
mkdir -p secrets
docker run --rm --user "$(id -u):$(id -g)" --mount "type=bind,source=$PWD,target=/setup" "$backend" python /app/scripts/configure_traccar.py --root /setup --client-url https://gps.ci.invalid
compose=(docker compose --env-file .env -p "$project" -f .transfer-smoke.yml --profile traccar)
"${compose[@]}" up -d --pull never --wait postgres
"${compose[@]}" run --rm --no-deps --pull never backend python init_db.py
"${compose[@]}" run --rm --no-deps --pull never backend python fix_missing_tables.py
"${compose[@]}" run --rm --no-deps --pull never backend python -c "from db import engine; from sqlalchemy import text; c=engine.connect(); t=c.begin(); c.execute(text('ALTER TABLE users ADD COLUMN IF NOT EXISTS password_version INTEGER NOT NULL DEFAULT 0')); c.execute(text('ALTER TABLE products ADD COLUMN IF NOT EXISTS price2 DOUBLE PRECISION')); c.execute(text(\"INSERT INTO products(code,name,category,price,price2,stock,is_active) VALUES ('CI-A','CI fixture','Test',10000,10000,10,1)\")); t.commit(); c.close()"
"${compose[@]}" run --rm --no-deps --pull never backend python scripts/check_release_database.py
"${compose[@]}" run --rm --no-deps --pull never backend python scripts/run_migrations.py
"${compose[@]}" up -d --no-build --pull never --wait --wait-timeout 240 backend frontend storefront traccar
"${compose[@]}" exec -T backend python scripts/ci_traccar_smoke.py --seed
docker run --rm --network host -e KIARAD_REVIEW_DISPOSABLE_DB=1 --mount "type=bind,source=$RUNNER_TEMP,target=/evidence" "$backend" python scripts/ci_traccar_smoke.py --output /evidence/traccar-smoke.json
curl --fail --silent --show-error http://127.0.0.1:8800/health
curl --fail --silent --show-error http://127.0.0.1:3300/api/health
curl --fail --silent --show-error http://127.0.0.1:3300/login -o "$RUNNER_TEMP/kiarad-login.html"
curl --fail --silent --show-error http://127.0.0.1:8190/buy/ -o "$RUNNER_TEMP/kiarad-buy.html"
curl --fail --silent --show-error http://127.0.0.1:8190/api/public/catalog -o "$RUNNER_TEMP/kiarad-catalog.json"
python - "$RUNNER_TEMP/kiarad-catalog.json" <<'PY'
import json,sys
assert any(row['code']=='CI-A' for row in json.load(open(sys.argv[1]))['products'])
PY
asset="$(python - "$RUNNER_TEMP/kiarad-login.html" <<'PY'
import re,sys
print(re.search(r'<script[^>]+src="([^\"]+)"', open(sys.argv[1]).read())[1])
PY
)"
curl --fail --silent --show-error "http://127.0.0.1:3300$asset" -o /dev/null
status="$(curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:8800/site-cms/products)"
[ "$status" = 401 ] || { echo 'Anonymous CMS access was not blocked' >&2; exit 1; }

python scripts/build_transfer_kit.py --output "$kit"
mkdir "$kit/payload"
docker save -o "$kit/payload/images.tar" "$backend" "$frontend" postgres:16 node:22-slim traccar/traccar:6.17.0-alpine
python - "$kit" "$backend" "$frontend" <<'PY'
import hashlib,json,subprocess,sys,os
from pathlib import Path
kit=Path(sys.argv[1]);release=json.loads((kit/'release.json').read_text());records=[]
for name in [*sys.argv[2:],'postgres:16','node:22-slim','traccar/traccar:6.17.0-alpine']:
 info=json.loads(subprocess.check_output(['docker','image','inspect',name]))[0]
 assert info['Os']=='linux' and info['Architecture']=='amd64'
 records.append({'name':name,'id':info['Id']})
with (kit/'payload/images.tar').open('rb') as handle: digest=hashlib.file_digest(handle,'sha256').hexdigest().upper()
(kit/'payload/images.json').write_text(json.dumps({'source_commit':release['source_commit'],'images':records,'archive_sha256':digest},indent=2)+'\n')
release['includes_images']=True
release['includes_traccar_gateway']=True
release['container_smoke_test']='passed on isolated CI PostgreSQL with synthetic product; not company acceptance'
(kit/'release.json').write_text(json.dumps(release,indent=2)+'\n')
(kit/'validation/container-smoke.json').write_text(json.dumps({'passed':True,'source_commit':release['source_commit'],'company_data_used':False,'checks':['core_schema','migrations','backend_health','frontend_health_proxy','login_html','login_asset','storefront_html','storefront_live_catalog','anonymous_cms_denial','real_traccar_to_consented_dashboard']},indent=2)+'\n')
import shutil
shutil.copyfile(Path(os.environ['RUNNER_TEMP'])/'traccar-smoke.json',kit/'validation/traccar-smoke.json')
checks=[]
for path in sorted(kit.rglob('*')):
 if path.is_file() and path.name!='checksums.json':
  with path.open('rb') as handle: sha=hashlib.file_digest(handle,'sha256').hexdigest().upper()
  checks.append({'path':path.relative_to(kit).as_posix(),'bytes':path.stat().st_size,'sha256':sha})
(kit/'checksums.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps({'source_commit':release['source_commit'],'images':len(records),'archive_bytes':(kit/'payload/images.tar').stat().st_size,'smoke_test':'passed'}))
PY
