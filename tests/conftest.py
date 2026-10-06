import pytest
from src.models import Target


@pytest.fixture
def targets():
    return [
        Target('s25', 'Samsung Galaxy S25 256GB', 'Samsung', ['Galaxy S25 256GB'], 256, 3350, 3200, 3000, 'high', 78, 4000, 3000),
        Target('s26', 'Samsung Galaxy S26 256GB', 'Samsung', ['Galaxy S26 256GB'], 256, 3600, 3400, 3200, 'high', 90, 4300, 3500),
    ]
