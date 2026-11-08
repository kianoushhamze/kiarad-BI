/* Real browser forms, routed exclusively to the synthetic QA API. */
const {chromium}=require('D:/project/.kiarad-browser-check/node_modules/playwright-core');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const session=JSON.parse(fs.readFileSync(path.join(root,'private_exports/assistant-qa-session.json'),'utf8'));
if(session.database!=='kiarad_assistant_qa_20261103')throw Error('Not QA');
const out=path.join(root,'audit-2026-11-03');fs.mkdirSync(out,{recursive:true});
const results=[],apiErrors=[],jsErrors=[];
const stamp=Date.now().toString(36);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.addInitScript(({token,user})=>{localStorage.setItem('kiarad_access_token',token);localStorage.setItem('kiarad_session_user',JSON.stringify(user));},session);
 await context.route('http://127.0.0.1:3000/api/**',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname.startsWith('/api/kiarad-assistant')){await route.abort();return;}
  const response=await route.fetch({url:'http://127.0.0.1:8001'+url.pathname.slice(4)+url.search});
  if(response.status()>=400)apiErrors.push({path:url.pathname,status:response.status()});
  await route.fulfill({response});
 });
 const page=await context.newPage();page.on('pageerror',error=>jsErrors.push(error.message));
 async function test(name,fn){try{await fn();results.push({name,passed:true});}catch(error){results.push({name,passed:false,error:error.message.slice(0,450)});await page.screenshot({path:path.join(out,'qa-'+name+'.png'),fullPage:true}).catch(()=>{});}}
 const api=async(p,options={})=>{const r=await context.request.fetch('http://127.0.0.1:8001'+p,{...options,headers:{Authorization:'Bearer '+session.token,...options.headers}});if(!r.ok())throw Error(p+': '+r.status());return r.json();};
 async function open(p){await page.goto('http://127.0.0.1:3000'+p);await page.waitForTimeout(500);}
 await test('manual-customer-create-edit',async()=>{
  await open('/data-entry');await page.locator('form select').nth(0).selectOption('customers');
  const fill=async(name)=>{await page.locator('fieldset').getByLabel(/کد مشتری/).fill('QA-UI-'+stamp);await page.locator('fieldset').getByLabel(/نام مشتری/).fill(name);await page.locator('fieldset').getByLabel(/سقف اعتبار/).fill('0');await page.getByRole('button',{name:'اعتبارسنجی و پیش‌نمایش'}).click();await page.getByRole('button',{name:'تأیید و ثبت همهٔ ردیف‌ها'}).waitFor();page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'تأیید و ثبت همهٔ ردیف‌ها'}).click();await page.getByText(/ردیف جدید و.*ردیف ویرایش‌شده ثبت شد/).waitFor();};
  await fill('مشتری فرم تست '+stamp);
  await fill('مشتری فرم اصلاح‌شده '+stamp);
  const rows=await api('/directory/customers?q='+encodeURIComponent('QA-UI-'+stamp));
  if(rows.length!==1||!rows[0].name.includes('اصلاح'))throw Error('customer upsert mismatch');
  await page.screenshot({path:path.join(out,'qa-manual-customer.png'),fullPage:true});
 });
 await test('manual-treasury-create-edit',async()=>{
  await open('/treasury');await page.getByRole('button',{name:'حساب بانکی/نقدی',exact:true}).click();
  await page.getByPlaceholder('نام حساب یا بانک').fill('حساب فرم تست '+stamp);
  await page.getByPlaceholder('موجودی فعلی (ریال)').fill('250000');
  await page.getByRole('button',{name:'ثبت و محاسبه مجدد',exact:true}).click();
  await page.getByText('حساب فرم تست '+stamp,{exact:true}).waitFor();
  const row=page.getByText('حساب فرم تست '+stamp,{exact:true}).locator('..').locator('..').locator('..');
  await row.getByRole('button',{name:'اصلاح موجودی'}).click();
  await page.locator('input[name=current_balance]').fill('275000');
  await page.getByRole('button',{name:'ثبت و محاسبه مجدد',exact:true}).click();
  await page.waitForTimeout(400);const overview=await api('/treasury/overview');
  const a=overview.accounts.find(x=>x.name==='حساب فرم تست '+stamp);if(!a||Number(a.current_balance)!==275000)throw Error('balance mismatch');
  await page.screenshot({path:path.join(out,'qa-manual-treasury.png'),fullPage:true});
 });
 await test('manual-crm-create',async()=>{
  await open('/crm');await page.getByPlaceholder('مثال: داروخانه رازی رفسنجان').fill('مشتری پیگیری تست '+stamp);
  await page.getByPlaceholder('بخشی از نام کالا یا متن دلخواه').fill('کالای آزمون دستیار');
  await page.locator('form textarea').fill('پیگیری کاملاً تستی برای بررسی ثبت از فرم');
  await page.locator('form button[type=submit]').click();await page.waitForTimeout(500);
  const rows=await api('/crm/interactions');if(!rows.some(r=>r.customer_name==='مشتری پیگیری تست '+stamp))throw Error('CRM not stored');
 });
 await test('manual-social-draft',async()=>{
  await open('/social');await page.locator('input[name=title]').fill('محتوای فرم تست '+stamp);await page.locator('textarea[name=body]').fill('متن آزمایشی برای بررسی فرم؛ منتشر نمی‌شود');
  await page.getByLabel('تاریخ و ساعت شمسی به وقت تهران',{exact:true}).fill('1405/08/25 10:00');
  await page.getByRole('button',{name:'ثبت برای بازبینی',exact:true}).click();await page.waitForTimeout(500);
  const data=await api('/integrations/content-calendar');if(!data.items.some(x=>x.title==='محتوای فرم تست '+stamp))throw Error('content not stored');
 });
 await test('manual-contract-draft',async()=>{
  await open('/compensation');await page.getByLabel('پرسنل',{exact:false}).first().selectOption(String(session.user.salesperson_id));
  await page.getByLabel('نوع حقوق',{exact:false}).selectOption('fixed');
  await page.getByRole('textbox',{name:/حقوق ثابت ماهانه/}).fill('15000000');
  await page.getByLabel('نحوهٔ پرداخت ثابت',{exact:false}).selectOption('full');
  await page.getByPlaceholder('تاریخ یا مرجع مصوبه و توضیح تصمیم مدیر').fill('قرارداد کاملاً تستی در محیط آزمون جدا');
  const saved=page.waitForResponse(r=>r.url().includes('/compensation/contract/')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'ذخیرهٔ پیش‌نویس',exact:true}).click();const response=await saved;
  if(!response.ok())throw Error('contract status '+response.status());
  const result=await response.json();if(Number(result.rules?.fixed_monthly_amount)!==150000000)throw Error('contract currency mismatch');
  await page.getByText('نسخهٔ پیش‌نویس ذخیره شد؛ هنوز مبنای فیش قطعی نیست.').waitFor();
  await page.screenshot({path:path.join(out,'qa-manual-contract.png'),fullPage:true});
 });
 await test('manual-target-create',async()=>{
  await open('/person-targets');await page.getByRole('button',{name:'+ تارگت جدید',exact:true}).click();
  const modal=page.locator('div.fixed.inset-0').last();await modal.getByLabel('عنوان',{exact:true}).fill('تارگت فرم تست '+stamp);
  await modal.getByLabel('مبلغ تارگت (ریال)',{exact:true}).fill('5000000');
  await modal.getByLabel('از تاریخ',{exact:true}).fill('1405/08/01');await modal.getByLabel('تا تاریخ',{exact:true}).fill('1405/08/30');
  const saved=page.waitForResponse(r=>r.url().endsWith('/targets/person-targets')&&r.request().method()==='POST');
  await modal.getByRole('button',{name:'ذخیره',exact:true}).click();if(!(await saved).ok())throw Error('target save failed');
  const data=await api('/targets/person-targets');if(!data.items.some(x=>x.title==='تارگت فرم تست '+stamp&&Number(x.target_amount)===5000000))throw Error('target not stored');
 });
 await test('manual-task-create',async()=>{
  await open('/tasks');await page.getByRole('button',{name:'ایجاد کار',exact:true}).click();
  await page.getByLabel('عنوان کار',{exact:true}).fill('وظیفه فرم تست '+stamp);
  const options=await page.getByLabel('پرسنل مسئول',{exact:true}).locator('option').all();if(options.length<2)throw Error('No test assignee');
  await page.getByLabel('پرسنل مسئول',{exact:true}).selectOption(await options[1].getAttribute('value'));
  const saved=page.waitForResponse(r=>r.url().endsWith('/tasks')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'ثبت و تخصیص',exact:true}).click();if(!(await saved).ok())throw Error('task save failed');
  const data=await api('/tasks');if(!data.tasks.some(x=>x.title==='وظیفه فرم تست '+stamp))throw Error('task not stored');
 });
 await test('manual-campaign-create',async()=>{
  await open('/campaigns');await page.getByPlaceholder('مثال: مهرماه سوآلین ویرا').fill('کمپین فرم تست '+stamp);
  const form=page.locator('form').first();await form.locator('input[type=number]').nth(0).fill('5000000');
  await page.getByLabel('تاریخ شروع شمسی کمپین',{exact:true}).fill('1405/08/01');await page.getByLabel('تاریخ پایان شمسی کمپین',{exact:true}).fill('1405/08/30');
  const saved=page.waitForResponse(r=>r.url().endsWith('/campaigns')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'🎯 ساخت کمپین در دیتابیس',exact:true}).click();if(!(await saved).ok())throw Error('campaign save failed');
  const data=await api('/campaigns');if(!data.some(x=>x.title==='کمپین فرم تست '+stamp))throw Error('campaign not stored');
 });
 await test('assistant-confirmation-and-replay',async()=>{
  const proposal=JSON.parse(fs.readFileSync(path.join(root,'private_exports/assistant-ui-confirmation.json'),'utf8'));
  let tasks=await api('/tasks');if(tasks.tasks.some(x=>x.title===proposal.title))throw Error('Task created before confirmation');
  await open('/assistant-actions?id='+proposal.id);
  const button=page.getByRole('button',{name:'تأیید و اعمال',exact:true});
  if(!await button.isDisabled())throw Error('Confirmation must require review checkbox');
  await page.getByRole('checkbox').check();await button.click();
  await page.getByText('عملیات ثبت شد. نتیجه را در بخش مربوط مشاهده کنید.').waitFor();
  tasks=await api('/tasks');if(tasks.tasks.filter(x=>x.title===proposal.title).length!==1)throw Error('Task not applied exactly once');
  await open('/assistant-actions?id='+proposal.id);if(await button.count())throw Error('Applied proposal can be confirmed again in UI');
  const replay=await api('/assistant/actions/'+proposal.id+'/confirm',{method:'POST',data:{confirm:true}});
  if(!replay.reused)throw Error('Replay protection failed');
  tasks=await api('/tasks');if(tasks.tasks.filter(x=>x.title===proposal.title).length!==1)throw Error('Duplicate task');
 });
 for(const route of ['/management','/customers','/catalog','/person-targets','/personnel','/compensation','/payroll','/map','/daily-reports','/tasks','/proformas','/campaigns','/online-sales','/assistant']){
  await test('page-'+route.slice(1),async()=>{const before=jsErrors.length;await open(route);if(page.url().includes('/login'))throw Error('unexpected login redirect');if(jsErrors.length>before)throw Error(jsErrors.at(-1));});
 }
 const report={database:session.database,production_data_changed:false,results,apiErrors,jsErrors};
 fs.writeFileSync(path.join(out,'manual-browser-qa.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify({cases:results.length,passed:results.filter(x=>x.passed).length,failures:results.filter(x=>!x.passed),apiErrors,jsErrors}));
 await browser.close();process.exitCode=results.some(x=>!x.passed)||jsErrors.length||apiErrors.length?1:0;
})().catch(e=>{console.error(e.message);process.exitCode=1;});
