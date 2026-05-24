import pytest
from app.database import init_db

@pytest.fixture(autouse=True, scope="session")
def setup_test_db():
    """
    Tüm test session'ı başlamadan önce otomatik olarak çalışır ve
    boş/yeni bir ortamda (örneğin CI sunucusunda) veritabanı tablolarının
    yaratıldığından emin olur.
    """
    init_db()
