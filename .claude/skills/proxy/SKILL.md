---
name: proxy
description: Подключение через прокси при региональных блокировках, таймаутах и ошибках доступа
trigger: automatic — когда запрос не проходит (403, timeout, connection refused, regional block)
---

# Прокси

## Когда использовать

Автоматически применяй прокси, когда команда или запрос не проходит из-за:
- Региональных ограничений (403 Forbidden, Access Denied)
- Таймаутов (connection timeout, read timeout)
- Отказов соединения (connection refused, connection reset)
- Любых других сетевых блокировок

## Данные прокси

Добавь в `.env` проекта:

```env
PROXY_HOST=<ваш IP>
PROXY_PORT=<ваш порт>
PROXY_LOGIN=<ваш логин>
PROXY_PASSWORD=<ваш пароль>
```

Полные URL (собираются из переменных):
```
HTTP_PROXY=http://<login>:<password>@<host>:<port>
HTTPS_PROXY=http://<login>:<password>@<host>:<port>
```

## Как применять

### Для Bash-команд (curl, wget, pip, npm и т.д.)

Добавляй переменные окружения перед командой:

```bash
HTTP_PROXY=$HTTP_PROXY HTTPS_PROXY=$HTTPS_PROXY <команда>
```

Примеры:
```bash
# curl
HTTP_PROXY=$HTTP_PROXY HTTPS_PROXY=$HTTPS_PROXY curl https://example.com

# pip
HTTP_PROXY=$HTTP_PROXY HTTPS_PROXY=$HTTPS_PROXY pip install package

# wget
HTTP_PROXY=$HTTP_PROXY HTTPS_PROXY=$HTTPS_PROXY wget https://example.com/file
```

### Для Python-скриптов

```python
import os
os.environ['HTTP_PROXY'] = 'http://$PROXY_LOGIN:$PROXY_PASSWORD@$PROXY_HOST:$PROXY_PORT'
os.environ['HTTPS_PROXY'] = 'http://$PROXY_LOGIN:$PROXY_PASSWORD@$PROXY_HOST:$PROXY_PORT'
```

### Для requests / httpx в Python

```python
proxies = {
    'http': 'http://$PROXY_LOGIN:$PROXY_PASSWORD@$PROXY_HOST:$PROXY_PORT',
    'https': 'http://$PROXY_LOGIN:$PROXY_PASSWORD@$PROXY_HOST:$PROXY_PORT',
}
response = requests.get(url, proxies=proxies)
```

## Важно

- Прокси использовать ТОЛЬКО когда прямое подключение не работает
- Сначала попробуй без прокси, при ошибке — повтори через прокси
- Не логируй и не выводи пользователю логин/пароль прокси в открытом виде
