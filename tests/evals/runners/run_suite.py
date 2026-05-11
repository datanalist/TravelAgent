from __future__ import annotations

"""CLI runner для User-Behaviour Eval pipeline.

Использование:
    python -m tests.evals.runners.run_suite --help
    python -m tests.evals.runners.run_suite --personas high_end_decisive --scenarios happy_warm_destination
    python -m tests.evals.runners.run_suite --all --max-turns 6
    python -m tests.evals.runners.run_suite --judge-only --input recordings/xxx.jsonl

Режимы:
    simulate (default): генерирует диалог и пишет JSONL + Langfuse trace
    judge-only: прогоняет judges на уже существующем JSONL
    both: simulate + judge (default при --all)
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from uuid import uuid4

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_suite")

_EVALS_DIR = Path(__file__).parent.parent
_PERSONAS_DIR = _EVALS_DIR / "personas"
_SCENARIOS_DIR = _EVALS_DIR / "scenarios"
_RECORDINGS_DIR = _EVALS_DIR / "recordings"
_REPORTS_DIR = _EVALS_DIR / "reports"


# ---------------------------------------------------------------------------
# YAML loaders
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_persona(name: str):
    from tests.evals.simulator.models import Persona, PersonaStyle
    data = _load_yaml(_PERSONAS_DIR / f"{name}.yaml")
    style_raw = data.pop("style", {})
    data["style"] = PersonaStyle(**style_raw)
    # attack_vectors_to_try — не поле Persona, убираем если есть
    data.pop("attack_vectors_to_try", None)
    return Persona(**data)


def _load_scenario(name: str):
    from tests.evals.simulator.models import Scenario, ExpectedOutcome, GroundTruthIntent
    data = _load_yaml(_SCENARIOS_DIR / f"{name}.yaml")
    eo_raw = data.pop("expected_outcome", {})
    gti_raw = data.pop("ground_truth_intents", [])
    data["expected_outcome"] = ExpectedOutcome(**eo_raw)
    data["ground_truth_intents"] = [GroundTruthIntent(**g) for g in gti_raw]
    return Scenario(**data)


def _available_names(directory: Path) -> list[str]:
    return [p.stem for p in directory.glob("*.yaml")]


# ---------------------------------------------------------------------------
# Simulate
# ---------------------------------------------------------------------------

async def _simulate_one(persona_name: str, scenario_name: str, args: argparse.Namespace):
    from src.llm.config import LLMConfig
    from src.llm.connector import LLMConnector
    from tests.evals.simulator.harness import run_conversation
    from tests.evals.tracing.langfuse_client import LangfuseClient

    persona = _load_persona(persona_name)
    scenario = _load_scenario(scenario_name)

    if args.max_turns:
        scenario.max_turns = args.max_turns

    # Передаём attack_vectors из YAML персоны-агрессора в сценарий
    raw_persona_yaml = _load_yaml(_PERSONAS_DIR / f"{persona_name}.yaml")
    if "attack_vectors_to_try" in raw_persona_yaml:
        scenario.attack_vectors_to_try = (
            scenario.attack_vectors_to_try or raw_persona_yaml["attack_vectors_to_try"]
        )

    llm_config = LLMConfig()
    connector = LLMConnector(llm_config)
    langfuse = LangfuseClient()

    client_id = uuid4()
    session_id = uuid4()

    logger.info("Запуск диалога: persona=%s scenario=%s", persona_name, scenario_name)

    record = await run_conversation(
        persona=persona,
        scenario=scenario,
        connector=connector,
        client_id=client_id,
        session_id=session_id,
        langfuse=langfuse,
    )

    logger.info(
        "Диалог завершён: turns=%d completed=%s error=%s",
        len(record.turns), record.completed, record.error,
    )
    return record


async def _simulate(args: argparse.Namespace):
    persona_names = _expand_names(args.personas, _PERSONAS_DIR)
    scenario_names = _expand_names(args.scenarios, _SCENARIOS_DIR)

    records = []
    for p in persona_names:
        for s in scenario_names:
            try:
                rec = await _simulate_one(p, s, args)
                records.append(rec)
            except Exception as exc:
                logger.error("Ошибка прогона %s × %s: %s", p, s, exc)

    return records


def _expand_names(raw: str | None, directory: Path) -> list[str]:
    if raw is None or raw == "all":
        return _available_names(directory)
    return [n.strip() for n in raw.split(",") if n.strip()]


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

async def _judge_records(records, args: argparse.Namespace):
    from src.llm.config import LLMConfig
    from src.llm.connector import LLMConnector
    from tests.evals.judges.tone_judge import ToneJudge
    from tests.evals.judges.injection_judge import InjectionJudge
    from tests.evals.judges.hallucination_judge import HallucinationJudge
    from tests.evals.judges.pii_leak_judge import PIILeakJudge
    from tests.evals.tracing.langfuse_client import LangfuseClient

    llm_config = LLMConfig()
    connector = LLMConnector(llm_config)
    langfuse = LangfuseClient()

    judges = [
        ToneJudge(connector),
        InjectionJudge(connector),
        HallucinationJudge(connector),
        PIILeakJudge(),
    ]

    all_results = []
    for record in records:
        conv_results = {"conversation": f"{record.persona_name}__{record.scenario_name}", "judges": {}}
        for judge in judges:
            try:
                verdicts = await judge.evaluate(record)
                conv_results["judges"][judge.name] = [v.model_dump() for v in verdicts]

                # Пишем score в Langfuse
                for v in verdicts:
                    if "_aggregate" in v.judge_name:
                        # trace_id мы не сохраняем в record — скипаем если нет Langfuse
                        pass
            except Exception as exc:
                logger.error("Judge %s ошибка: %s", judge.name, exc)
                conv_results["judges"][judge.name] = [{"error": str(exc)}]

        all_results.append(conv_results)

    return all_results


async def _judge_only(args: argparse.Namespace):
    """Загружает JSONL и прогоняет judges на нём."""
    from tests.evals.simulator.models import ConversationRecord, Turn

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Файл не найден: %s", input_path)
        sys.exit(1)

    turns = []
    with input_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                turns.append(Turn.model_validate_json(line))

    if not turns:
        logger.error("JSONL пустой: %s", input_path)
        sys.exit(1)

    # Восстанавливаем ConversationRecord из имени файла
    stem = input_path.stem  # timestamp__commit__persona__scenario
    parts = stem.split("__")
    persona_name = parts[2] if len(parts) > 2 else "unknown"
    scenario_name = parts[3] if len(parts) > 3 else "unknown"

    record = ConversationRecord(
        persona_name=persona_name,
        scenario_name=scenario_name,
        persona_version=1,
        scenario_version=1,
        turns=turns,
    )
    return await _judge_records([record], args)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _print_report(results: list[dict], report_path: Path | None = None):
    lines = ["# User-Behaviour Eval Report\n"]

    for conv in results:
        lines.append(f"\n## {conv['conversation']}\n")
        for judge_name, verdicts in conv["judges"].items():
            if not verdicts:
                continue
            # Показываем только aggregate
            agg = next((v for v in verdicts if "_aggregate" in v.get("judge_name", "")), None)
            if agg:
                icon = "✅" if agg["verdict"] == "pass" else "❌"
                lines.append(f"- **{judge_name}**: {icon} score={agg['score']:.2f} — {'; '.join(agg['reasons'])}")

    report = "\n".join(lines)
    print(report)

    if report_path:
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        # Также JSON
        json_path = report_path.with_suffix(".json")
        json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Отчёт сохранён: %s", report_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="User-Behaviour Eval Suite для TravelAgent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--personas",
        default=None,
        help="Список персон через запятую или 'all'. По умолчанию: all",
    )
    parser.add_argument(
        "--scenarios",
        default=None,
        help="Список сценариев через запятую или 'all'. По умолчанию: all",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="Переопределить max_turns из scenario.yaml",
    )
    parser.add_argument(
        "--judge-only",
        action="store_true",
        help="Только прогнать judges на существующем JSONL (не симулировать)",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Путь к JSONL-файлу для --judge-only режима",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Путь к файлу отчёта (.md). JSON создаётся рядом автоматически.",
    )
    return parser.parse_args()


async def main():
    args = _parse_args()

    if args.judge_only:
        if not args.input:
            logger.error("--judge-only требует --input <path.jsonl>")
            sys.exit(1)
        results = await _judge_only(args)
    else:
        records = await _simulate(args)
        if not records:
            logger.error("Ни одного прогона не завершилось успешно")
            sys.exit(1)
        results = await _judge_records(records, args)

    report_path = Path(args.report) if args.report else None
    _print_report(results, report_path)


if __name__ == "__main__":
    asyncio.run(main())
