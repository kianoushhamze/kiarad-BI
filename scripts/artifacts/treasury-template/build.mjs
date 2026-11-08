import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';
const output = 'D:/project/kiaradbi/templates';
const previews = 'D:/project/kiaradbi/audit-2026-10-19/template-previews';
await fs.mkdir(output, {recursive:true});
await fs.mkdir(previews, {recursive:true});
const workbook = Workbook.create();
const invoice=['شماره فاکتور','تاریخ','شناسه کالا','تعداد','قیمت واحد','تخفیف ردیف','درصد تخفیف ردیف','تخفیف کل فاکتور','مالیات و عوارض فاکتور'];
const layouts=[
 ['حساب و موجودی',['کد حساب','نام حساب','نوع حساب','مانده','تاریخ']],
 ['چک‌ها',['شماره مرجع','طرف حساب','نوع چک','مبلغ','سررسید','وضعیت','احتمال وصول']],
 ['خرید',invoice],['فروش',invoice],['برگشت خرید',invoice],['برگشت فروش',invoice],
 ['گزارش ماهانه',['ماه','نوع گزارش','فروش ناخالص','برگشت فروش','تخفیف فروش','بهای کالای فروش رفته','هزینه متغیر','هزینه ثابت','هزینه مالی','مالیات','سایر درآمد']],
 ['موجودی کالا',['شناسه کالا','تعداد','ارزش موجودی','تاریخ']],
 ['گزارش عمومی',['عنوان ستون اول','عنوان ستون دوم']],
];
for (const [name,headers] of layouts) {
 const sheet=workbook.worksheets.add(name); sheet.showGridLines=false;sheet.tabColor='#166E79';
 sheet.getRangeByIndexes(0,0,1,headers.length).values=[headers];
 sheet.getRangeByIndexes(0,0,1,headers.length).format={fill:'#123849',font:{name:'Tahoma',size:11,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:56,verticalAlignment:'center'};
 sheet.getRangeByIndexes(1,0,30,headers.length).format={fill:'#F0F8FA',font:{name:'Tahoma',size:11,color:'#1B5B97'},rowHeight:26};
 sheet.getRangeByIndexes(0,0,31,headers.length).format.columnWidth=25;
 // Identifier and date entry cells remain text: leading zeroes and Jalali dates survive.
 sheet.getRangeByIndexes(1,0,30,headers.length).setNumberFormat('@');
 sheet.freezePanes.freezeRows(1);
}
const guide=workbook.worksheets.add('راهنما');guide.showGridLines=false;
const notes=[
 ['قالب ورود گزارش مالی کیاراد','راهنمای تکمیل؛ ردیف نمونهٔ ساختگی ندارد'],
 ['ساختار','هر شیت یک گزارش است؛ سرستون سطر اول را نگه دارید و دیتا را از سطر دوم وارد کنید.'],
 ['واحد پول','در داشبورد واحد ریال یا تومان را برای کل شیت صریح انتخاب کنید؛ ترکیب واحدها مجاز نیست.'],
 ['تاریخ','به‌صورت متن مانند ۱۴۰۵/۰۷/۲۷ وارد کنید؛ ماه گزارش مانند ۱۴۰۵/۰۷ است.'],
 ['حساب و موجودی','نوع حساب: بانک یا صندوق؛ کد حساب یکتا؛ تاریخ همه مانده‌ها یکسان باشد.'],
 ['چک‌ها','نوع: دریافتنی یا پرداختنی؛ وضعیت: باز، سررسید گذشته، برگشتی، تسویه، وصول یا لغو؛ احتمال وصول از صفر تا صد.'],
 ['چک خرج‌شده','به‌عنوان چک باز دوباره وارد نکنید؛ انتقال نامشخص را در گزارش عمومی برای تطبیق نگه دارید.'],
 ['فاکتور و افر','هر ردیف، یک قلم فاکتور است. هدیه تعداد مثبت و قیمت صفر دارد. شناسه کالا در همه گزارش‌ها یکسان باشد.'],
 ['تخفیف','تخفیف کل شامل تخفیف ردیف است؛ سربرگ تخفیف و مالیات در همه ردیف‌های یک فاکتور یکسان تکرار شود.'],
 ['بازه فاکتور','ابتدا و انتهای بازه را در داشبورد مشخص کنید. فایل بدون رکورد می‌تواند با سرستون تنها نبود برگشت در بازه را اعلام کند.'],
 ['گزارش ماهانه','نوع: عملکرد یا بودجه؛ همه سرفصل‌های مبلغی الزامی هستند؛ مقدار نامعلوم را صفر نکنید. عملکرد واردشده پیش‌نویس است.'],
 ['موجودی کالا','ارزش، جمع بهای موجودی همان کالا در تاریخ گزارش است. این فایل تا تطبیق تاریخ و نگاشت، بهای فروش گذشته محسوب نمی‌شود.'],
 ['گزارش عمومی','نام ستون‌ها قابل تغییر است؛ فقط برای نگهداری و مشاهده، بدون ورود خودکار به حسابداری.'],
 ['ثبت','فایل ابتدا پیش‌نمایش می‌شود؛ پس از بررسی، تأیید ثبت را بزنید. گزارش هلو بازنویسی نمی‌شود.'],
 ['فرمول و ماکرو','قبل از بارگذاری، مقادیر محاسبه‌شده را بدون فرمول ذخیره کنید. فایل دارای فرمول، ماکرو یا پیوند خارجی رد می‌شود.'],
 ['محدودیت','حداکثر پنج مگابایت، ده هزار ردیف و شصت ستون در هر شیت.'],
 ['منبع قالب','قرارداد داخلی ورود اکسل خزانه؛ این فایل حاوی دیتای واقعی شرکت نیست.'],
];
guide.getRange('A1:B17').values=notes;
guide.getRange('A1:B17').format={font:{name:'Tahoma',size:11,color:'#183B4E'},wrapText:true,verticalAlignment:'center',rowHeight:46};
guide.getRange('A1:B1').format={fill:'#123849',font:{name:'Tahoma',size:13,bold:true,color:'#FFFFFF'},rowHeight:54};
guide.getRange('A1:A17').format.columnWidth=24;guide.getRange('B1:B17').format.columnWidth=94;
workbook.recalculate();
const scan=await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!',options:{useRegex:true,maxResults:20},summary:'Template error scan'});
await fs.writeFile(path.join(previews,'checks.ndjson'),scan.ndjson);
for(let i=0;i<layouts.length;i++) {
 const [name,headers]=layouts[i]; const end=String.fromCharCode(64+headers.length);
 const blob=await workbook.render({sheetName:name,range:`A1:${end}4`,scale:1.4});
 await fs.writeFile(path.join(previews,`sheet-${i}.png`),new Uint8Array(await blob.arrayBuffer()));
}
const g=await workbook.render({sheetName:'راهنما',range:'A1:B17',scale:1.2});
await fs.writeFile(path.join(previews,'guide.png'),new Uint8Array(await g.arrayBuffer()));
const file=await SpreadsheetFile.exportXlsx(workbook);await file.save(path.join(output,'treasury-import.xlsx'));
console.log(JSON.stringify({output:path.join(output,'treasury-import.xlsx'),sheets:layouts.length+1,has_synthetic_financial_data:false}));
