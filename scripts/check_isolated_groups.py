"""Run the existing opt-in PostgreSQL groups with temporary search paths."""
import json,os,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
groups=re.findall(r'File = "([^"]+)"; Flag = "([^"]+)"',(ROOT/'scripts/run_full_test_suite.ps1').read_text(encoding='utf-8-sig'))
results=[]
for filename,flag in groups:
    env=os.environ.copy();env[flag]='1';env['PGOPTIONS']='-c search_path=pg_temp -c statement_timeout=30000 -c lock_timeout=5000'
    result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p',filename,'-q'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
    results.append({'file':filename,'passed':result.returncode==0,'output':result.stdout+result.stderr})
    print(json.dumps({'file':filename,'passed':result.returncode==0}),flush=True)
folder=ROOT/'audit-2026-11-03';folder.mkdir(exist_ok=True)
(folder/'isolated-groups.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(any(not r['passed'] for r in results))
