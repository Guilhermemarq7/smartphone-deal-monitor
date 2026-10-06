from src.normalize import parse_brl, extract_storage_gb, is_accessory, detect_condition, match_target
from src.models import Target


def T():
    return [Target('s25','Samsung Galaxy S25 256GB','Samsung',['Galaxy S25 256GB'],256,3350,3200,3000,'high',78)]

def test_parse_brl():
    assert parse_brl('R$ 3.531,85') == 3531.85
    assert parse_brl('3.899,00 no Pix') == 3899.0

def test_storage():
    assert extract_storage_gb('Galaxy S25 256 GB 12GB RAM') == 256
    assert extract_storage_gb('telefone 1 TB') == 1024

def test_accessory_and_condition():
    assert is_accessory('Capa para Galaxy S25 256GB')
    assert detect_condition('Usado: Samsung Galaxy S25 256GB') == 'used'
    assert detect_condition('Galaxy S25 256GB novo lacrado') == 'new'

def test_match_storage_exact():
    assert match_target('Samsung Galaxy S25 256GB Azul',T()).id == 's25'
    assert match_target('Samsung Galaxy S25 128GB Azul',T()) is None
