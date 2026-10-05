#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }
usage() { printf 'Usage: bash scripts/demo-up.sh --project researcy-m5-NAME --env-file PATH --override PATH\n' >&2; exit 2; }
project='' env_file='' override=''
while (($#)); do
    (($# >= 2)) || usage
    case "$1" in
        --project) [[ -z "$project" ]] || usage; project=$2 ;;
        --env-file) [[ -z "$env_file" ]] || usage; env_file=$2 ;;
        --override) [[ -z "$override" ]] || usage; override=$2 ;;
        *) usage ;;
    esac
    shift 2
done
[[ "$project" =~ ^researcy-m5-[a-z0-9][a-z0-9-]*$ && ${#project} -le 63 ]] || fail 'an isolated project in the researcy-m5 namespace is required'
namespace=${project#researcy-}
[[ "${override##*/}" == "$namespace.private.yaml" ]] || fail 'an explicitly named M5 private override is required'
[[ "${env_file##*/}" == "$namespace.env" ]] || fail 'an explicitly named M5 environment file is required'
[[ -f "$env_file" && ! -L "$env_file" && -f "$override" && ! -L "$override" ]] || fail 'private configuration files must exist and must not be symlinks'
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ "$root" == */.omp/worktrees/* ]] || fail 'startup must run from the approved isolated worktree, never main'
command -v docker >/dev/null || fail 'Docker Compose is required'
command -v uv >/dev/null || fail 'uv and Python 3.12 are required for private Settings validation'
umask 077
private=$(mktemp -d "${TMPDIR:-/tmp}/researcy-m5-startup.XXXXXXXX")
trap 'rm -rf "$private"' EXIT
# Host shell variables must not silently override the explicit isolated env file.
compose=(env -i "PATH=$PATH" "HOME=$HOME" "DOCKER_CONFIG=${DOCKER_CONFIG:-$HOME/.docker}" docker compose
    --project-name "$project" --project-directory "$root" --env-file "$env_file"
    -f "$root/compose.yaml" -f "$override" --profile web --profile processing)
step() {
    local label=$1; shift
    if ! "$@" >"$private/step.log" 2>&1; then
        fail "$label (private diagnostic output suppressed; isolated volumes preserved)"
    fi
    printf 'OK: %s\n' "$label"
}
"${compose[@]}" config --format json >"$private/config.json" 2>"$private/config-error.log" || fail 'Compose configuration is invalid (details suppressed)'
# Validate rendered isolation BEFORE any build/start/stop/run. Settings receives the
# actual container environment, not a second hand-maintained settings parser.
if ! uv run --frozen --project "$root/apps/api" python - "$private/config.json" "$project" "$root" "$env_file" "$override" >"$private/summary.json" 2>"$private/validation.log" <<'PY'
import json
import os
from pathlib import Path
import stat
import sys
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(sys.argv[3]) / 'apps/api'))
from researcy.config import GEMINI_EXACT_ENDPOINT, Settings


def require(condition):
    if not condition:
        raise ValueError('isolated configuration rejected')


try:
    config_path, project, root, env_file, override = sys.argv[1:]
    for path in (env_file, override):
        require(stat.S_IMODE(Path(path).stat().st_mode) & 0o077 == 0)
        require(Path(path).resolve().name.startswith(project.removeprefix('researcy-')))
    config = json.loads(Path(config_path).read_text())
    require(config.get('name') == project)
    for volume in config.get('volumes', {}).values():
        require(not volume.get('external') and not volume.get('driver_opts')
            and volume.get('driver', 'local') == 'local'
            and volume.get('name', '').startswith(project + '_'))
    for network in config.get('networks', {}).values():
        require(not network.get('external') and not network.get('driver_opts')
            and network.get('driver', 'bridge') == 'bridge'
            and network.get('name', '').startswith(project + '_'))
    services = config['services']
    require(set(services) == {'postgres', 'minio', 'minio-init', 'qdrant', 'api', 'worker', 'web'})
    caps = {'postgres': 384, 'minio': 256, 'minio-init': 256, 'qdrant': 512,
        'api': 512, 'worker': 1024, 'web': 256}
    forbidden_ports = {3000, 8000, 55432, 9000, 9001}
    published = set()
    for name, service in services.items():
        require(not service.get('container_name') and not service.get('privileged')
            and not service.get('network_mode') and not service.get('volumes_from')
            and not service.get('devices') and not service.get('cap_add'))
        require(not service.get('pid') and not service.get('ipc')
            and not service.get('uts') and not service.get('use_api_socket'))
        require(set(service.get('networks', {'default': {}})) == {'default'})
        require(not service.get('configs') and not service.get('secrets'))
        require(all(alias == 'host.docker.internal=host-gateway' for alias in service.get('extra_hosts', [])))
        if name != 'minio-init' or 'mem_limit' in service:
            require(0 < int(service.get('mem_limit', 0)) <= caps[name] * 1024 * 1024)
        require(len(service.get('volumes', [])) == (1 if name in ('postgres', 'minio', 'qdrant') else 0))
        for mount in service.get('volumes', []):
            expected = {'postgres': ('postgres-data', '/var/lib/postgresql/data'),
                'minio': ('minio-data', '/data'), 'qdrant': ('qdrant-data', '/qdrant/storage')}.get(name)
            require(expected is not None and mount.get('type') == 'volume'
                and (mount.get('source'), mount.get('target')) == expected)
            require(not mount.get('volume', {}).get('subpath'))
        for port in service.get('ports', []):
            require(port.get('host_ip') == '127.0.0.1' and port.get('protocol', 'tcp') == 'tcp')
            value = int(port['published'])
            require(1024 <= value <= 65535 and value not in forbidden_ports and value not in published)
            published.add(value)
        if name in ('api', 'worker', 'web'):
            build = service['build']
            require(Path(build['context']).resolve() == Path(root) / 'apps' / ('web' if name == 'web' else 'api'))
            target = 'runner' if name == 'web' else 'production'
            require(build.get('dockerfile', 'Dockerfile') == 'Dockerfile'
                and build.get('target', target) == target
                and set(build) <= {'context', 'dockerfile', 'target'})
            require(not service.get('image') or service['image'].startswith(project + '-')
                or service['image'].startswith(project + '_'))
        else:
            expected_images = {'postgres': 'postgres:17.6-alpine',
                'minio': 'quay.io/minio/minio:RELEASE.2025-02-07T23-21-09Z',
                'minio-init': 'quay.io/minio/mc:RELEASE.2025-02-08T19-14-21Z',
                'qdrant': 'qdrant/qdrant:v1.19.0@sha256:057ee3a8da769fe7310dd3537b4dc7583bf87a95ce8ac43c0af5a46bc580d1fc'}
            require(service.get('image') == expected_images[name])
    require(set(config.get('volumes', {})) == {'postgres-data', 'minio-data', 'qdrant-data'})
    require(services['worker'].get('command') == ['python', '-m', 'researcy.ingestion.worker'])
    require(not services['api'].get('command') and not services['web'].get('command'))
    require(all(not services[name].get('entrypoint') for name in ('api', 'worker', 'web', 'postgres', 'minio', 'qdrant')))
    require(services['minio-init'].get('entrypoint') == ['/bin/sh', '-ec'])
    init_command = services['minio-init'].get('command')
    require(type(init_command) is list and len(init_command) == 1 and init_command[0].strip().replace('$$', '$') ==
        'until mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do sleep 1; done\n'
        'mc mb --ignore-existing "local/$MINIO_BUCKET"\n'
        'mc anonymous set none "local/$MINIO_BUCKET"')
    require(services['minio'].get('command') == ['server', '/data', '--console-address', ':9001'])
    require(services['api'].get('read_only') and services['worker'].get('read_only'))
    require(services['api'].get('user') == '65534:65534' and services['worker'].get('user') == '65534:65534')
    require(services['api'].get('cap_drop') == ['ALL'] and services['worker'].get('cap_drop') == ['ALL'])
    for role in ('api', 'worker'):
        service = services[role]
        require(0 < int(service.get('pids_limit', 0)) <= 64 and service.get('init'))
        options = service.get('security_opt', [])
        require(len(options) == 2 and any(value in ('no-new-privileges:true', 'no-new-privileges=true')
            for value in options))
        seccomp = [value for value in options if value.startswith(('seccomp=', 'seccomp:'))]
        require(len(seccomp) == 1)
        profile_path = Path(seccomp[0][8:])
        if not profile_path.is_absolute():
            profile_path = Path(root) / profile_path
        require(profile_path.resolve() == Path(root) / 'deploy/parser-seccomp.json')
        tmpfs = service.get('tmpfs', [])
        require(len(tmpfs) == 1 and tmpfs[0].startswith('/tmp:'))
        flags = set(tmpfs[0].split(':', 1)[1].split(','))
        require({'rw', 'noexec', 'nosuid'} <= flags)
        cap = 64 if role == 'api' else 384
        require(any('size=' + value in flags for value in (str(cap) + 'm', str(cap * 1024 * 1024))))
    web_ports = services['web'].get('ports', [])
    require(len(web_ports) == 1 and web_ports[0]['target'] == 3000)
    api_ports = services['api'].get('ports', [])
    require(len(api_ports) == 1 and api_ports[0]['target'] == 8000)
    web_port = int(web_ports[0]['published'])
    settings = {}
    for role in ('api', 'worker'):
        environment = services[role]['environment']
        os.environ.clear()
        os.environ.update({key: str(value) for key, value in environment.items() if value is not None})
        value = Settings.from_env()
        require(value.app_role == role)
        database = urlsplit(value.database_url)
        pg = services['postgres']['environment']
        require(database.scheme in ('postgres', 'postgresql') and database.hostname == 'postgres'
            and database.port == 5432 and not database.query and not database.fragment
            and unquote(database.path.lstrip('/')) == pg['POSTGRES_DB']
            and unquote(database.username or '') == pg['POSTGRES_USER']
            and unquote(database.password or '') == pg['POSTGRES_PASSWORD'])
        require(value.storage_minio_endpoint == 'minio:9000' and not value.storage_secure
            and value.storage_access_key == services['minio']['environment']['MINIO_ROOT_USER']
            and value.storage_secret_key == services['minio']['environment']['MINIO_ROOT_PASSWORD']
            and value.storage_bucket == services['minio-init']['environment']['MINIO_BUCKET'])
        require(value.qdrant_endpoint == 'http://qdrant:6333'
            and value.embedding_endpoint == 'http://host.docker.internal:11434')
        settings[role] = value
    api = settings['api']
    require(settings['worker'].database_url == api.database_url)
    require(len(api.trusted_origins) == 1)
    origin = api.trusted_origins[0]
    require(origin in (f'http://localhost:{web_port}', f'http://127.0.0.1:{web_port}'))
    require(api.google_redirect_uri == origin + '/auth/google/callback'
        and api.google_client_id and api.google_client_secret and len(api.session_lookup_key) >= 32)
    require(api.generation_provider == 'gemini' and api.generation_endpoint == GEMINI_EXACT_ENDPOINT
        and api.generation_model == 'gemini-3.8-flash' and api.generation_api_key)
    require(services['web']['environment'].get('API_INTERNAL_URL') == 'http://api:8000')
    print(json.dumps({'url': origin}))
except Exception:
    print('Isolated configuration or Settings validation failed; secrets suppressed.', file=sys.stderr)
    sys.exit(1)
PY
then
    fail 'isolated configuration or Settings validation failed (secrets suppressed)'
fi
printf 'OK: isolated namespace, private volumes, resource caps and actual Settings validated\n'
step 'frozen API/web/worker images built' "${compose[@]}" build api web worker
# On a repeat startup, only this validated isolated worker is quiesced before migrations.
step 'isolated worker quiesced before migration' "${compose[@]}" stop --timeout 90 worker
step 'PostgreSQL healthy' "${compose[@]}" up -d --wait --wait-timeout 90 postgres
step 'MinIO process started' "${compose[@]}" up -d --no-deps minio
step 'MinIO health verified before bucket initialization' "${compose[@]}" run --rm --no-deps --entrypoint python api -c '
import time
import httpx2
end = time.monotonic() + 60
while time.monotonic() < end:
    try:
        with httpx2.Client(timeout=2, trust_env=False) as client:
            if client.get("http://minio:9000/minio/health/ready").status_code == 200:
                break
    except httpx2.RequestError:
        pass
    time.sleep(1)
else:
    raise SystemExit(1)
'
step 'private bucket initialized' "${compose[@]}" up --no-deps --abort-on-container-exit --exit-code-from minio-init minio-init
step 'Qdrant healthy' "${compose[@]}" up -d --no-deps --wait --wait-timeout 90 qdrant
step 'database migration first application' "${compose[@]}" run --rm --no-deps api alembic upgrade head
step 'database migration second application' "${compose[@]}" run --rm --no-deps api alembic upgrade head
if ! "${compose[@]}" run --rm --no-deps --entrypoint python worker -c '
import json
from researcy.ingestion.preflight import run_preflight
result = run_preflight()
print(json.dumps(result))
' >"$private/preflight.json" 2>"$private/preflight.log"; then
    fail 'processing preflight or native warm failed (private diagnostics suppressed; volumes preserved)'
fi
uv run --frozen --project "$root/apps/api" python - "$private/preflight.json" <<'PY'
import json
import sys
try:
    result = json.loads(open(sys.argv[1]).read())
    identity = result['embedding']
    assert result['status'] == 'ok'
    print('OK: DB revision, private object write/read/delete probe, Qdrant schema and sandbox')
    print('OK: native identity and warm embedding vector verified; digest=' + identity['model_digest'])
except Exception:
    print('FAIL: preflight summary unavailable', file=sys.stderr)
    sys.exit(1)
PY
step 'API/web/isolated worker started' "${compose[@]}" up -d --no-deps --wait --wait-timeout 120 api web worker
if ! "${compose[@]}" exec -T api python -c '
import json
import sys
import time
import httpx2
with httpx2.Client(timeout=20, trust_env=False) as client:
    deadline = time.monotonic() + 120
    while True:
        healthy = True
        try:
            for url in ("http://127.0.0.1:8000/health", "http://web:3000/"):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Application startup deadline exceeded")
                if client.get(url, timeout=min(20, remaining)).status_code != 200:
                    healthy = False
                    break
        except httpx2.RequestError:
            healthy = False
        if healthy:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Application startup deadline exceeded")
        time.sleep(min(1, remaining))
    response = client.get("http://127.0.0.1:8000/ready")
    print(json.dumps(response.json()))
    assert response.status_code in (200, 503)
' >"$private/readiness.json" 2>"$private/readiness.log"; then
    fail 'liveness, production web or dependency/catalog readiness failed; generation execution unverified, qualification pending (volumes preserved)'
fi
uv run --frozen --project "$root/apps/api" python - "$private/summary.json" "$private/readiness.json" <<'PY'
import json
import sys
try:
    summary = json.loads(open(sys.argv[1]).read())
    result = json.loads(open(sys.argv[2]).read())
    print('URL: ' + summary['url'])
    print('Liveness: healthy; production web: reachable')
    allowed = {'postgres': {'verified', 'unavailable'}, 'private_bucket': {'verified', 'unavailable', 'unconfigured'},
        'qdrant': {'verified', 'unavailable'}, 'native_identity': {'verified', 'unavailable'},
        'native_model': {'loaded', 'cold', 'unavailable'},
        'generation_configuration': {'configured', 'unconfigured'},
        'generation_access': {'accessible', 'unavailable', 'unconfigured'}, 'generation_execution': {'unverified'}}
    assert all(result.get(name) in states for name, states in allowed.items())
    for name in allowed:
        print(name + ': ' + result[name])
    print('Qualification: pending — first approved application run supplies fresh role evidence; no generation probe was sent.')
    if result.get('status') != 'ready':
        print('FAIL: dependency/catalog readiness unavailable; isolated volumes preserved', file=sys.stderr)
        sys.exit(1)
except Exception:
    print('FAIL: safe startup summary unavailable', file=sys.stderr)
    sys.exit(1)
PY
printf 'Shutdown preserves data: use the same explicit env-file/override/project with docker compose down (never -v).\n'
