"""Check explicitly stated money against proposed writes, without model arithmetic."""
import re
from decimal import Decimal,InvalidOperation

DIGITS=str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')
SCALES={'هزار':1000,'میلیون':1000000,'میلیارد':1000000000}
WORDS={'یک':1,'دو':2,'سه':3,'چهار':4,'پنج':5,'شش':6,'هفت':7,'هشت':8,'نه':9,'ده':10,'یازده':11,'دوازده':12,'سیزده':13,'چهارده':14,'پانزده':15,'شانزده':16,'هفده':17,'هجده':18,'نوزده':19,'بیست':20,'سی':30,'چهل':40,'پنجاه':50,'شصت':60,'هفتاد':70,'هشتاد':80,'نود':90,'صد':100,'دویست':200,'سیصد':300}
MONEY_FIELDS={'amount','target_amount','price','price2','current_balance','minimum_reserve','bonus_reward','reported_sales_amount','reported_collections_amount'}
_NUMBER = r'(?:\d+(?:\.\d+)?|' + '|'.join(sorted(WORDS, key=len, reverse=True)) + r')'
_MONEY = re.compile(rf'(?<![\w\-−])({_NUMBER})\s*(هزار|میلیون|میلیارد)?\s*(تومان|تومن|ریال)(?!\w)')


def _normalized_money(text):
    return text.translate(DIGITS).replace('٬','').replace(',','').replace('٫','.').replace('\u200c',' ').strip()


def _in_rials(match):
    raw, scale, unit = match.groups()
    value = Decimal(WORDS[raw]) if raw in WORDS else Decimal(raw)
    return value * SCALES.get(scale, 1) * (10 if unit in {'تومان', 'تومن'} else 1)


def explicit_money(message):
    return [_in_rials(match) for match in _MONEY.finditer(_normalized_money(message))]


def parse_money_phrase(phrase):
    match = _MONEY.fullmatch(_normalized_money(phrase))
    if match is None:
        raise ValueError('مبلغ را همراه واحد ریال یا تومان مشخص کنید.')
    return _in_rials(match)


def check_proposed_money(message,operation,payload):
    expected=set(explicit_money(message))
    if not expected or operation=='save_contract':return None
    errors=[]
    def walk(value,unit='IRR',path='payload'):
        if isinstance(value,list):
            for i,item in enumerate(value):walk(item,unit,f'{path}.{i}')
        elif isinstance(value,dict):
            unit=value.get('unit',unit)
            for key,item in value.items():
                if key in MONEY_FIELDS and item is not None:
                    try:
                        amount=Decimal(str(item))*(10 if unit in {'TOMAN','toman'} else 1)
                    except InvalidOperation:continue
                    if amount!=0 and amount not in expected:errors.append(path+'.'+key)
                else:walk(item,unit,path+'.'+key)
    walk(payload)
    if errors:
        return {'status':'needs_currency_review','fields':errors,
                'explicit_amounts_irr':[str(x) for x in sorted(expected)],
                'message':'مبلغ پیشنهادی با مبلغ صریح درخواست سازگار نیست. تبدیل واحد فقط یک بار انجام شود: اگر unit برابر TOMAN است، مبلغ ردیف به تومان باقی می‌ماند. ساختار و مقدار را اصلاح کن؛ هنوز پیشنهادی ذخیره نشده است.'}


def normalize_explicit_toman(message,payload):
    import copy
    result=copy.deepcopy(payload)
    stated=set(explicit_money(message))
    def walk(value,unit='IRR'):
        if isinstance(value,list):
            for item in value:walk(item,unit)
        elif isinstance(value,dict):
            unit=value.get('unit',unit)
            for key,item in value.items():
                if key in MONEY_FIELDS and unit in {'TOMAN','toman'} and item is not None:
                    try:amount=Decimal(str(item))
                    except InvalidOperation:continue
                    # Only a unique literal money amount proves double conversion.
                    if amount in stated and amount*10 not in stated:value[key]=str(amount/10)
                else:walk(item,unit)
    walk(result)
    return result
