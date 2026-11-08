const {chromium}=require('D:/project/.kiarad-browser-check/node_modules/playwright-core');
const fs=require('node:fs'),path=require('node:path');const root=path.resolve(__dirname,'..');
const session=JSON.parse(fs.readFileSync(path.join(root,'private_exports/assistant-qa-session.json'),'utf8'));
if(session.database!=='kiarad_assistant_qa_20261103')throw Error('Not QA');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.addInitScript(s=>{localStorage.setItem('kiarad_access_token',s.token);localStorage.setItem('kiarad_session_user',JSON.stringify(s.user));},session);
 await context.route('http://127.0.0.1:3000/api/**',async r=>{const u=new URL(r.request().url());const response=await r.fetch({url:'http://127.0.0.1:8001'+u.pathname.slice(4)+u.search});await r.fulfill({response});});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:3000/monthly-plans');
  await page.getByLabel('پرسنل برنامه').selectOption(String(session.user.id));
  const parts=new Intl.DateTimeFormat('en-US-u-ca-persian',{year:'numeric',month:'2-digit',timeZone:'Asia/Tehran'}).formatToParts(new Date(Date.now()+180*86400000));
  const month=parts.find(p=>p.type==='year').value+'-'+parts.find(p=>p.type==='month').value;
  await page.getByLabel('ماه برنامه').fill(month);
  await page.getByRole('checkbox').uncheck();await page.getByPlaceholder('سال/ماه/روز شمسی').fill(month.replace('-','/')+'/10');
  const selection=page.getByLabel('پایگاه‌های برنامه');const options=await selection.locator('option').all();if(options.length<2)throw Error('test bases missing');
  await selection.selectOption([await options[0].getAttribute('value'),await options[1].getAttribute('value')]);
  await page.getByRole('button',{name:'افزودن روزها و پایگاه‌ها به پیش‌نویس',exact:true}).click();
  const response=page.waitForResponse(r=>r.url().endsWith('/monthly-visit-plans')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'ذخیرهٔ پیش‌نویس ماهانه',exact:true}).click();const res=await response;if(!res.ok())throw Error('draft '+res.status());
  await page.getByRole('button',{name:'ارسال برای تأیید مدیرعامل',exact:true}).click();
  await page.getByRole('textbox',{name:'نظر مدیرعامل'}).fill('بازبینی و تأیید برنامهٔ کاملاً تستی');
  const approval=page.waitForResponse(r=>r.url().includes('/monthly-visit-plans/')&&r.url().endsWith('/review'));
  await page.getByRole('button',{name:'تأیید و فعال‌سازی برنامه',exact:true}).click();if(!(await approval).ok())throw Error('approval failed');
  await page.getByText('برنامهٔ اجرایی مصوب',{exact:false}).first().waitFor();
  await page.screenshot({path:path.join(root,'audit-2026-11-03/monthly-plan-browser.png'),fullPage:true});
  if(errors.length)throw Error(errors.join(';'));
  fs.writeFileSync(path.join(root,'audit-2026-11-03/monthly-plan-browser.json'),JSON.stringify({passed:true,checks:['two_bases_one_day','draft','submit','ceo_review','publish'],production_data_changed:false}));
  console.log(JSON.stringify({passed:true,checks:5}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
