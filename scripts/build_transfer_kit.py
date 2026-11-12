"""Build a checksummed source-and-tools kit; company runtime data stays separate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def git_snapshot(root):
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    entries = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=root).decode('utf-8')
    files = []
    for entry in entries.split('\0'):
        if not entry:
            continue
        metadata, path = entry.split('\t', 1)
        mode, sha, stage = metadata.split()
        if mode not in {'100644', '100755'} or stage != '0':
            raise ValueError('Unsupported or conflicted Git entry: ' + path)
        files.append({'path': path, 'sha': sha})
    return {'commit': commit, 'files': files}


def build(root, snapshot, output, evidence, provisional=False):
    if output.exists():
        raise ValueError('Use a new output folder; existing kits are never overwritten.')
    commit = snapshot['commit']
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('Expected a full Git commit SHA.')
    output.mkdir(parents=True)
    records = []
    with zipfile.ZipFile(output / 'source.zip', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=8) as archive:
        seen = set()
        for entry in sorted(snapshot['files'], key=lambda row: row['path']):
            name = entry['path']
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts or name in seen:
                raise ValueError('Unsafe or duplicate source path: ' + name)
            seen.add(name)
            if name == '.env' or name.startswith(('secrets/', 'private_uploads/', 'private_exports/', '.git/')) or '/node_modules/' in name:
                raise ValueError('Runtime secrets or build material in source inventory: ' + name)
            path = root / relative
            if path.is_symlink():
                raise ValueError('Source symlink is not supported: ' + name)
            data = path.read_bytes()
            blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if blob != entry['sha']:
                raise ValueError('Source differs from Git snapshot: ' + name)
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
            records.append({'path': name, 'git_blob_sha': blob, 'sha256': hashlib.sha256(data).hexdigest()})
    with zipfile.ZipFile(output / 'source.zip') as archive:
        if archive.testzip() is not None:
            raise ValueError('Source ZIP integrity check failed.')
    for path in (root / 'transfer').iterdir():
        if path.is_file():
            shutil.copyfile(path, output / path.name)
    shutil.copyfile(root / 'docs/General_Debug_20261112.md', output / 'General_Debug_20261112.md')
    shutil.copyfile(root / 'docs/Agent_Mobile_Handoff_20261113.md', output / 'Agent_Mobile_Handoff_20261113.md')
    shutil.copyfile(root / 'docs/Completion_Validation_20261113.md', output / 'Completion_Validation_20261113.md')
    release = {'source_commit': commit, 'image_tag': 'r20261113-' + commit[:12], 'prepared_for': '2026-11-13',
               'timezone': 'Asia/Tehran', 'architecture': 'linux/amd64', 'source_files': len(records),
               'includes_images': False, 'includes_company_data': False, 'company_acceptance_complete': False,
               'provisional_test_kit': provisional}
    (output / 'release.json').write_text(json.dumps(release, indent=2) + '\n', encoding='utf-8')
    (output / 'source-files.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
    if evidence.is_dir():
        shutil.copytree(evidence, output / 'validation')
    if os.getenv('GITHUB_RUN_ID'):
        (output / 'ci.json').write_text(json.dumps({'run_id': os.environ['GITHUB_RUN_ID'],
                                                  'source_commit': commit, 'event': os.getenv('GITHUB_EVENT_NAME'),
                                                  'url': f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"}, indent=2) + '\n')
    hashes = [{'path': path.relative_to(output).as_posix(), 'bytes': path.stat().st_size,
               'sha256': hashlib.sha256(path.read_bytes()).hexdigest().upper()}
              for path in sorted(output.rglob('*')) if path.is_file()]
    (output / 'checksums.json').write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf-8')
    return release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, help='Verified GitHub tree inventory, for connector-based source retrieval')
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--provisional', action='store_true')
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text()) if args.snapshot else git_snapshot(args.root)
    release = build(args.root, snapshot, args.output, args.evidence or args.root / 'transfer/validation',
                    args.provisional or os.getenv('GITHUB_EVENT_NAME') == 'pull_request')
    print(json.dumps(release))


if __name__ == '__main__':
    main()
