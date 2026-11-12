function origin(value,development=false){
 const u=new URL(value.trim());
 if(u.username||u.password||u.search||u.hash||u.pathname!=='/')throw new Error('فقط نشانی اصلی سرور را بدون مسیر یا رمز وارد کنید.');
 if(u.protocol!=='https:'&&!(development&&u.protocol==='http:'&&['localhost','127.0.0.1','10.0.2.2'].includes(u.hostname)))throw new Error('نشانی سرور باید HTTPS معتبر باشد.');
 return u.origin;
}
function withinShift(timestamp,shift){return shift.collecting&&Number.isFinite(timestamp)&&timestamp>=Date.parse(shift.started_at)-5000&&timestamp<=Date.parse(shift.expires_at)&&timestamp<=Date.now()+90000;}
module.exports={origin,withinShift};
