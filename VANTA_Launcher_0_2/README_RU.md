# VANTA Launcher 0.4 — Qt interface

Новая оболочка лаунчера на PySide6 / Qt. Это ранняя функциональная версия.

## Интерфейс
- Главная страница с игровой карточкой и действиями.
- Разделы «Версии», «Моды» и «Настройки».
- Список JAR-модов с включением/выключением через суффикс `.disabled`.
- Адаптивная компоновка, боковая навигация и статус установки.

## Установка
- Minecraft Java Edition 1.21.11.
- Fabric Loader, Fabric API и Sodium устанавливаются через Modrinth/Fabric.
- Для установки требуется Java 21 x64.
- Кнопка «Играть» открывает установленный игровой лаунчер; прямой запуск и авторизация в VANTA пока не реализованы.

## Сборка Windows
GitHub Actions собирает приложение в формате onedir. Скачай artifact `VANTA-Launcher-Windows`, распакуй всю папку и запускай `VANTA-Launcher.exe`. Не перемещай EXE отдельно от соседних файлов.

Локально:
```powershell
python -m pip install -r requirements.txt
pyinstaller --noconfirm --clean --onedir --windowed --name VANTA-Launcher --collect-all PySide6 vanta_launcher_qt.py
```
