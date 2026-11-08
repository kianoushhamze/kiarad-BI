"""Pure observed inventory intelligence and explicit-policy order scenarios."""
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
from holoo_finance import numeric
from purchase_profit import estimate_purchase_profit, _normalize_invoice, _day, EvidenceError


SEMANTICS = {"header_sum_price": "gross_before_discount_tax", "header_discount_scope": "includes_line_discounts"}


def valid(value, nonnegative=True):
    result=numeric(value)
    if nonnegative and result < 0:
        raise ValueError("negative")
    return result


def f(value):
    return float(value) if value is not None else None


def order_scenario(stock, reserved, daily_demand, policy):
    """No purchase is placed. Missing approved policy stays unknown."""
    blocked={"status":"policy_required","reorder_point":None,"target_stock":None,"suggested_quantity":None}
    if not policy:
        return blocked
    try:
        lead,review,safety,minimum,pack=[valid(policy[k]) for k in ('lead_days','review_days','safety_units','minimum_order','pack_units')]
        available=valid(stock)-valid(reserved)
        demand=valid(daily_demand)
        if pack<=0 or review<=0 or lead>365 or review>365 or policy.get('units_confirmed') is not True:
            return blocked
        point=demand*lead+safety
        target=demand*(lead+review)+safety
        needed=max(Decimal(0),target-available)
        quantity=((max(needed,minimum)/pack).to_integral_value(rounding=ROUND_CEILING)*pack) if needed>0 and available<=point and demand>0 else Decimal(0)
        return {'status':'review_order' if quantity else 'no_order','available_stock':f(available),'reorder_point':f(point),'target_stock':f(target),'suggested_quantity':f(quantity),'automatic_purchase':False}
    except (KeyError,ValueError,TypeError):
        return blocked


def analyze_inventory(payload, today, policies=None, reservations=None, batches=None, window_days=90):
    policies,reservations,batches=policies or {},reservations or {},batches or {}
    result={'items':[],'warnings':[],'financial_access_required':True,'automatic_purchase':False,'method_version':1}
    if not payload:
        return {**result,'status':'source_missing','warnings':['نسخهٔ کالا و فاکتور هلو موجود نیست.']}
    source=payload.get('sources',{})
    try:
        factor=valid(payload.get('currency_factor'))
        if factor not in {1,10}:raise ValueError()
        end=min(_day(payload['to_date']),today)
        requested=end-timedelta(days=window_days-1)
        start=max(_day(payload['from_date']),requested)
        covered=(end-start).days+1
        if covered<=0:raise ValueError()
    except (KeyError,ValueError):
        return {**result,'status':'source_invalid','warnings':['واحد پول یا بازهٔ منبع معتبر نیست.']}
    fresh=end==today
    complete=all(source.get(k,{}).get('ok') and source.get(k,{}).get('complete') for k in ('products','sales','sales_returns'))
    metrics=defaultdict(lambda:{'outbound':Decimal(0),'returns':Decimal(0),'revenue':Decimal(0),'free_units':Decimal(0),'last_sale':None,'invoices':set(),'recent30':Decimal(0),'prior30':Decimal(0)})
    errors=Counter()
    for kind in ('sales','sales_returns'):
        seen=set()
        for row in source.get(kind,{}).get('rows',[]):
            try:
                key=str(row.get('ErpCode') or row.get('SanadCode') or '')
                when=_day(row.get('Date'))
                if not key or key in seen:raise EvidenceError('duplicate')
                seen.add(key)
                if not start<=when<=end:continue
                items,net,_=_normalize_invoice(row,factor,SEMANTICS)
                for item in items:
                    value=metrics[item['product']]
                    returned=kind=='sales_returns'
                    value['returns' if returned else 'outbound']+=item['quantity']
                    value['revenue']+=item['net']*(-1 if returned else 1)
                    if not returned:
                        age=(end-when).days
                        if age<30:value['recent30']+=item['quantity']
                        elif age<60:value['prior30']+=item['quantity']
                        value['free_units']+=item['quantity'] if item['net']==0 else 0
                        value['last_sale']=max(value['last_sale'] or when,when)
                        value['invoices'].add(key)
            except (EvidenceError,ValueError,TypeError):
                errors[kind]+=1
                complete=False
    costs=estimate_purchase_profit({**payload,'invoice_amount_semantics':{k:SEMANTICS for k in ('sales','purchases','sales_returns','purchase_returns')}},0,detail_from=start)
    by_cost={p['product_erp_code']:p for p in costs.get('products',[])}
    seen_products=set()
    duplicate_codes=Counter(str(p.get('ErpCode') or '') for p in source.get('products',{}).get('rows',[]))
    for raw in source.get('products',{}).get('rows',[]):
        code=str(raw.get('ErpCode') or '')
        if not code or duplicate_codes[code]!=1:
            errors['products']+=1;continue
        seen_products.add(code)
        value=metrics[code]
        warnings=[]
        active=raw.get('IsActive') in (True,1,'true','True','1')
        if not active:warnings.append('فعال‌بودن کالا در منبع تأیید نشده یا کالا غیرفعال است؛ سفارش مسدود است.')
        try:stock=valid(raw.get('Few'))
        except ValueError:stock=None;warnings.append('موجودی کالا معتبر نیست.')
        reserve=reservations.get(code)
        if reserve is not None:
            try:reserve=valid(reserve)
            except ValueError:reserve=None
        if reserve is None:warnings.append('نگاشت رزروهای این کالا تأیید نشده است.')
        try:reference_cost=valid(raw.get('BuyPrice'))*factor
        except ValueError:reference_cost=None
        try:reference_sell=valid(raw.get('SellPrice'))*factor
        except ValueError:reference_sell=None
        days_since=(end-value['last_sale']).days if value['last_sale'] else None
        daily=value['outbound']/covered if complete else None
        movement='نامشخص' if not complete else 'بدون خروج در بازه' if not value['outbound'] else 'بدون خروج در ۹۰ روز' if days_since>=90 else 'کم‌تحرک در ۳۰ روز اخیر' if days_since>=30 else 'دارای خروج اخیر'
        if not complete:warnings.append('منبع فروش یا برگشت ناقص/نامعتبر است.')
        if not fresh:warnings.append('موجودی و فروش تا روز جاری تازه نشده‌اند؛ سفارش مسدود است.')
        if covered<window_days:warnings.append('پوشش تاریخ کمتر از بازهٔ انتخابی است؛ سفارش مسدود است.')
        expiry=[];total_batch=Decimal(0);expired=Decimal(0)
        for batch in batches.get(code,[]):
            try:
                expiry_date=_day(batch['expiry_date']);qty=valid(batch['quantity']);total_batch+=qty
                if expiry_date<today:expired+=qty
                if expiry_date<=today+timedelta(days=90):expiry.append({'batch_code':batch['batch_code'],'expiry_date':expiry_date.isoformat(),'quantity':f(qty),'expired':expiry_date<today})
            except (ValueError,KeyError):warnings.append('اطلاعات یکی از بچ‌ها معتبر نیست.')
        if not batches.get(code):warnings.append('اطلاعات سری ساخت و انقضا موجود نیست؛ نبود هشدار به معنی نبود انقضا نیست.')
        if stock is not None and total_batch>stock:warnings.append('جمع بچ‌های دستی از موجودی هلو بیشتر است؛ تطبیق لازم است.')
        if expired:warnings.append('کالای منقضی در بچ‌های ثبت‌شده وجود دارد؛ موجودی قابل فروش باید تطبیق شود.')
        order=order_scenario(stock,reserve,daily,policies.get(code)) if stock is not None and reserve is not None and daily is not None else {'status':'data_required','suggested_quantity':None}
        if not active or not fresh or not complete or covered<window_days or expired or (stock is not None and total_batch>stock):
            order={'status':'data_required','suggested_quantity':None}
        cost=by_cost.get(code,{})
        profit=cost.get('estimated_gross_profit_irr')
        if profit is None:warnings.append('بهای کامل تاریخی و سیاست مالیات برای سود این کالا کافی نیست.')
        result['items'].append({'erp_code':code,'name':raw.get('Name') or 'کالای بدون نام','display_code':str(raw.get('Code') or ''),'active':active,
            'current_sell_price_irr':f(reference_sell),
            'stock':f(stock),'reserved':f(reserve),'outbound_quantity':f(value['outbound']) if complete else None,'return_quantity':f(value['returns']) if complete else None,
            'free_outbound_units':f(value['free_units']) if complete else None,'net_sales_irr':f(value['revenue']) if complete else None,
            'last_sale_date':value['last_sale'].isoformat() if value['last_sale'] else None,'days_since_last_sale':days_since,'movement':movement,
            'outbound_trend_percent':f((value['recent30']-value['prior30'])/value['prior30']*100) if complete and covered>=60 and value['prior30'] else None,
            'daily_observed_outbound':f(daily),'stock_cover_days':f(max(Decimal(0),stock-(valid(reserve) if reserve is not None else 0))/daily) if stock is not None and reserve is not None and daily else None,
            'capital_at_current_purchase_price_irr':f(stock*reference_cost) if stock is not None and reference_cost is not None else None,
            'estimated_gross_profit_irr':profit,'costed_sales_lines':cost.get('costed_sales_lines',0),'sales_lines':cost.get('sales_lines',0),
            'order':order,'expiry_alerts':expiry,'warnings':warnings,'policy':policies.get(code)})
    positives=sorted([r for r in result['items'] if (r['net_sales_irr'] or 0)>0],key=lambda r:r['net_sales_irr'],reverse=True)
    total=sum(r['net_sales_irr'] for r in positives);cumulative=0
    for row in positives:
        # The class uses cumulative revenue before the item, so the largest item is A.
        row['abc_class']='A' if cumulative<.8 else 'B' if cumulative<.95 else 'C'
        row['revenue_share_percent']=100*row['net_sales_irr']/total
        cumulative+=row['net_sales_irr']/total
    for row in result['items']:row.setdefault('abc_class',None)
    if any(code not in seen_products for code in metrics):result['warnings'].append('بعضی شناسه‌های فاکتور در فهرست کالا نگاشت یکتا ندارند.')
    result.update(status='observed' if complete else 'partial',from_date=start.isoformat(),to_date=end.isoformat(),as_of=today.isoformat(),covered_days=covered,requested_days=window_days,source_fresh=fresh,errors=dict(errors),
        methods=['نرخ خروج مشاهده‌شده شامل افر فروش است؛ برگشت جدا نمایش داده می‌شود و بدون تأیید قابل‌فروش‌بودن به تقاضا برگردانده نمی‌شود.',
                 'نقطه سفارش: خروج روزانه × روز تأمین + ذخیره؛ موجودی هدف: خروج روزانه × مجموع روز تأمین و بازبینی + ذخیره. مقدار پیشنهادی با حداقل سفارش و مضرب بسته گرد به بالا می‌شود.',
                 'گروه‌بندی الف/ب/ج بر سهم فروش خالص مثبت با مرزهای مرجع ۸۰ و ۹۵ درصد است؛ قاعدهٔ پیش‌بینی تقاضا نیست.',
                 'عدم فروش در بازه، سن واقعی موجودی را ثابت نمی‌کند. ارزش بر قیمت خرید فعلی، برآورد سرمایه است و بهای تاریخی یا سود حسابداری نیست.'])
    result['methods'].append('فروش ثبت‌شده، تقاضای واقعیِ بدون محدودیت موجودی نیست؛ کمبود موجودی و فصل و ترویج فروش در این سناریو مدل نشده‌اند. روند، خروج ۳۰ روز آخر در برابر ۳۰ روز قبل است و با مخرج صفر نامعلوم می‌ماند.')
    return result
