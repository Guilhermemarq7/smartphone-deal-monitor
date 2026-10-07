from src.collectors.magalu import _all_prices, _context_price, _coupon_value

def test_magalu_price_helpers():
    text='Preço R$ 3.899,00 R$ 3.899,00 no Pix Ou R$ 4.332,22 em 10x Cupom R$ 250 OFF'
    assert _context_price(text,'pix') == 3899.0
    assert 4332.22 in _all_prices(text)
    assert _coupon_value(text) == 250.0


def test_pix_context_does_not_cross_another_price():
    assert _context_price('Cashback R$ 500,00 Preço R$ 3.199,00 no Pix','pix') == 3199
