# VANTA Launcher — prototype 0.1

Первый прототип лаунчера для Windows.

## Что уже есть
- Тёмный интерфейс VANTA.
- Целевая версия Minecraft Java 1.21.11.
- Установка Fabric Loader через официальный Fabric Installer.
- Загрузка совместимых Fabric API и Sodium из Modrinth API.
- Кнопка «Играть» открывает официальный Minecraft Launcher.
- Кнопка открытия папки `.minecraft`.
- Журнал установки и индикатор прогресса.

## Что нужно
- Windows 10/11 x64.
- Python 3.10+ для сборки.
- Java 21 x64 для запуска Fabric Installer.
- Официальный Minecraft Launcher и лицензия Minecraft Java Edition для игры.

## Сборка EXE на Windows
1. Установи Python 3.10+ и отметь `Add Python to PATH`.
2. Распакуй архив.
3. Запусти `build_windows.bat`.
4. Готовый файл появится в `dist\VANTA-Launcher.exe`.

## Как пользоваться
1. Запусти `VANTA-Launcher.exe`.
2. Нажми «Установить сборку».
3. Дождись окончания загрузки.
4. Нажми «Играть».
5. В официальном Minecraft Launcher выбери профиль Fabric Loader 1.21.11.

## Важно
Это ранний прототип. Кнопка «Играть» пока передаёт запуск официальному Minecraft Launcher — собственная авторизация Microsoft и прямой запуск игры будут отдельным этапом разработки. Лаунчер скачивает моды с Modrinth и Fabric Loader с инфраструктуры FabricMC.

## Автоматическая сборка EXE через GitHub Actions (без Windows на твоём ПК)

В проект добавлен workflow `.github/workflows/build-windows.yml`. Он запускается на виртуальном Windows runner GitHub Actions и собирает настоящий Windows `.exe`.

1. Создай пустой репозиторий на GitHub.
2. Загрузи туда все файлы проекта, включая скрытую папку `.github`.
3. Открой вкладку **Actions** репозитория.
4. Выбери **Build VANTA Launcher (Windows EXE)** и нажми **Run workflow**.
5. После успешного завершения открой запуск workflow и скачай artifact `VANTA-Launcher-Windows-x64`.

Сборка выполняется на Windows runner, поэтому PyInstaller не пытается кросс-компилировать Windows EXE из Linux.

## Автоматическая сборка Windows EXE через GitHub Actions
1. Создай новый пустой репозиторий на GitHub.
2. Загрузи в него содержимое этой папки.
3. Открой вкладку Actions и запусти `Build VANTA Windows EXE` (или сделай push в `main`).
4. После успешного завершения открой запуск workflow и скачай artifact `VANTA-Launcher-Windows`.
