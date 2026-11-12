"""Capacity-constrained, two-cycle field routes with explicit travel estimates."""
from datetime import date, datetime, time, timedelta
from math import asin, cos, radians, sin, sqrt, ceil
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RoutePolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    user_ids: list[int] = Field(min_length=1, max_length=20)
    month: str = Field(pattern=r'^14\d{2}-(0[1-9]|1[0-2])$')
    dates: list[date] = Field(min_length=1, max_length=31)
    visits_per_base: int = Field(default=2, ge=1, le=4)
    stops_per_day: int = Field(default=10, ge=1, le=12)
    work_minutes: int = Field(default=480, ge=60, le=720)
    break_minutes: int = Field(default=30, ge=0, le=120)
    visit_minutes: int = Field(default=25, ge=5, le=120)
    min_gap_days: int = Field(default=10, ge=1, le=21)
    start_time: time = time(8, 0)
    estimated_speed_kmh: float = Field(default=30, ge=5, le=100)
    detour_factor: float = Field(default=1.4, ge=1, le=3)
    max_leg_km: float = Field(default=40, ge=1, le=300)
    depot_latitude: float = Field(ge=-90, le=90)
    depot_longitude: float = Field(ge=-180, le=180)
    city: str | None = Field(default=None, max_length=100)

    @field_validator('user_ids')
    @classmethod
    def users(cls, values):
        if len(values) != len(set(values)) or any(type(v) is not int or v <= 0 for v in values):
            raise ValueError('Distinct positive user IDs required')
        return values

    @model_validator(mode='after')
    def valid_window(self):
        from monthly_visit_plans import month_window
        begin, end = month_window(self.month)
        if len(set(self.dates)) != len(self.dates) or any(not begin <= d < end for d in self.dates):
            raise ValueError('Dates must be distinct and inside the selected Jalali month')
        if self.break_minutes + self.visit_minutes > self.work_minutes:
            raise ValueError('Shift cannot fit a visit and break')
        if self.start_time.hour * 60 + self.start_time.minute + self.work_minutes > 24 * 60:
            raise ValueError('Shift must end on the same local day')
        return self


def distance_km(a, b):
    x1,y1,x2,y2=map(radians,[a[0],a[1],b[0],b[1]])
    value=sin((x2-x1)/2)**2+cos(x1)*cos(x2)*sin((y2-y1)/2)**2
    return 6371*2*asin(sqrt(min(1,value)))


def build_routes(bases, policy: RoutePolicy, *, today: date):
    dates=sorted(d for d in policy.dates if d>today)
    depot=(policy.depot_latitude,policy.depot_longitude)
    eligible=[];missing=[];seen=set()
    for base in bases:
        key=(base['source'],base['id'])
        if key in seen:continue
        seen.add(key)
        if policy.city and (base.get('city') or '').strip()!=policy.city.strip():continue
        lat,lng=base.get('latitude'),base.get('longitude')
        if lat is None or lng is None or not -90<=float(lat)<=90 or not -180<=float(lng)<=180:
            missing.append({'source':key[0],'id':key[1],'name':base.get('name'),'reason':'missing_coordinates'})
            continue
        eligible.append(dict(base,key=key,point=(float(lat),float(lng))))
    counts={b['key']:0 for b in eligible};last={};owner={};routes=[]
    travel=lambda a,b:ceil(distance_km(a,b)*policy.detour_factor/policy.estimated_speed_kmh*60)
    for day in dates:
        for uid in policy.user_ids:
            selected=[];point=depot;minutes=policy.break_minutes
            while len(selected)<policy.stops_per_day:
                candidates=[b for b in eligible if counts[b['key']]<policy.visits_per_base
                    and (b['key'] not in last or (day-last[b['key']]).days>=policy.min_gap_days)
                    and (b['key'] not in owner or owner[b['key']]==uid)]
                # Cover lower visit counts first; deterministic order makes review reproducible.
                candidates.sort(key=lambda b:(counts[b['key']],distance_km(point,b['point']),b['source'],b['id']))
                picked=None
                for b in candidates:
                    leg=distance_km(point,b['point'])
                    if selected and leg>policy.max_leg_km:continue
                    cost=travel(point,b['point'])+policy.visit_minutes
                    if minutes+cost+travel(b['point'],depot)<=policy.work_minutes:
                        picked=(b,cost);break
                if picked is None:break
                b,cost=picked;arrival=minutes+travel(point,b['point']);minutes+=cost
                start=datetime.combine(day,policy.start_time)+timedelta(minutes=arrival)
                selected.append({'base_source':b['source'],'base_id':b['id'],'name':b.get('name'),
                    'visit_date':day.isoformat(),'stop_order':len(selected)+1,'objective':'ویزیت، نیازسنجی و ثبت نتیجه',
                    'start_time':start.time().isoformat(),'end_time':(start+timedelta(minutes=policy.visit_minutes)).time().isoformat()})
                counts[b['key']]+=1;last[b['key']]=day;owner[b['key']]=uid;point=b['point']
            if selected:
                routes.append({'user_id':uid,'date':day.isoformat(),'stops':selected,
                    'estimated_total_minutes':minutes+travel(point,depot),'travel_basis':'straight_line_detour_estimate_not_road_routing'})
    shortfalls=[{'source':b['source'],'id':b['id'],'name':b.get('name'),'scheduled':counts[b['key']],
                 'required':policy.visits_per_base} for b in eligible if counts[b['key']]<policy.visits_per_base]
    needed=len(eligible)*policy.visits_per_base
    return {'feasible':not missing and not shortfalls and needed>0,'routes':routes,'missing_coordinates':missing,
            'uncovered':shortfalls,'required_visits':needed,'scheduled_visits':sum(counts.values()),
            'theoretical_capacity':len(dates)*len(policy.user_ids)*policy.stops_per_day,
            'minimum_staff_by_visit_count':ceil(needed/(len(dates)*policy.stops_per_day)) if dates and needed else None,
            'policy':policy.model_dump(mode='json'),'warnings':['زمان سفر برآورد است؛ ترافیک، ساعات پذیرش و زمان جاده‌ای هنوز تأیید نشده‌اند.',
                'برنامه فقط روزهای آینده را شامل می‌شود و تا تصویب، مسیر عملیاتی ایجاد نمی‌کند.']}
