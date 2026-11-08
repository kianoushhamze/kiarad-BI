"""Source-backed catalog conversation. No model-generated facts or financial writes."""
import re
from decimal import Decimal


def normalize(value):
    return re.sub(r"\s+", " ", str(value or "").translate(str.maketrans("يك", "یک")).replace("\u200c", " ")).strip().lower()


# Search aliases only: an alias is enabled only when that literal catalog prefix exists.
# These do not assert supplier identity or product attributes.
ALIASES = {
    "lufente": ("لوفنته", "لوفتنه", "لوفنت"), "dermalist": ("درمالیست",),
    "laboren": ("لابورن", "لابورین"), "lucel": ("لوسل", "لوسل"),
    "delano": ("دلانو",), "milito": ("میلیتو",), "pleasant": ("پلیزنت", "پلزنت"),
    "richmond": ("ریچموند",), "total derm": ("توتال درم", "توتالدرم"),
    "elvatan": ("الواتن", "الواتان"), "achiote": ("آچیوته", "اچیوته"),
    "paradox": ("پارادوکس",), "cyno care": ("ساینوکر", "ساینو کر"),
    "old stop": ("اولداستاپ", "اولد استاپ"), "solamor": ("سولامور",),
    "vinur": ("وینور",), "rinkon": ("رینکون",), "cip": ("سی آی پی", "سی ای پی"),
    "mc": ("ام سی", "ام‌سی"), "hlm": ("اچ ال ام",), "v&v": ("وی اند وی",),
}
DISPLAY = {key:values[0] for key,values in ALIASES.items()}
STOP = set("با توجه به موجودی انبار انبارمون و کاردکس محصولات محصول کالا کالاها برند از چی چه سفارش بدم خرید پیشنهاد بده بهم فروشش فروش رو را براساس بر اساس کن میخوام برای لطفا لیست قیمت چقدر است هست داریم بگو من همون همان این اون برنده برندش موجودی‌مون".split())
STOP.update("وضعیت چطور چطوره چقدره لطفاً بدهید بررسی تحلیل کلی همه پرفروش پرفروشترین ترین کدوم چهارتا باید بخرم پیشنهادت درباره کاردکسش فروششون مون کنیم مقایسه انبارمان موجودیمون موجودیها".split())
STOP.update('روز روزه اخیر گذشته جاری ماه هفته بازه مدت هفتگی ماهانه سالانه سال امروز دیروز گردش همین اینها اینا'.split())
STOP.update('نشون نمایش نشان میدی میده میدن میتونی میتوانی لطفاً لطفا اطلاعات بیار بفرست پیدا پیداش جستجو جست‌وجو بگرد چندتا تعداد مقدارش موجوده داری دارید بفرمایید'.split())


def catalog_intent(question):
    q = normalize(question)
    # Mentioning a brand inside a payroll/target/finance/action request must not
    # hijack that request and replace it with a stock report.
    if any(word in q for word in ('تارگت','هدف','حقوق','پورسانت','قرارداد','فیش','وظیفه','تسک','ثبت کن','کمپین','تسویه','وصول','خزانه','چک','سود','تولیدکننده','تولید کننده','تأمین کننده','تامین کننده','ساخت کجا')):
        return False
    return any(word in q for word in ("برند", "موجودی", "انبار", "کاردکس", "کالا", "محصول", "سفارش", "قیمت"))


def question_window(question, today):
    q=normalize(question).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789'))
    match=re.search(r'(\d{1,3})\s*روز',q)
    if match:
        return max(1,min(365,int(match[1])))
    if 'ماه جاری' in q or 'این ماه' in q:
        from iran_time import iran_month_bounds
        return (today-iran_month_bounds(today)[0]).days+1
    return 90


def limit_short_window_orders(analysis, days):
    if days<30:
        analysis.setdefault('warnings',[]).append('بازهٔ کوتاه‌تر از ۳۰ روز برای تعیین مقدار خرید کافی نیست.')
        for row in analysis.get('items',[]):
            row['order']={'status':'data_required','suggested_quantity':None}
    return analysis


def catalog_groups(rows):
    groups = {}
    for row in rows:
        # Prefix is taken from the source, not from a language model's brand knowledge.
        match = re.match(r"^([A-Za-z][A-Za-z&]*(?: +[A-Z][A-Z&]+)*)", str(row.get("name") or ""))
        if match:
            key = normalize(match[1])
            groups.setdefault(key, []).append(row)
    return groups


def resolve_selection(question, rows, previous_questions=()):
    """Catalog keywords and explicit aliases. Ambiguity never picks a SKU arbitrarily."""
    groups = catalog_groups(rows)
    code_match = re.search(r'کد\s*[:：]?\s*([\w-]+)', normalize(question))
    if code_match:
        found = [row for row in rows if normalize(row.get('code')) == code_match[1]]
        return {'status':'matched','label':code_match[1],'match_basis':'exact_product_code','items':found} if found else {'status':'not_found','label':code_match[1]}

    def find(q):
        q = normalize(q)
        hits = []
        for key in groups:
            terms = (key,) + ALIASES.get(key, ())
            if any(re.search(r"(?<!\w)" + re.escape(normalize(term)) + r"(?!\w)", q) for term in terms):
                hits.append(key)
        return hits

    def group_selection(q,key,basis):
        remaining=normalize(q)
        for term in sorted((key,)+ALIASES.get(key,()),key=len,reverse=True):
            remaining=remaining.replace(normalize(term),' ')
        terms=[w for w in re.findall(r'[\w&]+',remaining) if len(w)>=3 and w not in STOP]
        # Keep product descriptors that actually occur in the catalog, so e.g.
        # "کرم درمالیست" selects creams rather than every SKU of the brand.
        descriptors=[w for w in terms if any(w in normalize(r.get('name')) for r in rows)]
        selected=[r for r in groups[key] if all(w in normalize(r.get('name')) for w in descriptors)]
        if not selected:
            return {'status':'not_found','label':normalize(q)}
        label=DISPLAY.get(key,key)+('؛ '+' / '.join(descriptors) if descriptors else '')
        return {'status':'matched','label':label,'match_basis':basis,'items':selected}

    hits = find(question)
    if len(hits) > 1:
        return {"status": "ambiguous", "candidates": [DISPLAY.get(k, k) for k in hits]}
    if hits:
        key = hits[0]
        return group_selection(question,key,'catalog_name_prefix')

    words = [w for w in re.findall(r"[\w&]+", normalize(question)) if len(w) >= 3 and w not in STOP]
    # An explicit unknown brand must not inherit the old brand.
    explicit = re.search(r"برند\s+([^\s؟?،]+)", normalize(question))
    if explicit and explicit[1] not in {"همون", "همان", "این", "اون"}:
        term = explicit[1]
        matches = [r for r in rows if term in normalize(r.get("name")) or term == normalize(r.get("code"))]
        if matches:
            return {"status": "matched", "label": term, "match_basis": "catalog_text", "items": matches}
        # A close spelling is a clarification candidate, never a silently accepted identity.
        from difflib import SequenceMatcher
        candidates = []
        for key in groups:
            score = max(SequenceMatcher(None,term,normalize(x)).ratio() for x in (key,) + ALIASES.get(key,()))
            if len(term)>=4 and score>=0.65:
                candidates.append((score,DISPLAY.get(key,key)))
        candidates.sort(reverse=True)
        return {"status": "not_found", "label": term, "candidates": [v for _,v in candidates[:4]]}
    if words:
        matches = [r for r in rows if all(w in normalize(r.get("name")) or w == normalize(r.get("code")) for w in words)]
        if matches:
            return {"status": "matched", "label": " / ".join(words), "match_basis": "catalog_text", "items": matches}
        # Do not answer a specific unknown product using a previous unrelated brand.
        known = [w for w in words if any(w in normalize(r.get('name')) for r in rows)]
        candidates = [str(r.get('name')) for r in rows if known and all(w in normalize(r.get('name')) for w in known)]
        return {"status": "not_found", "label": " / ".join(words), "candidates": candidates[:6]}

    # Only user-authored adjacent catalog questions can provide follow-up identity.
    # Assistant prose (including old hallucinations) is never evidence.
    followup = any(w in normalize(question) for w in ('همون','همان','کاردکس','فروشش','محصولاتش','این برند','اون برند'))
    for old in reversed(list(previous_questions)[-6:]) if followup else ():
        if not catalog_intent(old):
            break
        old_hits = find(old)
        if len(old_hits) == 1:
            key = old_hits[0]
            return group_selection(old,key,'previous_user_catalog_name')
        if len(old_hits) > 1 or "برند" in normalize(old):
            break
    return {"status": "needs_selection"}


def number(value, decimals=1):
    if value is None:
        return "نامعلوم"
    value = Decimal(str(value))
    out = f"{value:,.{decimals}f}".rstrip("0").rstrip(".") if decimals else f"{value:,.0f}"
    return out.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def toman(irr):
    return "نامعلوم" if irr is None else number(Decimal(str(irr)) / 10) + " تومان"


def business_date(value):
    if not value:
        return 'نامعلوم'
    from datetime import date, datetime
    from iran_time import IRAN_TIMEZONE
    import jdatetime
    if isinstance(value,str):
        value = datetime.fromisoformat(value.replace('Z','+00:00')) if 'T' in value or ' ' in value else date.fromisoformat(value)
    if isinstance(value,datetime):
        if value.tzinfo:
            value=value.astimezone(IRAN_TIMEZONE)
        rendered=jdatetime.datetime.fromgregorian(datetime=value).strftime('%Y/%m/%d ساعت %H:%M')
    else:
        rendered=jdatetime.date.fromgregorian(date=value).strftime('%Y/%m/%d')
    return rendered.translate(str.maketrans('0123456789','۰۱۲۳۴۵۶۷۸۹'))


def dates_for_model(value):
    """Compute display dates and currency conversions before asking the model."""
    from datetime import date, datetime
    if isinstance(value,dict):
        result={}
        for key,item in value.items():
            result[key]=dates_for_model(item)
            if key.endswith('_irr'):
                if item is None:
                    result[key+'_toman_display']='نامعلوم؛ دادهٔ مبلغ موجود نیست'
                elif not isinstance(item,bool):
                    try:
                        amount=Decimal(str(item))/Decimal(10)
                        if amount.is_finite():
                            rendered=format(amount,',f')
                            if '.' in rendered:rendered=rendered.rstrip('0').rstrip('.')
                            result[key+'_toman_display']=rendered.translate(str.maketrans('0123456789','۰۱۲۳۴۵۶۷۸۹'))+' تومان'
                    except (ValueError,TypeError,ArithmeticError):
                        pass
            if isinstance(item,(date,datetime)) or (isinstance(item,str) and re.match(r'^20\d{2}-\d{2}-\d{2}(?:$|T| )',item)):
                try:
                    result[key+'_display']=business_date(item)
                except (ValueError,TypeError):
                    pass
        return result
    if isinstance(value,list):
        return [dates_for_model(v) for v in value]
    return value


def inventory_answer(selection, analysis, role):
    label = selection["label"]
    codes = {str(r.get("holoo_erp_code")) for r in selection["items"] if r.get("holoo_erp_code")}
    items = [r for r in analysis.get("items", []) if str(r["erp_code"]) in codes]
    fresh = bool(analysis.get("source_fresh"))
    complete = analysis.get("status") == "observed"
    header = [f"تحلیل {label}؛ تطبیق با نام واقعی کالاهای هلو.",
              f"بازهٔ بررسی: {business_date(analysis.get('from_date'))} تا {business_date(analysis.get('to_date'))}؛ {number(analysis.get('covered_days'), 0)} روز.",
              f"زمان دریافت منبع به وقت تهران: {business_date(analysis.get('captured_at'))}؛ شناسهٔ نسخه: {analysis.get('snapshot_id') or 'نامعلوم'}."]
    if not fresh or not complete:
        header.append("هشدار: منبع کهنه یا ناقص است؛ اعداد زیر فقط سابقهٔ موجودند و پیشنهاد مقدار خرید معتبر نیست.")
    if analysis.get('requested_days',90)<30:
        header.append('این بازه برای گزارش گردش قابل استفاده است، اما برای تعیین مقدار خرید کوتاه است؛ پیشنهاد مقدار سفارش مسدود است.')
    if analysis.get('covered_days',0)<analysis.get('requested_days',90):
        header.append('منبع تمام بازهٔ درخواستی را پوشش نمی‌دهد؛ نتیجه فقط مربوط به تاریخ‌های نمایش‌داده‌شده است و مقدار سفارش تأیید نمی‌شود.')
    if not items or len(items) != len(selection["items"]):
        header.append("نگاشت همهٔ کالاهای انتخاب‌شده با نسخهٔ هلو کامل نیست؛ تحلیل و سفارش تا تطبیق شناسه‌ها متوقف است.")
        return {"answer": "\n".join(header), "mode": "inventory_data_required", "items": [], "source_fresh": fresh, "automatic_purchase": False}

    def priority(row):
        if not row.get("active") or not fresh or not complete:
            return 3
        if (row.get("outbound_quantity") or 0) > 0:
            return 0 if (row.get("stock") is not None and row["stock"] <= 0) else 1
        return 2

    items.sort(key=lambda r: (priority(r), r.get("stock_cover_days") if r.get("stock_cover_days") is not None else float("inf"), -(r.get("outbound_quantity") or 0), r["erp_code"]))
    header.append(f"{number(len(items), 0)} قلم منطبق؛ اولویت‌بندی بر مبنای خروج مشاهده‌شده و پوشش موجودی است.")
    moving=[r for r in items if r.get('active') and (r.get('outbound_quantity') or 0)>0 and r.get('stock_cover_days') is not None]
    if fresh and complete and moving:
        def label_of(row):
            name=str(row['name'])
            for key,display in DISPLAY.items():
                name=re.sub(r'^'+re.escape(key),display+' ',name,flags=re.I)
            return name
        first=moving[0]
        summary='جمع‌بندی تصمیم: ابتدا تأمین «'+label_of(first)+'» را بررسی کن؛ پوشش موجودی آن '+number(first['stock_cover_days'])+' روز و کمترین مقدار بین اقلام دارای خروج است.'
        largest=max(moving,key=lambda r:r['stock_cover_days'])
        if largest['erp_code']!=first['erp_code']:
            summary+=' «'+label_of(largest)+'» با '+number(largest['stock_cover_days'])+' روز بیشترین پوشش را دارد؛ پیش از افزایش خرید، علت سطح موجودی و برنامهٔ فروشش را بررسی کن.'
        header.append(summary)
    for row in items[:20]:
        name = str(row["name"])
        for key, display in DISPLAY.items():
            name = re.sub(r"^" + re.escape(key), display + " ", name, flags=re.I)
        stock = row.get("stock")
        outgoing = row.get("outbound_quantity")
        cover = row.get("stock_cover_days")
        order = row.get("order", {})
        if not row.get("active"):
            verdict = "غیرفعال؛ خرید مسدود"
        elif not fresh or not complete:
            verdict = "منبع معتبر تازه لازم است"
        elif outgoing is None:
            verdict = "سابقهٔ خروج کافی نیست"
        elif outgoing <= 0:
            verdict = "بدون خروج در بازه؛ خرید مجدد فعلاً توجیه فروش ندارد"
        elif order.get("status") == "review_order":
            verdict = "پیشنهاد قابل بازبینی: " + number(order.get("suggested_quantity")) + " واحد؛ نیازمند تأیید مدیر"
        elif order.get("status") == "no_order":
            verdict = "طبق سیاست ثبت‌شده فعلاً خرید لازم نیست"
        else:
            verdict = ("ناموجود با خروج ثبت‌شده؛ بررسی تأمین در اولویت" if stock is not None and stock <= 0 else "تعیین مقدار خرید نیازمند سیاست تأمین معتبر")
        line = f"• {name} | کد {row.get('display_code') or row['erp_code']}\n  موجودی {number(stock)}؛ رزرو {number(row.get('reserved'))}؛ خروج {number(outgoing)}؛ برگشت {number(row.get('return_quantity'))}؛ افر خروجی {number(row.get('free_outbound_units'))} واحد."
        line += ' قیمت فروش جاری: '+toman(row.get('current_sell_price_irr'))+'.'
        line += f" پوشش موجودی: {number(cover)} روز."
        if role in {"ceo", "finance"}:
            line += " فروش خالص کالا: " + toman(row.get("net_sales_irr")) + "."
        trend = row.get("outbound_trend_percent")
        line += " روند خروج ۳۰ روز آخر نسبت به ۳۰ روز قبل: " + (number(trend) + " درصد" if trend is not None else "قابل محاسبه نیست") + "."
        line += "\n  نتیجه: " + verdict + "."
        header.append(line)
    if len(items) > 20:
        header.append(f"{number(len(items)-20, 0)} قلم دیگر در تحلیل انبار قابل مشاهده است.")
    header.append("خروج شامل افر است؛ برگشت جداست و قابل‌فروش‌بودنش فرض نشده. مبلغ فروش پس از تخفیف و برگشت و بدون مالیات است؛ مبلغ داخلی ریال و نمایش بالا تومان با تقسیم بر ۱۰ است.")
    if any(not r.get("policy") for r in items):
        header.append("برای مقدار سفارش، زمان تأمین، دورهٔ بازبینی، ذخیرهٔ اطمینان، حداقل خرید و مضرب بسته را در تحلیل انبار تعریف کنید؛ موجودی صفر به‌تنهایی دلیل خرید نیست.")
    header.append("اطلاعات کامل انقضا و تقاضای ازدست‌رفته در زمان ناموجودی تأیید نشده؛ این اولویت‌بندی تضمین فروش یا سود نیست. هیچ سفارش خریدی ثبت نشده است.")
    return {"answer": "\n\n".join(header), "mode": "verified_catalog_analysis", "items": items[:20], "matched_count": len(items),
            "snapshot_id": analysis.get("snapshot_id"), "source_fresh": fresh, "automatic_purchase": False,
            "action": {"label": "بررسی تحلیل و سیاست تأمین", "href": "/catalog"}}
