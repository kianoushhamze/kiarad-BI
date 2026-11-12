"""Attach same-run manuals/mobile builds and refresh every kit checksum."""
import argparse,hashlib,json,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--kit',type=Path,required=True);p.add_argument('--extras',type=Path,required=True);a=p.parse_args()
expected={'Kiarad-Training-Manual/Kiarad-Comprehensive-Manual-FA.pdf','Kiarad-Android-Pilot/app-release.apk','Kiarad-iOS-Simulator/Kiarad-iOS-Simulator.zip'}
for path in expected:
 if not (a.extras/path).is_file():raise RuntimeError('Missing release deliverable: '+path)
shutil.copytree(a.extras,a.kit/'deliverables')
release=json.loads((a.kit/'release.json').read_text());release.update({'includes_training_pdf':True,'includes_android_pilot_apk':True,'includes_ios_simulator':True,'includes_ios_device_ipa':False,'mobile_device_acceptance_complete':False})
(a.kit/'release.json').write_text(json.dumps(release,indent=2)+'\n')
checks=[]
for path in sorted(a.kit.rglob('*')):
 if path.is_file() and path.relative_to(a.kit).as_posix()!='checksums.json':
  with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest().upper()
  checks.append({'path':path.relative_to(a.kit).as_posix(),'bytes':path.stat().st_size,'sha256':sha})
(a.kit/'checksums.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps({'release':release,'checked_files':len(checks)}))
