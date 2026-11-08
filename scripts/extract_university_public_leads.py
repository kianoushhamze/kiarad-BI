"""Run with the bundled PDF runtime. Never connects to the company database."""
import json
import sys
from datetime import datetime,timezone
from pathlib import Path
import pdfplumber
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from public_directory_extract import parse_university_tables

source=ROOT/'data/public-prospects/reference-candidates/kmu-night-pharmacies.pdf'
with pdfplumber.open(source) as document:
    tables=[]
    for page in document.pages:
        gray=[rect for rect in page.rects if rect.get('non_stroking_color')==0.788 and 30<rect['width']<160 and rect['height']>10]
        top=min(rect['top'] for rect in gray)
        candidates=[rect for rect in gray if abs(rect['top']-top)<2]
        headers=[rect for rect in candidates if not any(other['width']>rect['width']+1 and other['x0']<=rect['x0'] and other['x1']>=rect['x1'] for other in candidates)]
        headers.sort(key=lambda rect:rect['x0'])
        if len(headers)!=8:raise ValueError('unexpected_header_geometry')
        table=[]
        for offset in (0,4):
            name_header=headers[offset+2]
            name_cells=[rect for rect in page.rects if abs(rect['x0']-name_header['x0'])<1 and abs(rect['x1']-name_header['x1'])<1 and rect['top']>name_header['bottom'] and rect['bottom']<=page.height and rect['height']>5]
            for cell in sorted(name_cells,key=lambda rect:rect['top']):
                row=[None]*8;middle=(cell['top']+cell['bottom'])/2
                for column in range(offset,offset+4):
                    header=headers[column]
                    boxes=[rect for rect in page.rects if abs(rect['x0']-header['x0'])<1 and abs(rect['x1']-header['x1'])<1 and rect['top']<=middle<=rect['bottom']]
                    if len(boxes)!=1:raise ValueError('ambiguous_cell_geometry')
                    box=boxes[0]
                    row[column]=page.crop((box['x0'],box['top'],box['x1'],box['bottom'])).extract_text(x_tolerance=2) or ''
                table.append(row)
        tables.append(table)
items=parse_university_tables(tables,'https://pr.kmu.ac.ir/Images/Download/31467/1_1.pdf')
for item in items:
    item['issues']=[issue for issue in item['issues'] if issue!='source_date_unknown']+['historical_nowruz_1399_roster','current_activity_unconfirmed']
report={'observed_at':datetime.now(timezone.utc).isoformat(),'source_publication_date':None,'source_period':'نوروز ۱۳۹۹؛ از نوشتهٔ حاشیهٔ صفحهٔ دوم',
        'source_file':str(source.relative_to(ROOT)),'official_complete_register':False,
        'coverage':'فهرست دانشگاه از داروخانه‌های شبانه‌روزی و برخی داروخانه‌های کشیک تعطیلات؛ فهرست کل استان نیست.',
        'inserted_customers':0,'requires_review':True,'items':items}
target=ROOT/'data/public-prospects/university-unverified-2026-10-27.json'
target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'review_only_leads':len(items),'cities':len({item['city'] for item in items}),
                  'city_requires_review':sum('city_requires_review' in item['issues'] for item in items),
                  'inserted_customers':0,'file':str(target.relative_to(ROOT))}))
