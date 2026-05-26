# Экспорт из Figma (reference)

Код в этой папке — экспорт из макета Yandex Cloud. Использование:

1. **Пути SVG** — подставьте реальные значения `d` из Figma (Copy as SVG / экспорт):
   - блок сервисов: `../assets/svg-pzc9bu2q82.ts`
   - полная страница Frame95: `../assets/svg-gauvwr1sed.ts`
2. **Картинки** — импорты `figma:asset/...` в Vite не работают. Экспортируйте изображения из Figma и замените плейсхолдеры на локальные пути, например:
   ```ts
   import imgShape from '@/assets/shape.png';
   ```
3. **Шрифты** — в макете используются `YS_Display:Black`, `YS_Text:Regular` и т.д. В проекте подключён fallback Onest; при наличии Yandex Sans подключите через `@font-face`.

**Файлы:**
- `FigmaExportFrame3.tsx` — блок «Сервисы, которые решают эту задачу» (карточки, слайдер).
- `FigmaExportFrame95.tsx` — упрощённая структура полной страницы (hero, навигация). Полный экспорт из Figma (все Group, CasesBlock, StartBlock, SafetyBlock, TechBlock, QuestionsBlock, CTA, Footer) можно вставить в этот файл, сохранив импорт `svgPaths` из `../assets/svg-gauvwr1sed` и константы-плейсхолдеры для картинок.
