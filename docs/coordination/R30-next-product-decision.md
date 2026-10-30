# Один следующий outcome после R30

1. Следующий outcome: Ричи сам один раз замечает конкретный факт в свежем кадре и вслух задаёт по нему короткий русский вопрос; это начало осмысленного общения без spoken/manual trigger.
2. Основа: уже принятые R21 camera→same9B FINAL→Piper/Agent playback и R29 движения; нужен узкий opt-in admission в существующем Agent/audio lock на фактическом idle, без нового observer/framework/модели и без fake STT.
3. Цена: одно окно≤35min после R30 (source+review≤15min, exact install+один proof≤15min, rollback≥5min); bounded once-per-arm, без периодической бесконечной генерации/format tuning.
4. Smallest actual proof: один настоящий новый кадр с provenance, обоснованный наблюдаемым содержимым вопрос без ввода STT, полный playback, возврат capture/listening, STOP отменяет pending output; не считать clock-only settle/заготовленную реплику успехом.
5. Fallback: выключить только initiative feature/точно вернуть Agent/helper preimages, сохранить текущие обычный локальный голос+camera+motor/+2dB; во время R30 никаких implementation/inference/control этого outcome не запускать.
