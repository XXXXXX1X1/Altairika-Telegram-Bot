---
name: tavily
description: Извлечение контента из URL (extract) и веб-поиск (search) через Tavily API. Автоматический fallback когда WebFetch не справляется.
---

# Tavily — извлечение контента и веб-поиск

Tavily API используется как **автоматический fallback** когда WebFetch возвращает мусор, ошибку, или пустой контент.

## Когда использовать АВТОМАТИЧЕСКИ (без вопросов пользователю)

- WebFetch вернул ошибку (403, 429, timeout)
- WebFetch вернул мусор (сплошной HTML, cookie-баннеры, "enable JavaScript", captcha)
- WebFetch вернул пустой или слишком короткий контент (< 100 символов полезного текста)
- Нужно извлечь контент из SPA/JavaScript-heavy сайта

**Правило:** Если WebFetch не дал полезный результат — сразу используй Tavily extract, не спрашивая пользователя.

## Режимы

### Extract — извлечение контента по URL

Когда есть конкретный URL и нужно получить его содержимое.

```bash
python3 ~/.claude/skills/tavily/tavily_client.py extract "https://example.com/article"
```

Несколько URL за раз (до 20):
```bash
python3 ~/.claude/skills/tavily/tavily_client.py extract "URL1" "URL2" "URL3"
```

Глубокое извлечение (для сложных сайтов, стоит 2x кредитов):
```bash
python3 ~/.claude/skills/tavily/tavily_client.py extract "URL" --depth advanced
```

### Search — поиск информации в интернете

Когда нужно найти актуальную информацию по запросу.

```bash
python3 ~/.claude/skills/tavily/tavily_client.py search "Claude Code MCP servers setup"
```

Глубокий поиск (больше результатов, дороже):
```bash
python3 ~/.claude/skills/tavily/tavily_client.py search "запрос" --depth advanced
```

## Переменные окружения

- `TAVILY_API_KEY` — API ключ Tavily. Скрипт ищет его в env vars, потом в `.env` файле текущего проекта.

## Обработка ошибок

- **Нет API ключа** → скажи пользователю добавить `TAVILY_API_KEY=...` в `.env`
- **URL failed** → попробуй с `--depth advanced`, если не помогло — сообщи пользователю
- **Timeout** → повтори один раз, потом сообщи

## Чеклист

- [ ] Убедился что WebFetch действительно не справился
- [ ] Запустил tavily_client.py с правильным режимом
- [ ] Получил и обработал результат
- [ ] Если extract failed — попробовал --depth advanced
