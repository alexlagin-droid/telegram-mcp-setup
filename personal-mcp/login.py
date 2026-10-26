"""One-time interactive setup: Telegram login + registration in MCP clients.

    python login.py              # login (if needed) + register
    python login.py --relogin    # force a new login
    python login.py --register   # only (re)register in Claude Desktop / Claude Code / Cursor
    python login.py --test       # check that the saved session works
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
SERVER_PATH = BASE_DIR / "server.py"
SERVER_NAME = "telegram"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    if os.name != "nt":
        os.chmod(CONFIG_PATH, 0o600)


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


async def do_login(cfg: dict) -> dict:
    print()
    print("=== Шаг 1. API ключи Telegram ===")
    print("Откроется https://my.telegram.org -> API development tools.")
    print("Войдите по номеру, создайте приложение (любое название), скопируйте api_id и api_hash.")
    if not cfg.get("api_id"):
        try:
            webbrowser.open("https://my.telegram.org/apps")
        except Exception:
            pass
    while True:
        api_id = ask("api_id", str(cfg.get("api_id", "")))
        if api_id.isdigit():
            break
        print("api_id - это число, попробуйте ещё раз")
    api_hash = ask("api_hash", cfg.get("api_hash", ""))

    print()
    print("=== Шаг 2. Вход в аккаунт ===")
    print("Номер в формате +79991234567. Код придёт в приложение Telegram.")
    client = TelegramClient(StringSession(), int(api_id), api_hash,
                            device_model="Personal MCP", app_version="1.0")
    await client.start()  # prompts for phone, code and 2FA password
    me = await client.get_me()
    session = client.session.save()
    await client.disconnect()
    print(f"\nВход выполнен: {me.first_name} (@{me.username or '-'})")

    cfg.update(api_id=int(api_id), api_hash=api_hash, session=session)
    cfg.setdefault("read_only", False)
    cfg.setdefault("send_allowlist", [])
    save_config(cfg)
    print(f"Сохранено в {CONFIG_PATH}")
    return cfg


# ---------------------------------------------------------------- registering

def server_entry() -> dict:
    return {"command": sys.executable, "args": [str(SERVER_PATH)]}


def update_json_config(path: Path, label: str):
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except json.JSONDecodeError:
        print(f"  [!] {label}: {path} повреждён, пропускаю")
        return
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    data.setdefault("mcpServers", {})[SERVER_NAME] = server_entry()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  [+] {label}: {path}")


def claude_desktop_configs() -> list[Path]:
    paths = []
    if os.name == "nt":
        appdata = Path(os.environ.get("APPDATA", ""))
        paths.append(appdata / "Claude" / "claude_desktop_config.json")
        # Microsoft Store build keeps its config inside the package folder.
        packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Packages"
        if packages.exists():
            for pkg in packages.glob("Claude_*"):
                paths.append(pkg / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json")
    elif sys.platform == "darwin":
        paths.append(Path.home() / "Library/Application Support/Claude/claude_desktop_config.json")
    else:
        paths.append(Path.home() / ".config/Claude/claude_desktop_config.json")
    # Only touch configs of installed apps (the Claude folder exists).
    return [p for p in paths if p.parent.exists()]


def register():
    print()
    print("=== Шаг 3. Подключение к ИИ-клиентам ===")
    found = False

    for path in claude_desktop_configs():
        update_json_config(path, "Claude Desktop")
        found = True

    cursor_dir = Path.home() / ".cursor"
    if cursor_dir.exists():
        update_json_config(cursor_dir / "mcp.json", "Cursor")
        found = True

    claude_cli = shutil.which("claude")
    if claude_cli:
        subprocess.run([claude_cli, "mcp", "remove", "-s", "user", SERVER_NAME],
                       capture_output=True)
        r = subprocess.run([claude_cli, "mcp", "add", "-s", "user", SERVER_NAME, "--",
                            sys.executable, str(SERVER_PATH)], capture_output=True, text=True)
        if r.returncode == 0:
            print("  [+] Claude Code: claude mcp add -s user telegram")
        else:
            print(f"  [!] Claude Code: {r.stderr.strip() or r.stdout.strip()}")
        found = True

    if not found:
        print("  Клиенты не найдены. Добавьте вручную в конфиг вашего MCP-клиента:")
    print()
    print("Конфиг для любого MCP-клиента:")
    print(json.dumps({"mcpServers": {SERVER_NAME: server_entry()}}, indent=2))
    print()
    print("Перезапустите Claude Desktop / Cursor, чтобы сервер подхватился.")


async def test(cfg: dict):
    client = TelegramClient(StringSession(cfg["session"]), cfg["api_id"], cfg["api_hash"])
    await client.connect()
    if not await client.is_user_authorized():
        print("Сессия недействительна - запустите: start.bat relogin")
        return
    me = await client.get_me()
    print(f"OK: {me.first_name} (@{me.username or '-'})\nПоследние чаты:")
    async for d in client.iter_dialogs(limit=5):
        print(f"  {d.name}  (id {d.id}, непрочитано {d.unread_count})")
    await client.disconnect()


def main():
    args = set(sys.argv[1:])
    cfg = load_config()
    if "--test" in args:
        if not cfg.get("session"):
            print("Сначала выполните вход: start.bat")
        else:
            asyncio.run(test(cfg))
        return
    if "--register" not in args and ("--relogin" in args or not cfg.get("session")):
        cfg = asyncio.run(do_login(cfg))
    elif cfg.get("session"):
        print(f"Уже авторизовано ({CONFIG_PATH}). Для повторного входа: start.bat relogin")
    register()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nОтменено")
        sys.exit(1)
