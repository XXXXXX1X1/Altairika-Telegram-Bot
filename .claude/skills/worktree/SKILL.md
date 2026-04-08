---
name: worktree
description: Создание и управление git worktrees для параллельной работы нескольких Claude в одном проекте. Используй когда пользователь хочет параллельную работу, изолированные изменения или эксперимент с откатом.
---

# Git Worktree Manager

Управление изолированными рабочими копиями проекта через git worktree. Позволяет нескольким Claude работать параллельно в одном проекте, не мешая друг другу.

## Когда активировать

- Пользователь говорит: "создай worktree", "работай в отдельной ветке", "сделай это изолированно"
- Пользователь хочет параллельную работу: "параллельно сделай X и Y", "запусти это отдельно"
- Пользователь хочет эксперимент с откатом: "попробуй вот это, но чтобы можно было откатить"
- Пользователь говорит: "смержи worktree", "удали worktree", "покажи worktrees", "список worktrees"

## Операции

### 1. Создать worktree

**Аргумент:** `$ARGUMENTS` = имя worktree (например: `research`, `content`, `experiment`)

```bash
# Убедиться что .claude/worktrees/ в .gitignore
grep -q '.claude/worktrees/' .gitignore 2>/dev/null || echo '.claude/worktrees/' >> .gitignore

# Создать worktree с отдельной веткой
git worktree add .claude/worktrees/$ARGUMENTS -b worktree-$ARGUMENTS
```

После создания сообщи пользователю:
```
Worktree "$ARGUMENTS" создан.
- Папка: .claude/worktrees/$ARGUMENTS/
- Ветка: worktree-$ARGUMENTS
- Все мои действия теперь будут в этой папке.

Когда закончу — скажи "смержи worktree $ARGUMENTS" чтобы перенести изменения в основной проект.
```

**После создания — ПЕРЕКЛЮЧИСЬ на работу в worktree:**
- ВСЕ операции с файлами делай через путь `.claude/worktrees/$ARGUMENTS/`
- Читай файлы: `.claude/worktrees/$ARGUMENTS/path/to/file`
- Пиши файлы: `.claude/worktrees/$ARGUMENTS/path/to/file`
- Запускай скрипты: `cd .claude/worktrees/$ARGUMENTS && python3 execution/...`
- НЕ трогай файлы в корне проекта

### 2. Показать все worktrees

```bash
git worktree list
```

### 3. Смержить worktree

**Аргумент:** `$ARGUMENTS` = имя worktree для мержа

```bash
# 1. Закоммитить незакоммиченные изменения в worktree
cd .claude/worktrees/$ARGUMENTS && git add -A && git status
```

Если есть что коммитить:
```bash
cd .claude/worktrees/$ARGUMENTS && git commit -m "worktree $ARGUMENTS: описание изменений"
```

```bash
# 2. Вернуться в корень и смержить
cd <корень_проекта> && git merge worktree-$ARGUMENTS --no-edit
```

Если мерж-конфликт — сообщи пользователю и помоги разрешить.

После успешного мержа спроси: "Удалить worktree $ARGUMENTS? Изменения уже в основной ветке."

### 4. Удалить worktree

**Аргумент:** `$ARGUMENTS` = имя worktree для удаления

```bash
git worktree remove .claude/worktrees/$ARGUMENTS
git branch -d worktree-$ARGUMENTS
```

## Правила работы в worktree

1. **Все пути** — через `.claude/worktrees/<name>/`, НИКОГДА через корень
2. **Скрипты** — `cd .claude/worktrees/<name> && python3 ...`
3. **Результаты** — в `.claude/worktrees/<name>/tmp/...`
4. **Коммить часто** — маленькие коммиты = чистый мерж
5. **Не трогай корень** — только свой worktree
6. **CLAUDE.md и skills** — читаются из корня проекта (общие для всех)

## Обработка ошибок

| Ошибка | Решение |
|--------|---------|
| `fatal: is not a git repository` | Проект не инициализирован как git-репо. Выполни `git init` |
| `fatal: '$ARGUMENTS' is already checked out` | Worktree с таким именем уже существует. Покажи `git worktree list` |
| `error: branch 'worktree-X' not found` | Ветка уже удалена. Просто удали директорию: `rm -rf .claude/worktrees/X` |
| Мерж-конфликт | Покажи конфликтующие файлы, помоги разрешить, потом `git add` + `git commit` |
