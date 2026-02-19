import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    def _load_dotenv_file(path: str = ".env") -> None:
        env_path = Path(path)
        if not env_path.exists():
            return
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return
        for raw_line in lines:
            line = str(raw_line or "").lstrip("\ufeff").strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            key = key.strip().lstrip("\ufeff")
            if not key:
                continue
            value = raw_value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    _load_dotenv_file(".env")

from core.app_factory import create_app

try:
    app = create_app()
except RuntimeError as e:
    if "SECRET_KEY" in str(e):
        print("启动失败：未配置 SECRET_KEY。请在项目根目录的 .env 中设置 SECRET_KEY，或设置 DEV_ALLOW_INSECURE=1 用于本地开发。")
    raise
except Exception as e:
    print("启动失败：", e)
    raise

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = str(os.getenv("FLASK_DEBUG", "0")).strip().lower() in {"1", "true", "yes", "on"}
    app.run(host=host, port=port, debug=debug)
