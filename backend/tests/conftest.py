import os
import pytest
from app.database import init_db

@pytest.fixture(autouse=True, scope="session")
def setup_test_db(tmp_path_factory):
    """
    Tüm test session'ı başlamadan önce otomatik olarak çalışır.
    Test veritabanı için tmp_path_factory ile izole bir dosya yolu oluşturur,
    böylece testler asıl 'backend/sqlgen.db' dosyasına yazmaz.
    """
    # İzole geçici bir db dosyası yarat
    test_db_dir = tmp_path_factory.mktemp("db")
    test_db_path = test_db_dir / "test_sqlgen.db"
    
    # Uygulamanın bu DB yolunu kullanmasını sağla
    os.environ["SQLGEN_DB_PATH"] = str(test_db_path)
    os.environ.setdefault("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "true")
    
    # Boş veritabanına tabloları kur
    init_db()

@pytest.fixture(autouse=True)
def clear_settings_cache():
    from app.settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
