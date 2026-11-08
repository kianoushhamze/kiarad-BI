"""Copy real local attachments to a private archive and verify a separate restore."""
import json
from datetime import datetime,timezone
from pathlib import Path
import sys
import tempfile
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from file_recovery import create_bundle,restore_bundle,file_digest


def main():
    folder=ROOT/'private_exports'/'file-backups'/uuid4().hex
    folder.mkdir(parents=True)
    archive=folder/'uploads.zip'
    roots={'team_chat':ROOT/'private_uploads'/'team_chat','catalog_uploads':ROOT/'kiarad-dashboard'/'public'/'uploads'}
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'source_modified':False,'restored_over_live_files':False,'passed':False}
    try:
        manifest=create_bundle(roots,archive)
        with tempfile.TemporaryDirectory(prefix='file-restore-',dir=folder) as temporary:
            restored=Path(temporary)/'restored'
            restore_bundle(archive,restored)
            matches=all(file_digest(restored/item['path'])==item['sha256'] for item in manifest['files'])
            report.update(passed=matches,file_count=len(manifest['files']),file_bytes=sum(item['bytes'] for item in manifest['files']),
                          missing_source_roots=[key for key,value in manifest['roots'].items() if not value['exists']],
                          archive=str(archive.relative_to(ROOT)),archive_sha256=file_digest(archive),temporary_restore_removed=True)
    except Exception as error:report['error_type']=type(error).__name__
    output=ROOT/'audit-2026-10-27'/'file-recovery.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    return int(not report['passed'])


if __name__=='__main__':raise SystemExit(main())
