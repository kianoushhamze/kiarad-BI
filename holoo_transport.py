"""Shared HTTP transport for private Tailnet Holoo endpoints."""
import ipaddress
from urllib.parse import urlsplit
import requests


def holoo_request(method, url, **kwargs):
    host = (urlsplit(url).hostname or '').lower()
    try:
        tailnet = ipaddress.ip_address(host) in ipaddress.ip_network('100.64.0.0/10')
    except ValueError:
        tailnet = host.endswith('.ts.net')
    if tailnet:
        with requests.Session() as session:
            session.trust_env = False
            return session.request(method, url, **kwargs)
    return requests.request(method, url, **kwargs)
