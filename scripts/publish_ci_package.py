"""Verify an exact CI kit and archive it in a draft Release, outside Actions quota."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import zipfile


def verify_kit(root, commit):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Expected a full source commit')
    release = json.loads((root / 'release.json').read_text(encoding='utf-8'))
    if release.get('source_commit') != commit:
        raise ValueError('Package source commit mismatch')
    if release.get('includes_company_data') is not False or release.get('company_acceptance_complete') is not False:
        raise ValueError('Only company-data-free, unaccepted CI packages may be archived')
    records = json.loads((root / 'checksums.json').read_text(encoding='utf-8'))
    names = set()
    for row in records:
        name = row['path']
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or name in names or name == 'checksums.json':
            raise ValueError('Unsafe or duplicate package path')
        if any(part in {'secrets', 'private_exports', 'private_uploads', '.git', 'node_modules'} or
               (part.startswith('.env') and not part.endswith('.example')) for part in relative.parts):
            raise ValueError('Runtime material in package')
        names.add(name)
        path = root / name
        if any(part.is_symlink() for part in [path, *path.parents]):
            raise ValueError('Package symlinks are not supported')
        if not path.is_file() or path.stat().st_size != row['bytes']:
            raise ValueError('Package file missing or size mismatch: ' + name)
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest().upper()
        if digest != row['sha256'].upper():
            raise ValueError('Package checksum mismatch: ' + name)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    if actual != names | {'checksums.json'}:
        raise ValueError('Unlisted files in package')
    if not {'release.json', 'source.zip', 'source-files.json'}.issubset(names):
        raise ValueError('Missing source identity files')
    with zipfile.ZipFile(root / 'source.zip') as archive:
        for name in archive.namelist():
            if name == '.env' or name.startswith(('secrets/', 'private_exports/', 'private_uploads/', '.git/')) or '/node_modules/' in name:
                raise ValueError('Runtime material in source archive')
    return release, sorted(names | {'checksums.json'})


def create_archive(root, output, commit):
    release, names = verify_kit(root, commit)
    # Keep generated delivery archives outside the kit being verified.
    if output.resolve().is_relative_to(root.resolve()):
        raise ValueError('Archive output must be outside the package')
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in names:
            archive.write(root / name, name)
    return release


def gh(*args, body=None):
    result = subprocess.run(['gh', *args], input=json.dumps(body) if body is not None else None,
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit', required=True, type=Path)
    args = parser.parse_args()
    repo, commit, run_id = (os.environ[k] for k in ('GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_RUN_ID'))
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if actual != commit:
        raise ValueError('Checkout SHA differs from workflow SHA')
    if os.environ.get('GITHUB_EVENT_NAME') not in {'push', 'pull_request', 'workflow_dispatch'}:
        raise ValueError('Unsupported publication event')
    tag = 'ci-package-' + run_id
    attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '1')
    metadata = json.loads((args.kit / 'release.json').read_text())
    kind = 'Offline' if metadata.get('includes_images') else 'Source'
    output = Path(os.environ['RUNNER_TEMP']) / f'Kiarad-{kind}-{commit[:12]}-attempt{attempt}.zip'
    release = create_archive(args.kit, output, commit)
    evidence = json.loads((args.kit / 'ci.json').read_text())
    if evidence.get('source_commit') != commit or str(evidence.get('run_id')) != run_id:
        raise ValueError('Package CI identity differs from the current run')
    prefix = f'repos/{repo}/releases'
    releases = gh('api', prefix + '?per_page=100')
    existing = next((r for r in releases if r['tag_name'] == tag), None)
    if existing is None:
        existing = gh('api', '-X', 'POST', prefix, '--input', '-', body={
            'tag_name': tag, 'target_commitish': commit, 'name': 'Kiarad CI package ' + commit[:12],
            'draft': True, 'prerelease': True, 'make_latest': 'false',
            'body': f'Exact source: `{commit}`. CI: https://github.com/{repo}/actions/runs/{run_id}\n\n'
                    'Draft software package, not company acceptance. Source and Offline ZIPs include their own '
                    'release identity, checksums and Persian manual. No company database or credentials are included.'})
    if not existing['draft'] or existing['target_commitish'] != commit:
        raise ValueError('Existing release identity or audience differs')
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    assets = gh('api', f"{prefix}/{existing['id']}/assets?per_page=100")
    asset = next((a for a in assets if a['name'] == output.name), None)
    if asset is None:
        subprocess.run(['gh', 'release', 'upload', tag, str(output), '-R', repo], check=True)
        assets = gh('api', f"{prefix}/{existing['id']}/assets?per_page=100")
        asset = next(a for a in assets if a['name'] == output.name)
    if asset['state'] != 'uploaded' or asset['size'] != output.stat().st_size or asset.get('digest') != 'sha256:' + digest:
        raise ValueError('Remote asset digest or size differs; keep original for review')
    # Small sidecars let the owner inspect identity and checksums without first
    # downloading the complete Linux image archive.
    for filename in ('release.json', 'ci.json', 'checksums.json'):
        sidecar = output.with_name(output.stem + '.' + filename)
        shutil.copyfile(args.kit / filename, sidecar)
        wanted = hashlib.sha256(sidecar.read_bytes()).hexdigest()
        present = next((a for a in assets if a['name'] == sidecar.name), None)
        if present is None:
            subprocess.run(['gh', 'release', 'upload', tag, str(sidecar), '-R', repo], check=True)
            assets = gh('api', f"{prefix}/{existing['id']}/assets?per_page=100")
            present = next(a for a in assets if a['name'] == sidecar.name)
        if present.get('digest') != 'sha256:' + wanted or present['size'] != sidecar.stat().st_size:
            raise ValueError('Remote metadata sidecar differs')
    report = {'release_id': existing['id'], 'release_url': existing['html_url'], 'asset_id': asset['id'],
              'asset_name': output.name, 'sha256': digest, 'source_commit': commit,
              'includes_images': release['includes_images'], 'company_acceptance_complete': False}
    print(json.dumps(report))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write(f"\nPackage: {existing['html_url']}\n\n`{output.name}`\n\nSHA256: `{digest}`\n")


if __name__ == '__main__':
    main()
