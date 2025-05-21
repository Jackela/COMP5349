import sys
import os
import importlib.util # <--- 新增导入，用于更底层的模块查找诊断

# ----- Start of sys.path modification and debug block -----
print(f"\nDEBUG: ---- TOP OF tests/web_app/conftest.py ----")
print(f"DEBUG: Current __file__ is {__file__}")

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
print(f"DEBUG: Calculated project_root: {project_root}")

# 确保 project_root 在 sys.path 的第一个位置
if project_root in sys.path and sys.path[0] != project_root:
    # 如果 project_root 已存在但不在首位，则先移除 (处理大小写不一致等情况)
    try:
        sys.path.remove(project_root.lower()) # 尝试移除小写版本
    except ValueError:
        pass
    try:
        sys.path.remove(project_root.upper()) # 尝试移除大写版本
    except ValueError:
        pass
    try:
        sys.path.remove(project_root) # 尝试移除原始版本
    except ValueError:
        pass
    sys.path.insert(0, project_root)
    print(f"DEBUG: Moved/Ensured {project_root} is at the front of sys.path")
elif project_root not in sys.path:
    sys.path.insert(0, project_root)
    print(f"DEBUG: Added {project_root} to sys.path")
else:
    print(f"DEBUG: {project_root} was ALREADY at the front of sys.path.")

print(f"DEBUG: Current sys.path (after ensuring project_root is at index 0):")
for i, p_path in enumerate(sys.path):
    print(f"  sys.path[{i}]: {p_path}")
print("----- End of sys.path debug -----\n")
# ----- End of sys.path modification and debug block -----

# ----- 新增的 importlib 诊断代码块 -----
print(f"DEBUG: ---- importlib.util.find_spec diagnostics ----")
# 检查 'web_app' 包
spec_web_app = importlib.util.find_spec("web_app")
print(f"DEBUG: importlib.util.find_spec('web_app') result: {spec_web_app}")
if spec_web_app:
    print(f"DEBUG: spec_web_app.name: {spec_web_app.name}")
    print(f"DEBUG: spec_web_app.loader: {spec_web_app.loader}")
    print(f"DEBUG: spec_web_app.origin: {spec_web_app.origin}") # 应该指向 web_app/__init__.py
    print(f"DEBUG: spec_web_app.has_location: {spec_web_app.has_location}")
    if spec_web_app.has_location:
        print(f"DEBUG: spec_web_app.submodule_search_locations: {spec_web_app.submodule_search_locations}") # 应该包含 web_app 目录

# 检查 'web_app.app' 模块
spec_web_app_app = importlib.util.find_spec("web_app.app")
print(f"DEBUG: importlib.util.find_spec('web_app.app') result: {spec_web_app_app}")
if spec_web_app_app:
    print(f"DEBUG: spec_web_app_app.name: {spec_web_app_app.name}")
    print(f"DEBUG: spec_web_app_app.loader: {spec_web_app_app.loader}")
    print(f"DEBUG: spec_web_app_app.origin: {spec_web_app_app.origin}") # 应该指向 web_app/app.py
print("----- End of importlib.util.find_spec diagnostics -----\n")
# ----- 诊断代码块结束 -----

# 你原来的导入语句和其他 conftest.py 内容
import pytest
from unittest.mock import patch, MagicMock
from web_app.app import app as flask_app # 这行是关键



# 下面是你原来 `tests/web_app/conftest.py` 中定义的 fixtures
@pytest.fixture(autouse=True)
def mock_env_vars():
    """Mock environment variables for all tests."""
    with patch.dict(os.environ, {
        'DB_HOST': 'test-db-host',
        'DB_USER': 'test-db-user',
        'DB_PASSWORD': 'test-db-password',
        'DB_NAME': 'test-db-name',
        'DB_PORT': '3306',
        'S3_IMAGE_BUCKET': 'test-image-bucket',
        'FLASK_SECRET_KEY': 'test-secret-key',
        'LOG_LEVEL': 'DEBUG'
    }):
        yield

@pytest.fixture
def mock_db_connection():
    """Mock database connection for all tests."""
    # 注意：这里的 'web_app.utils.db_utils.get_db_connection' 路径
    # 需要确保与你的项目中 db_utils.py 的实际位置和导入方式一致
    with patch('web_app.utils.db_utils.get_db_connection') as mock_get_db:
        mock_conn = MagicMock()
        mock_get_db.return_value = mock_conn
        yield mock_conn

@pytest.fixture
def mock_s3_client():
    """Mock S3 client for all tests."""
    with patch('boto3.client') as mock_client: # 通常 boto3.client 是这么 mock
        mock_s3 = MagicMock()
        mock_client.return_value = mock_s3
        yield mock_s3

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    # 使用从 web_app.app 导入的 flask_app 实例
    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,  # Disable CSRF protection for testing
        "MAX_CONTENT_LENGTH": 16 * 1024 * 1024,  # 16MB
        "ALLOWED_EXTENSIONS": {'png', 'jpg', 'jpeg', 'gif'},
        # Explicitly set S3_IMAGE_BUCKET here to ensure it's not None
        "S3_IMAGE_BUCKET": os.environ.get('S3_IMAGE_BUCKET', 'test-image-bucket-fallback'),
        "DB_HOST": os.environ.get('DB_HOST'), # Ensure these are also picked up if mock_env_vars is used
        "DB_USER": os.environ.get('DB_USER'),
        "DB_PASSWORD": os.environ.get('DB_PASSWORD'),
        "DB_NAME": os.environ.get('DB_NAME'),
        "DB_PORT": int(os.environ.get('DB_PORT', 3306))
    })
    
    with flask_app.test_request_context():
        yield flask_app

@pytest.fixture
def client(app): # 依赖上面定义的 app fixture
    """A test client for the app."""
    # Patch get_db_connection here to ensure it's active for test client requests
    with patch('web_app.utils.db_utils.get_db_connection') as mock_get_db_conn:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        # Configure common mock behaviors for the DB connection if needed
        # For example, mock_cursor.fetchone.return_value = None
        # mock_cursor.fetchall.return_value = []
        # mock_cursor.lastrowid = 1 # if your tests expect a lastrowid
        mock_get_db_conn.return_value = mock_conn
        yield app.test_client()

@pytest.fixture
def runner(app): # 依赖上面定义的 app fixture
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()

@pytest.fixture
def mock_request_id():
    """Mock request ID for testing."""
    with patch('uuid.uuid4') as mock_uuid:
        mock_uuid.return_value.hex = 'test-request-id'
        yield 'test-request-id'