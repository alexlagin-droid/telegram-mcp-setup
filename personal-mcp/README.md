# Personal Telegram MCP

Свой MCP-сервер, через который ИИ-агент (Claude Desktop, Claude Code, Cursor и т.д.) работает с **вашим личным аккаунтом** Telegram. Python + [Telethon](https://github.com/LonamiWebs/Telethon), без Docker.

## Запуск (Windows)

1. Скачайте папку `personal-mcp` в любое место, например `C:\tools\personal-mcp`.
2. Двойной клик по **`start.bat`**. Он сам:
   - найдёт Python 3.10+ (или предложит поставить через winget);
   - создаст `.venv` и поставит зависимости;
   - откроет my.telegram.org — возьмите там `api_id` и `api_hash`;
   - спросит номер телефона, код из Telegram и пароль 2FA (если есть);
   - пропишет сервер в Claude Desktop, Cursor и Claude Code (те, что установлены).
3. Перезапустите Claude Desktop / Cursor. Готово.

Другие команды:

| Команда | Что делает |
|---|---|
| `start.bat test` | проверить, что сессия жива, показать 5 последних чатов |
| `start.bat relogin` | войти заново (другой аккаунт / сессия отозвана) |
| `start.bat register` | только заново прописать сервер в клиентах (например, после переноса папки) |

macOS/Linux: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python login.py`.

## Инструменты для агента

Чтение: `get_me`, `list_chats`, `get_messages`, `search_messages`, `get_chat_info`, `download_media`, `mark_as_read`
Запись: `send_message`, `send_file`, `edit_message`, `forward_message`

Параметр `chat` принимает `@username`, числовой id, телефон, `me` (Избранное) или название чата.

## Настройки безопасности (`config.json`)

```json
{
  "read_only": true,
  "send_allowlist": ["me", "durov", "-1001234567890"]
}
```

- `read_only: true` — агент только читает, любые отправки запрещены.
- `send_allowlist` — писать можно только в эти чаты (username без @ или id). Пустой список = в любые.

## ⚠️ Важно

- `config.json` содержит **строку сессии = полный доступ к аккаунту** (переписка, отправка от вашего имени, без пароля и 2FA). Не отправляйте его никому, не коммитьте, не кладите в облачные папки.
- Скомпрометировали? Telegram → Настройки → Устройства → завершите сеанс **«Personal MCP»**, потом `start.bat relogin`.
- Текст сообщений, которые читает агент, уходит к провайдеру модели — не давайте ему читать то, что не готовы показать.
- Telegram может ограничить аккаунт за спам/массовые рассылки через userbot. Не просите агента слать много сообщений незнакомым людям.
