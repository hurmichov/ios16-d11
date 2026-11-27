# VI-BR-PORT: патч под GTX 1660 (6 ГБ)

Патч поверх [edsuuu/VI-BR-PORT](https://github.com/edsuuu/VI-BR-PORT), коммит
`da559920c3f4a11b5c30acb45c7e905370c773a3` (main на 2026-11-27).

Что внутри (подробно: [GTX1660.ru.md](GTX1660.ru.md)):

- `VICTORY_VRAM_TIER`: значения по умолчанию для карт с 6 ГБ видеопамяти;
- `VICTORY_OUTPUT`: размер вывода игры (перенесено из Protonida);
- `VICTORY_FSR`: FSR 1 (EASU + RCAS) в момент вывода кадра; интерфейс поверх мира,
  без увеличения;
- пресеты `Play-GTX1660.cmd`: `perf540`, `test720`, `half`, `native`.

## Как применить (Windows, PowerShell)

```powershell
git clone https://github.com/edsuuu/VI-BR-PORT
cd VI-BR-PORT
git checkout -b gtx1660 da559920c3f4a11b5c30acb45c7e905370c773a3
git am <путь>\0001-gtx1660-vram-fsr1-presets.patch
copy victory.example.toml victory.toml      # укажите game_dir
cargo build --locked --release -p victory
target\release\victory.exe shaders <шейдеры игры>
Play-GTX1660.cmd "D:\...\game_scarlett_master.exe" perf540
```

На GTX 1660 пока не запускалось. Сборка для Windows проходит `cargo check` и `clippy`.
Тесты и `spirv-val` для шейдеров проходят.
