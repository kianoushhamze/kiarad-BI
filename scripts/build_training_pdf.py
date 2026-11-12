"""Render the versioned Persian handbook with embedded local fonts."""
import argparse
import base64
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
import shutil
from threading import Thread
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class Quiet(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass

def build(output):
 output.mkdir(parents=True,exist_ok=True)
 server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT)))
 thread=Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox','--disable-dev-shm-usage'])
   page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}/docs/training/manual-fa.html',wait_until='networkidle');page.evaluate('document.fonts.ready')
   if page.locator('section').count()!=35:raise RuntimeError('Handbook chapter inventory changed unexpectedly')
   if not page.evaluate('document.fonts.check("13px Vazir")'):raise RuntimeError('Persian font failed to load')
   page.pdf(path=str(output/'Kiarad-Comprehensive-Manual-FA.pdf'),format='A4',print_background=True,display_header_footer=True,header_template='<span></span>',footer_template='<div style="width:100%;font-size:9px;text-align:center;color:#78688a">Kiarad · 2026-11-13 &nbsp; | &nbsp; <span class="pageNumber"></span> / <span class="totalPages"></span></div>',prefer_css_page_size=True)
   browser.close()
  html=(ROOT/'docs/training/manual-fa.html').read_text()
  for name in ['Vazirmatn-Regular.ttf','Vazirmatn-Bold.ttf']:
   html=html.replace('../../site-healer/fonts/'+name,'data:font/ttf;base64,'+base64.b64encode((ROOT/'site-healer/fonts'/name).read_bytes()).decode())
  (output/'manual-fa.html').write_text(html)
 finally:server.shutdown();server.server_close()
 print(output/'Kiarad-Comprehensive-Manual-FA.pdf')
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);build(parser.parse_args().output)
