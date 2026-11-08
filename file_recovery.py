"""Private file backup and restore into a NEW directory, never over live uploads."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile

ROOT_NAMES={'team_chat','catalog_uploads'}


def file_digest(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def create_bundle(roots, archive):
    archive=Path(archive)
    if archive.exists():raise ValueError('archive_exists')
    if set(roots)!=ROOT_NAMES:raise ValueError('unexpected_roots')
    for root in roots.values():
        if Path(root).resolve() in archive.resolve().parents:raise ValueError('archive_inside_source')
    partial=archive.with_suffix(archive.suffix+'.partial')
    partial_created=False
    manifest={'version':1,'roots':{},'files':[]}
    try:
        with partial.open('xb') as target:
            partial_created=True
        with partial.open('wb') as target,zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
            for name,root in roots.items():
                root=Path(root)
                if root.is_symlink():raise ValueError('source_symlink')
                manifest['roots'][name]={'exists':root.exists()}
                if not root.exists():continue
                if not root.is_dir():raise ValueError('source_not_directory')
                for path in sorted(root.rglob('*')):
                    if path.is_symlink() or path.is_junction():raise ValueError('source_link')
                    if not path.is_file():continue
                    if root.resolve() not in path.resolve().parents:raise ValueError('source_escape')
                    before=path.stat();key=name+'/'+path.relative_to(root).as_posix()
                    digest=hashlib.sha256();length=0
                    with path.open('rb') as source,bundle.open(key,'w',force_zip64=True) as output:
                        for chunk in iter(lambda:source.read(1024*1024),b''):
                            output.write(chunk);digest.update(chunk);length+=len(chunk)
                    after=path.stat()
                    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or length!=before.st_size:
                        raise ValueError('source_changed_during_backup')
                    manifest['files'].append({'path':key,'bytes':length,'sha256':digest.hexdigest()})
            bundle.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
        # Never replace an earlier backup.
        with archive.open('xb') as final,partial.open('rb') as source:shutil.copyfileobj(source,final)
    finally:
        if partial_created:partial.unlink(missing_ok=True)
    return manifest


def restore_bundle(archive,destination):
    destination=Path(destination)
    if destination.exists():raise ValueError('destination_must_be_new')
    with zipfile.ZipFile(archive) as bundle:
        names=bundle.namelist()
        if len(names)!=len(set(names)):raise ValueError('duplicate_members')
        manifest=json.loads(bundle.read('manifest.json'))
        if manifest.get('version')!=1 or set(manifest.get('roots',{}))!=ROOT_NAMES:raise ValueError('invalid_manifest')
        entries=manifest['files'];expected={'manifest.json'}
        for item in entries:
            key=item['path'];parts=PurePosixPath(key).parts
            if not parts or parts[0] not in ROOT_NAMES or len(parts)<2 or '..' in parts or '\\' in key or ':' in key or PurePosixPath(key).is_absolute():
                raise ValueError('unsafe_member')
            expected.add(key)
            info=bundle.getinfo(key)
            if stat.S_ISLNK(info.external_attr>>16) or info.file_size!=item['bytes']:raise ValueError('invalid_member')
        if len(expected)!=len(entries)+1 or expected!=set(names):raise ValueError('unexpected_members')
        # Validate all content before creating any restored files.
        for item in entries:
            digest=hashlib.sha256()
            with bundle.open(item['path']) as source:
                for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
            if digest.hexdigest()!=item['sha256']:raise ValueError('checksum_mismatch')
        destination.mkdir(parents=True,exist_ok=False)
        for name,state in manifest['roots'].items():
            if state['exists']:(destination/name).mkdir()
        for item in entries:
            target=destination.joinpath(*PurePosixPath(item['path']).parts)
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as output,bundle.open(item['path']) as source:shutil.copyfileobj(source,output)
    return manifest
