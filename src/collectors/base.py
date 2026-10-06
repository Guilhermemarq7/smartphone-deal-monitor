from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from ..models import Offer, Target

@dataclass
class CollectorResult:
    source: str
    offers: list[Offer]
    ok: bool
    message: str=""

class Collector(Protocol):
    name: str
    def collect(self, targets:list[Target]) -> CollectorResult: ...


def build_session(user_agent:str, retries:int=2, backoff:float=.7) -> requests.Session:
    s=requests.Session(); s.headers.update({"User-Agent":user_agent,"Accept-Language":"pt-BR,pt;q=0.9,en;q=0.5"})
    retry=Retry(total=retries,connect=retries,read=retries,status=retries,backoff_factor=backoff,
                status_forcelist=(429,500,502,503,504),allowed_methods=frozenset(["GET","HEAD"]))
    s.mount("https://",HTTPAdapter(max_retries=retry)); s.mount("http://",HTTPAdapter(max_retries=retry))
    return s
