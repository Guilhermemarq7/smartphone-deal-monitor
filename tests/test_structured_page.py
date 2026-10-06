from src.collectors.structured_pages import StructuredPageCollector
from src.models import Target

HTML='''<html><head><script type="application/ld+json">{"@type":"Product","name":"Samsung Galaxy S25 256GB","offers":{"@type":"Offer","price":"3199.90","priceCurrency":"BRL"}}</script></head><body><h1>Samsung Galaxy S25 256GB</h1></body></html>'''

def test_jsonld_product():
    c=StructuredPageCollector({'pages':[]})
    t=Target('s25','Samsung Galaxy S25 256GB','Samsung',['Galaxy S25 256GB'],256,3350,3200,3000,'high',78)
    o=c._parse(HTML,{'url':'https://shop.example/p','store':'Samsung','target_id':'s25'},t,[t])
    assert o.price_base == 3199.90
    assert o.target_id == 's25'
    assert o.is_official_store
