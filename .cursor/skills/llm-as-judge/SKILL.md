# Skill: llm-as-judge

Eval-промпт для автоматической оценки ответов агента: high-end тон, корректность tool-calls, отсутствие галлюцинаций. Используется как сэмплированный (5%) контроль качества с записью в таблицу `evals`.

## Когда использовать

- При создании `src/llm/prompts/tone_judge_prompt.py` (high-end tone eval)
- При создании дополнительных судей (galution-eval, tool-call-eval)
- При деградации метрики «high-end tone» < 75% — для калибровки критериев
- В CI / nightly eval-прогонах на golden dataset

## Что делает

1. Получает на вход: пару `(user_message, agent_response)` + опциональный контекст (`profile`, `tool_results`).
2. Вызывает LLM с критериями оценки (formal register, premium-лексика, no «скидки», экспертность).
3. Просит вернуть JSON: `{score: 0–10, verdict: "pass" | "fail", reasons: [...]}`.
4. Записывает в таблицу `evals` (через `agent-travel-dba`).
5. По агрегации (день/неделя) — даёт метрику high-end tone compliance.

## Контракт (input → output)

```python
def build_tone_judge_messages(
    user_message: str,
    agent_response: str,
    context: dict | None = None,
) -> list[Message]:
    """returns messages for LLM-as-Judge call"""

class JudgeVerdict(BaseModel):
    score: int           # 0–10
    verdict: Literal["pass", "fail"]  # threshold = 7
    reasons: list[str]   # короткие пояснения
    flagged_phrases: list[str]  # напр. ["скидка", "дешёвый"]
```

## Шаблон промпта (high-end tone)

```text
[SYSTEM]
Ты — эксперт по премиальному клиентскому сервису. Оцени ответ AI-консьержа
туристического агентства класса high-end по критериям:

1. Формальный регистр и уважительная лексика (на «вы», без сленга).
2. Premium-словарь: «эксклюзив», «привилегии», «уникальный опыт».
3. ЗАПРЕТ слова «скидка», «дёшево», «горящее предложение».
4. Экспертность: конкретика по турам/направлениям, без воды.
5. Краткость + чёткая структура (не «стена текста»).

Шкала: 0 (грубое нарушение) → 10 (эталон).
Threshold: score ≥ 7 → "pass".

Ответь СТРОГО JSON без обрамления:
{
  "score": int,
  "verdict": "pass" | "fail",
  "reasons": ["..."],
  "flagged_phrases": ["..."]
}

[USER]
USER MESSAGE:
{user_message}

AGENT RESPONSE:
{agent_response}
```

## Правила и инварианты

- **Temperature = 0.0** для судьи (максимальная воспроизводимость оценок)
- **Tools НЕ передаются** (судья не вызывает действия)
- **`max_tokens ≤ 200`** — короткий JSON-ответ
- Сэмплирование: **5%** реальных ответов агента (`spec-observability.md` §4)
- Threshold для `pass`: `score ≥ 7` (калибруется по golden dataset)
- Полный текст user/agent — **маскируй PII** перед отправкой судье (`mask_pii(...)` из `agent-travel-security`)
- Судья — **другая модель** или другой prompt context (избегай self-eval bias); рекомендуется Claude если основной OpenAI и наоборот
- Версионируй prompt (`TONE_JUDGE_V1`) — изменение промпта инвалидирует исторические оценки (помечай в `evals.judge_version`)
- Не использовать judge для **блокировки** ответа в реальном времени — только offline / async-eval
- При `verdict="fail"` — записывай в `evals` для ручного review (триггер калибровки system_prompt)
- Стоимость judge-вызова — отдельный счётчик в `usage` (не смешивать с production cost)

## Метрики

| Метрика | Цель | Источник |
|---|---|---|
| High-end tone compliance | ≥ 75% pass rate | productContext.md, spec-observability §4 |
| Сэмплинг | 5% production traffic | spec-observability §4 |
| Latency judge-вызова | ≤ 3 с (асинхронно) | внутренний бюджет |
| Стоимость judge | ≤ 2% от прод-стоимости | бюджетный лимит |

## Дополнительные судьи (расширения)

| Skill-вариант | Что оценивает |
|---|---|
| `tool-call-judge` | Корректность параметров `search_tours`, наличие обязательных полей |
| `hallucination-judge` | Сравнение цен/отелей в ответе vs `tool_results` (детектор галлюцинаций) |
| `injection-judge` | Признаки prompt injection в ответе (утечка system prompt) |

(Эти варианты — в backlog; создавать по мере необходимости.)

## Используется агентами

- `agent-travel-llm` — **владелец** промптов (`src/llm/prompts/tone_judge_prompt.py`)
- `agent-travel-test` — потребитель в offline-eval pipeline; golden dataset
- `agent-travel-dba` — таблица `evals` (схема: `judge_version`, `score`, `verdict`, `sampled_at`, `session_id`)

## Связанные документы

- `docs/specs/spec-observability.md` §4 (Evals: SLO-таргеты, методология)
- `memory-bank/productContext.md` (high-end тон, запрет «скидок»)
- `docs/governance.md` (R9 — нарушение high-end тона)
- `.cursor/skills/output-validation/SKILL.md` (синхронный layer защиты; judge — асинхронный/eval-уровень; вариант `hallucination-judge` усиливает hallucination-detection из output-validation)

## Статус

Backlog — реализация при разработке `src/llm/prompts/tone_judge_prompt.py` + eval pipeline в `agent-travel-test`.
