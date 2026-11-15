"""Archive the two protected CI versions before reclaiming Actions storage."""
import hashlib,json,subprocess,zipfile,os
from pathlib import Path

ROOT=Path(os.environ['RUNNER_TEMP'])/'kiarad-artifact-archive'
ROOT.mkdir(exist_ok=True)
REPO='kianoushhamze/kiarad-BI'
plan=json.loads(Path('.github/archive-ci-plan.json').read_text())
records=[]

def api(path,method='GET',body=None):
    args=['gh','api','-X',method,'repos/'+REPO+'/'+path]
    if body is not None:args+=['--input','-']
    p=subprocess.run(args,input=json.dumps(body) if body is not None else None,capture_output=True,text=True)
    if p.returncode:raise RuntimeError(p.stderr[:500])
    return json.loads(p.stdout) if p.stdout.strip() else None

for sha in sorted({a['workflow_run']['head_sha'] for a in plan['keep']}):
    tag='archive-ci-'+sha[:7]+'-20261115'
    found=[r for r in api('releases?per_page=100') if r['tag_name']==tag]
    if found:
        release=found[0]
        assert release['draft'] and release['target_commitish']==sha
    else:
        release=api('releases','POST',{'tag_name':tag,'target_commitish':sha,'name':'Archived CI packages '+sha[:7],
            'draft':True,'prerelease':True,'make_latest':'false',
            'body':'Private archive of existing CI artifacts for source '+sha+'. Preserves the installed/reference package while reclaiming Actions storage. These are historical packages, not a new company deployment. Original artifact IDs and SHA256 checksums are in the attached manifest.'})
    print(json.dumps({'stage':'archive_release_ready','tag':tag,'id':release['id']}),flush=True)
    assets=api(f"releases/{release['id']}/assets?per_page=100")
    for artifact in sorted((a for a in plan['keep'] if a['workflow_run']['head_sha']==sha),key=lambda a:a['size_in_bytes']):
        name=artifact['name']+'-'+sha[:7]+'.zip'
        existing=next((a for a in assets if a['name']==name),None)
        expected=artifact['digest'].removeprefix('sha256:')
        path=ROOT/name
        if existing is None:
            print(json.dumps({'stage':'download','artifact_id':artifact['id'],'bytes':artifact['size_in_bytes']}),flush=True)
            with path.open('wb') as stream:
                r=subprocess.run(['gh','api',f"repos/{REPO}/actions/artifacts/{artifact['id']}/zip"],stdout=stream,stderr=subprocess.PIPE)
            if r.returncode:raise RuntimeError(r.stderr.decode()[:400])
            with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            assert digest==expected and path.stat().st_size==artifact['size_in_bytes']
            with zipfile.ZipFile(path) as archive:
                assert archive.testzip() is None
                if 'Transfer' in artifact['name']:
                    version=json.loads(archive.read('release.json'))
                    assert version['source_commit']==sha and not version['includes_company_data']
            print(json.dumps({'stage':'upload','name':name,'sha256':expected}),flush=True)
            r=subprocess.run(['gh','release','upload',tag,str(path),'-R',REPO],capture_output=True,text=True)
            if r.returncode:raise RuntimeError(r.stderr[:500])
            assets=api(f"releases/{release['id']}/assets?per_page=100")
            existing=next(a for a in assets if a['name']==name)
        assert existing['size']==artifact['size_in_bytes'] and existing['state']=='uploaded'
        if existing.get('digest'):
            assert existing['digest']=='sha256:'+expected
        else:
            r=subprocess.Popen(['gh','api',f"repos/{REPO}/releases/assets/{existing['id']}",'-H','Accept: application/octet-stream'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            actual=hashlib.file_digest(r.stdout,'sha256').hexdigest()
            assert r.wait()==0 and actual==expected
        row={'original_artifact_id':artifact['id'],'source_commit':sha,'name':name,'bytes':artifact['size_in_bytes'],
             'sha256':expected,'release_id':release['id'],'release_tag':tag,'asset_id':existing['id'],'verified':True}
        records.append(row)
        (ROOT/'release-archive-records.json').write_text(json.dumps(records,indent=2))
        if path.exists():path.unlink()
        print(json.dumps({'stage':'verified','artifact_id':artifact['id'],'asset_id':existing['id']}),flush=True)
    manifest=ROOT/('manifest-'+sha[:7]+'.json')
    manifest.write_text(json.dumps([r for r in records if r['source_commit']==sha],indent=2)+'\n')
    if not any(a['name']==manifest.name for a in assets):
        subprocess.run(['gh','release','upload',tag,str(manifest),'-R',REPO],check=True)

assert {r['original_artifact_id'] for r in records}=={a['id'] for a in plan['keep']}
# Reclaim Actions storage only after ALL protected archives have verified copies.
for row in records:
    assert row['verified']
    api('actions/artifacts/'+str(row['original_artifact_id']),'DELETE')
    print(json.dumps({'stage':'actions_copy_deleted','artifact_id':row['original_artifact_id']}),flush=True)
print(json.dumps({'complete':True,'verified_assets':len(records),'original_actions_artifacts_deleted':True}),flush=True)

