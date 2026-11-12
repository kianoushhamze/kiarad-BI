"""Prepare a private, stateless Traccar forwarder; never print its credential."""
import argparse,os,re,secrets
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape
from dotenv import dotenv_values

IMAGE='traccar/traccar:6.17.0-alpine'

def configure(root,client_url):
    root=root.resolve();envfile=root/'.env'
    if not envfile.is_file():raise ValueError('Existing company/stage .env required; it is never created from defaults')
    if any(ord(ch)<32 for ch in client_url):raise ValueError('Control characters are not allowed in the GPS hostname')
    u=urlsplit(client_url)
    _=u.port  # Validate an explicitly supplied HTTPS port before writing files.
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in {'','/'}:raise ValueError('Use the HTTPS GPS hostname only, without credentials or a path')
    values=dotenv_values(envfile,encoding='utf-8-sig');token=values.get('KIARAD_TRACCAR_FORWARD_TOKEN') or secrets.token_hex(32)
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,200}',token):raise ValueError('Existing forwarding credential is invalid; correct it locally')
    folder=root/'secrets';folder.mkdir(exist_ok=True);config=folder/'traccar-forward.xml'
    # Forwarder only: no persistent third-party location database, public admin UI,
    # telemetry, reverse-geocoding or unused protocol listeners.
    entries={'database.memory':'true','database.registerUnknown':'true','database.registerUnknown.regex':'[a-f0-9]{32}','web.enable':'false','protocols.enable':'osmand','osmand.port':'5055',
             'forward.type':'json','forward.url':'http://backend:8000/tracking/traccar/positions',
             'forward.header':'X-Kiarad-Traccar-Token: '+token,'forward.retry.enable':'true','forward.retry.count':'10','forward.retry.delay':'10000','forward.retry.limit':'2000',
             'filter.enable':'false','geocoder.enable':'false','geolocation.enable':'false','speedLimit.enable':'false',
             'server.statistics':'','logger.level':'warning','logger.console':'true'}
    xml='<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">\n<properties>\n'+''.join('  <entry key="'+k+'">'+escape(v)+'</entry>\n' for k,v in entries.items())+'</properties>\n'
    temporary=config.with_suffix('.partial');temporary.write_text(xml,encoding='utf-8');os.chmod(temporary,0o600);os.replace(temporary,config)
    text=envfile.read_text(encoding='utf-8-sig');text=re.sub(r'(?m)^\s*(?:KIARAD_TRACCAR_ENABLED|KIARAD_TRACCAR_FORWARD_TOKEN|KIARAD_TRACCAR_CLIENT_URL)\s*=.*\r?$','',text)
    text+='\nKIARAD_TRACCAR_ENABLED=1\nKIARAD_TRACCAR_FORWARD_TOKEN='+token+'\nKIARAD_TRACCAR_CLIENT_URL='+client_url.rstrip('/')+'\n'
    tmp=envfile.with_suffix('.traccar.partial');tmp.write_text(text,encoding='utf-8');os.chmod(tmp,0o600);os.replace(tmp,envfile)
    return {'configured':True,'image':IMAGE,'persistent_gateway_location_database':False,'public_admin_UI':False,'company_device_acceptance_complete':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--client-url',required=True);a=p.parse_args()
    import json
    print(json.dumps(configure(a.root,a.client_url)))
