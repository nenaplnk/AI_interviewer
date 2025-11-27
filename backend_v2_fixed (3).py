"""
AI Technical Interviewer v2 - Multi-Agent System
3 агента: HR Manager, Tech Lead, Senior Developer
С функцией адаптации задач, системой штрафов и финальным совещанием
+ Новые метрики: Context Switching, Code Readability, Conflict Behavior
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import sys
import io
import re
import sqlite3
from datetime import datetime
from datetime import timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from functools import lru_cache
from database import (
    init_database, seed_coding_tasks, seed_theory_questions,
    get_tasks_by_level, get_theory_by_level, get_adaptive_task, DB_PATH
)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
API_KEY = "your api key"
API_BASE_URL = "your api base url"
MODEL_NAME = "model name"

# ЗАГРУЗКА КОНФИГУРАЦИИ ИЗ JSON ФАЙЛА
# Здесь мы загружаем все промты и параметры из внешнего файла
def load_config():
    config_path = "prompts_config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки конфигурации: {e}")
        raise

CONFIG = load_config()

@lru_cache(maxsize=100)
def cached_adr_analysis(answer_hash: str, question_hash: str) -> Dict:
    """Кэширование анализа ADR для одинаковых ответов"""
    # Реализация будет в calculate_adr_with_llm
    pass

# Метрика для оценки воды
#========================
def calculate_adr_with_llm(answer: str, question: str, expected_topics: List[str]) -> Dict[str, Any]:
    """
    Оценивает глубину ответа с помощью LLM вместо жесткого списка терминов
    Возвращает: {'adr_score': float (0.0-1.0), 'feedback': str, 'issues': List[str]}
    """
    if not answer or len(answer.strip()) < 10:
        return {
            "adr_score": 0.0,
            "feedback": "Ответ слишком короткий или отсутствует",
            "issues": ["слишком короткий ответ"]
        }
    
    # Промпт для оценки глубины ответа
    prompt = CONFIG["prompts"]["theory"]["adr_analysis"].format(
        question=question,
        expected_topics=", ".join(expected_topics),
        answer=answer
    )
    
    system_prompt = CONFIG["prompts"]["theory"]["adr_system"]
    
    try:
        response = call_llm_simple(prompt, system_prompt)
        # Очищаем ответ от возможного мусора
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            result = json.loads(json_str)
            # Нормализуем оценку к шкале 0-1
            adr_score = min(10, max(0, result.get("score", 5))) / 10.0
            return {
                "adr_score": adr_score,
                "feedback": result.get("feedback", "Хороший ответ"),
                "issues": result.get("issues", []),
                "improvement_suggestions": result.get("improvement_suggestions", [])
            }
        # Если не удалось распарсить JSON
        return {
            "adr_score": 0.5,
            "feedback": "Не удалось проанализировать глубину ответа",
            "issues": ["ошибка анализа"],
            "improvement_suggestions": ["Попробуйте дать более развернутый ответ"]
        }
    except Exception as e:
        print(f"Ошибка при расчете ADR через LLM: {e}")
        return {
            "adr_score": 0.5,
            "feedback": f"Ошибка анализа: {e}",
            "issues": ["техническая ошибка"],
            "improvement_suggestions": ["Повторите попытку позже"]
        }

# ============================================
# НОВАЯ МЕТРИКА: Context Switching Penalty
# ============================================
def analyze_context_switching(
    current_message: str, 
    chat_history: List[Dict], 
    current_context: str,
    level: str
) -> Dict[str, Any]:
    """
    Анализирует логичность ответа и попытки смены темы.
    LLM выявляет:
    - Нелогичные ответы, не относящиеся к вопросу
    - Попытки уйти от темы
    - Неконструктивные отвлечения
    Возвращает: {'is_violation': bool, 'penalty_score': float, 'reason': str, 'severity': str}
    """
    if not current_message or len(current_message.strip()) < 5:
        return {
            "is_violation": False,
            "penalty_score": 0.0,
            "reason": "Сообщение слишком короткое для анализа",
            "severity": "none"
        }
    
    # Собираем последние 5 сообщений для контекста
    recent_history = chat_history[-5:] if len(chat_history) >= 5 else chat_history
    history_text = "\n".join([
        f"{'Кандидат' if msg['role'] == 'user' else 'Интервьюер'}: {msg['content'][:200]}"
        for msg in recent_history
    ])
    
    prompt = CONFIG["prompts"]["context_switching"]["analysis"].format(
        current_context=current_context,
        level=level,
        history_text=history_text,
        current_message=current_message
    )
    
    system_prompt = CONFIG["prompts"]["context_switching"]["system"]
    
    try:
        response = call_llm_simple(prompt, system_prompt)
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(0))
            is_violation = result.get("is_violation", False)
            severity = result.get("severity", "none")
            # Рассчитываем штраф в зависимости от severity и уровня
            penalty_multipliers = {
                "none": 0.0,
                "minor": 0.5,
                "moderate": 1.0,
                "severe": 1.5
            }
            base_penalty = CONFIG["penalty_weights"].get(level, CONFIG["penalty_weights"]["middle"]).get("context_switching", 2)
            penalty_score = base_penalty * penalty_multipliers.get(severity, 0.0)
            return {
                "is_violation": is_violation,
                "penalty_score": penalty_score,
                "reason": result.get("reason", "Анализ завершен"),
                "severity": severity,
                "specific_issue": result.get("specific_issue", "")
            }
        return {
            "is_violation": False,
            "penalty_score": 0.0,
            "reason": "Не удалось проанализировать",
            "severity": "none"
        }
    except Exception as e:
        print(f"Ошибка при анализе context switching: {e}")
        return {
            "is_violation": False,
            "penalty_score": 0.0,
            "reason": f"Ошибка анализа: {e}",
            "severity": "none"
        }

# ============================================
# НОВАЯ МЕТРИКА: Code Readability Penalty (PEP8)
# ============================================
def analyze_code_readability(code: str, level: str) -> Dict[str, Any]:
    """
    Проверяет код на соответствие PEP8 и читаемость.
    Штрафы возрастают в зависимости от уровня пользователя:
    - Junior: мягкие требования
    - Middle: средние требования  
    - Senior: строгие требования
    Возвращает: {'violations': List, 'penalty_score': float, 'feedback': str, 'readability_score': float}
    """
    if not code or len(code.strip()) < 10:
        return {
            "violations": [],
            "penalty_score": 0.0,
            "feedback": "Код отсутствует или слишком короткий",
            "readability_score": 1.0
        }
    
    # Базовые проверки PEP8 без внешних библиотек
    violations = []
    lines = code.split('\n')
    
    for i, line in enumerate(lines, 1):
        # 1. Длина строки > 79 символов (PEP8 E501)
        if len(line) > 79:
            violations.append({
                "line": i,
                "type": "line_too_long",
                "message": f"Строка {i}: длина {len(line)} символов (максимум 79)",
                "severity": "minor"
            })
        # 2. Trailing whitespace (PEP8 W291)
        if line.rstrip() != line and line.strip():
            violations.append({
                "line": i,
                "type": "trailing_whitespace",
                "message": f"Строка {i}: лишние пробелы в конце",
                "severity": "minor"
            })
        # 3. Tabs вместо пробелов (PEP8 W191)
        if '\t' in line:
            violations.append({
                "line": i,
                "type": "tabs_used",
                "message": f"Строка {i}: использованы табы вместо пробелов",
                "severity": "minor"
            })
        # 4. Множественные пустые строки (PEP8 E303)
        if i > 1 and not line.strip() and not lines[i-2].strip() if i > 1 else False:
            # Проверяем, нет ли уже такого нарушения для предыдущей строки
            if not any(v["line"] == i-1 and v["type"] == "multiple_blank_lines" for v in violations):
                violations.append({
                    "line": i,
                    "type": "multiple_blank_lines",
                    "message": f"Строка {i}: множественные пустые строки",
                    "severity": "minor"
                })
    
    # 5. Проверки через regex
    # Отсутствие пробелов вокруг операторов (PEP8 E225)
    operator_pattern = r'[a-zA-Z0-9_][\+\-\*\/\=\<\>][a-zA-Z0-9_]'
    for i, line in enumerate(lines, 1):
        # Игнорируем строки с комментариями и строковыми литералами
        if '#' in line:
            line_to_check = line[:line.index('#')]
        else:
            line_to_check = line
        if re.search(operator_pattern, line_to_check):
            # Исключаем случаи внутри строк
            if not ('"' in line_to_check or "'" in line_to_check):
                violations.append({
                    "line": i,
                    "type": "missing_whitespace_around_operator",
                    "message": f"Строка {i}: отсутствуют пробелы вокруг оператора",
                    "severity": "minor"
                })
    
    # 6. Naming conventions (упрощенная проверка)
    # snake_case для функций и переменных
    camel_case_pattern = r'\b[a-z]+[A-Z][a-zA-Z]*\s*='
    for i, line in enumerate(lines, 1):
        if re.search(camel_case_pattern, line) and 'class' not in line:
            violations.append({
                "line": i,
                "type": "naming_convention",
                "message": f"Строка {i}: используется camelCase вместо snake_case",
                "severity": "moderate"
            })
    
    # 7. Отсутствие docstring для функций (для middle/senior)
    if level in ["middle", "senior"]:
        func_pattern = r'def\s+\w+\s*\([^)]*\)\s*:'
        for i, line in enumerate(lines, 1):
            if re.match(func_pattern, line.strip()):
                # Проверяем следующую строку на наличие docstring
                if i < len(lines):
                    next_line = lines[i].strip()
                    if not (next_line.startswith('"""') or next_line.startswith("'''")):
                        violations.append({
                            "line": i,
                            "type": "missing_docstring",
                            "message": f"Строка {i}: функция без docstring",
                            "severity": "moderate" if level == "middle" else "severe"
                        })
    
    # Расчет штрафа в зависимости от уровня
    severity_weights = {
        "minor": {"junior": 0.2, "middle": 0.5, "senior": 1.0},
        "moderate": {"junior": 0.5, "middle": 1.0, "senior": 2.0},
        "severe": {"junior": 1.0, "middle": 2.0, "senior": 3.0}
    }
    total_penalty = 0.0
    for v in violations:
        severity = v.get("severity", "minor")
        weight = severity_weights.get(severity, {}).get(level, 0.5)
        total_penalty += weight
    
    # Ограничиваем максимальный штраф
    base_penalty = CONFIG["penalty_weights"].get(level, CONFIG["penalty_weights"]["middle"]).get("poor_code_readability", 3)
    max_penalty = base_penalty * 2
    total_penalty = min(total_penalty, max_penalty)
    
    # Рассчитываем readability score (0-1)
    # Чем больше нарушений, тем ниже score
    violations_per_line = len(violations) / max(len(lines), 1)
    readability_score = max(0.0, 1.0 - violations_per_line * 0.5)
    
    # Формируем feedback
    if not violations:
        feedback = "Отличный код! Соответствует PEP8."
    elif len(violations) <= 3:
        feedback = f"Код в целом хорош, но есть {len(violations)} небольших замечания по стилю."
    elif len(violations) <= 7:
        feedback = f"Найдено {len(violations)} нарушений PEP8. Рекомендуется улучшить читаемость кода."
    else:
        feedback = f"Много нарушений стиля ({len(violations)}). Для {level} уровня это недопустимо."
    
    return {
        "violations": violations,
        "penalty_score": round(total_penalty, 2),
        "feedback": feedback,
        "readability_score": round(readability_score, 2),
        "violations_count": len(violations)
    }

# ============================================
# НОВАЯ МЕТРИКА: Conflict Behavior Penalty
# ============================================
def analyze_conflict_behavior(
    message: str, 
    chat_history: List[Dict],
    level: str
) -> Dict[str, Any]:
    """
    Выявляет деструктивное поведение в конфликтных ситуациях.
    LLM определяет:
    - Грубость, агрессию
    - Неуважение к интервьюеру
    - Нарушение этических норм
    - Манипулятивное поведение
    Возвращает: {'is_violation': bool, 'penalty_score': float, 'behavior_type': str, 'reason': str}
    """
    if not message or len(message.strip()) < 5:
        return {
            "is_violation": False,
            "penalty_score": 0.0,
            "behavior_type": "none",
            "reason": "Сообщение слишком короткое"
        }
    
    # Собираем контекст последних сообщений
    recent_history = chat_history[-5:] if len(chat_history) >= 5 else chat_history
    history_text = "\n".join([
        f"{'Кандидат' if msg['role'] == 'user' else 'Интервьюер'}: {msg['content'][:150]}"
        for msg in recent_history
    ])
    
    prompt = CONFIG["prompts"]["conflict_behavior"]["analysis"].format(
        history_text=history_text,
        message=message
    )
    
    system_prompt = CONFIG["prompts"]["conflict_behavior"]["system"]
    
    try:
        response = call_llm_simple(prompt, system_prompt)
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(0))
            is_violation = result.get("is_violation", False)
            severity = result.get("severity", "none")
            behavior_type = result.get("behavior_type", "none")
            # Штрафы за разные типы нарушений
            severity_penalties = {
                "none": 0.0,
                "minor": 3.0,      # Небольшое замечание
                "moderate": 7.0,   # Серьезное замечание
                "severe": 15.0,    # Грубое нарушение
                "critical": 25.0   # Критическое нарушение (дисквалификация)
            }
            # Дополнительный множитель по уровню (senior должен вести себя профессиональнее)
            level_multipliers = {
                "junior": 0.8,
                "middle": 1.0,
                "senior": 1.3
            }
            base_penalty = severity_penalties.get(severity, 0.0)
            multiplier = level_multipliers.get(level, 1.0)
            penalty_score = base_penalty * multiplier
            return {
                "is_violation": is_violation,
                "penalty_score": round(penalty_score, 2),
                "behavior_type": behavior_type,
                "severity": severity,
                "reason": result.get("reason", "Анализ завершен"),
                "specific_quote": result.get("specific_quote", "")
            }
        return {
            "is_violation": False,
            "penalty_score": 0.0,
            "behavior_type": "none",
            "severity": "none",
            "reason": "Не удалось проанализировать"
        }
    except Exception as e:
        print(f"Ошибка при анализе conflict behavior: {e}")
        return {
            "is_violation": False,
            "penalty_score": 0.0,
            "behavior_type": "none",
            "severity": "none",
            "reason": f"Ошибка анализа: {e}"
        }

def check_feedback_response_time(session: 'InterviewSession') -> Optional['Penalty']:
    """
    Проверяет, не превышено ли время ответа на фидбек
    Возвращает штраф если нужно, иначе None
    """
    if not session.last_feedback_time or session.feedback_response_penalty_applied:
        return None
    
    # Устанавливаем разные лимиты для теории и кода
    if session.last_feedback_type == "theory":
        # Теория: строгие лимиты (в минутах)
        time_limits = {
            "junior": 3,   # 3 минуты для junior
            "middle": 2,   # 2 минуты для middle  
            "senior": 1.5  # 1.5 минуты для senior
        }
    else:
        # Код: мягкие лимиты (в минутах)
        time_limits = {
            "junior": 15,
            "middle": 10, 
            "senior": 8
        }
    
    # Получаем лимит для текущего уровня
    time_limit_minutes = time_limits.get(session.level, 5)
    current_time = datetime.now()
    time_elapsed = (current_time - session.last_feedback_time).total_seconds() / 60
    
    # Проверяем превышение лимита
    if time_elapsed > time_limit_minutes:
        # Штраф только для теоретической части!
        if session.last_feedback_type == "theory":
            penalty_points = CONFIG["penalty_weights"][session.level]["slow_feedback_response"]
            penalty = Penalty(
                type="timeout",
                points=penalty_points,
                reason=f"Превышено время ответа на фидбек в теории ({time_elapsed:.1f} мин > {time_limit_minutes} мин)"
            )
            session.feedback_response_penalty_applied = True
            return penalty
    return None

def calculate_learning_agility(previous_answer: str, new_answer: str, feedback: str) -> Dict[str, Any]:
    """
    Рассчитывает способность кандидата учиться на фидбеке
    Сравнивает предыдущий ответ, новый ответ и полученный фидбек
    Возвращает: {'score': float (0.0-1.0), 'improvement_areas': List[str], 'feedback': str}
    """
    if not previous_answer or not feedback or not new_answer:
        return {
            "score": 0.0,
            "improved_areas": [],
            "still_needs_improvement": [],
            "feedback": "Недостаточно данных для анализа обучения"
        }
    
    # Промпт для анализа улучшения
    prompt = CONFIG["prompts"]["learning_agility"]["analysis"].format(
        previous_answer=previous_answer,
        feedback=feedback,
        new_answer=new_answer
    )
    
    system_prompt = CONFIG["prompts"]["learning_agility"]["system"]
    
    try:
        response = call_llm_simple(prompt, system_prompt)
        # Очищаем ответ от возможного мусора
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            result = json.loads(json_str)
            # Нормализуем оценку к шкале 0-1
            learning_score = min(10, max(0, result.get("score", 5))) / 10.0
            return {
                "score": learning_score,
                "improved_areas": result.get("improved_areas", []),
                "still_needs_improvement": result.get("still_needs_improvement", []),
                "feedback": result.get("feedback", "Хорошее улучшение")
            }
        # Если не удалось распарсить JSON
        return {
            "score": 0.5,
            "improved_areas": ["небольшие улучшения"],
            "still_needs_improvement": ["требуется больше практики"],
            "feedback": "Умеренное улучшение после фидбека"
        }
    except Exception as e:
        print(f"Ошибка при расчете Learning Agility: {e}")
        return {
            "score": 0.0,
            "improved_areas": [],
            "still_needs_improvement": ["техническая ошибка анализа"],
            "feedback": f"Ошибка анализа: {e}"
        }

def is_clarification_question_llm(message: str, current_context: str) -> Dict[str, Any]:
    """
    Использует LLM для определения, является ли сообщение уточняющим вопросом
    current_context: информация о текущей задаче/вопросе для контекста
    """
    if not message.strip():
        return {"is_clarification": False, "confidence": 0.0, "reason": "Пустое сообщение"}
    
    prompt = CONFIG["prompts"]["clarification"]["analysis"].format(
        current_context=current_context,
        message=message
    )
    
    system_prompt = CONFIG["prompts"]["clarification"]["system"]
    
    try:
        response = call_llm_simple(prompt, system_prompt)
        # Очищаем ответ от возможного мусора
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            result = json.loads(json_str)
            # Валидация результата
            is_clarification = bool(result.get("is_clarification", False))
            confidence = float(result.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))  # Ограничение от 0 до 1
            return {
                "is_clarification": is_clarification,
                "confidence": confidence,
                "reason": result.get("reason", "Анализ завершен"),
                "suggested_response": result.get("suggested_response", "") if is_clarification else ""
            }
        # Если не удалось распарсить JSON
        return {
            "is_clarification": False,
            "confidence": 0.5,
            "reason": "Не удалось проанализировать сообщение",
            "suggested_response": ""
        }
    except Exception as e:
        print(f"Ошибка при анализе уточняющего вопроса: {e}")
        return {
            "is_clarification": False,
            "confidence": 0.0,
            "reason": f"Ошибка анализа: {e}",
            "suggested_response": ""
        }

# ТИПЫ АГЕНТОВ
class AgentRole(str, Enum):
    HR_MANAGER = "hr_manager"
    TECH_LEAD = "tech_lead"
    SENIOR_DEV = "senior_dev"

@dataclass
class Agent:
    role: AgentRole
    name: str
    title: str
    personality: str
    focus_areas: List[str]

# Здесь мы загружаем агентов из JSON конфигурации
AGENTS = {
    AgentRole.HR_MANAGER: Agent(
        role=AgentRole.HR_MANAGER,
        name=CONFIG["agents"]["hr_manager"]["name"],
        title=CONFIG["agents"]["hr_manager"]["title"],
        personality=CONFIG["agents"]["hr_manager"]["personality"],
        focus_areas=CONFIG["agents"]["hr_manager"]["focus_areas"]
    ),
    AgentRole.TECH_LEAD: Agent(
        role=AgentRole.TECH_LEAD,
        name=CONFIG["agents"]["tech_lead"]["name"],
        title=CONFIG["agents"]["tech_lead"]["title"],
        personality=CONFIG["agents"]["tech_lead"]["personality"],
        focus_areas=CONFIG["agents"]["tech_lead"]["focus_areas"]
    ),
    AgentRole.SENIOR_DEV: Agent(
        role=AgentRole.SENIOR_DEV,
        name=CONFIG["agents"]["senior_dev"]["name"],
        title=CONFIG["agents"]["senior_dev"]["title"],
        personality=CONFIG["agents"]["senior_dev"]["personality"],
        focus_areas=CONFIG["agents"]["senior_dev"]["focus_areas"]
    ),
}

# СИСТЕМА ШТРАФОВ (ОБНОВЛЕНА)
@dataclass
class Penalty:
    type: str
    points: float
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

# Здесь мы загружаем типы штрафов из JSON конфигурации
PENALTY_TYPES = CONFIG["penalty_types"]

# СОСТОЯНИЕ СЕССИИ (ОБНОВЛЕНО)
@dataclass
class InterviewSession:
    id: int = None
    level: str = None
    current_agent: AgentRole = AgentRole.HR_MANAGER
    phase: str = "intro" 
    # Задачи и вопросы
    coding_tasks: List[Dict] = field(default_factory=list)
    theory_questions: List[Dict] = field(default_factory=list)
    current_task_idx: int = 0
    current_theory_idx: int = 0
    used_task_ids: List[int] = field(default_factory=list)
    # Результаты
    coding_scores: Dict[int, float] = field(default_factory=dict)
    theory_scores: Dict[int, float] = field(default_factory=dict)
    attempts: Dict[str, int] = field(default_factory=dict)
    # Штрафы и оценки агентов
    penalties: List[Penalty] = field(default_factory=list)
    agent_scores: Dict[str, float] = field(default_factory=dict)
    agent_notes: Dict[str, List[str]] = field(default_factory=dict)
    agent_feedback: Dict[str, str] = field(default_factory=dict)
    # Время
    start_time: datetime = None
    phase_start_time: datetime = None
    # История чата
    chat_history: List[Dict] = field(default_factory=list)
    # ADR анализа
    adr_scores: Dict[int, float] = field(default_factory=dict)
    # Отслеживание времени реакции
    last_feedback_time: Optional[datetime] = None
    last_feedback_type: Optional[str] = None
    feedback_response_deadline: Optional[datetime] = None
    feedback_response_penalty_applied: bool = False
    # Learning Agility
    previous_answers: Dict[int, str] = field(default_factory=dict)
    feedback_received: Dict[int, str] = field(default_factory=dict)
    learning_agility_scores: Dict[int, float] = field(default_factory=dict)
    # Proactive Clarification
    clarification_requests: Dict[str, List[Dict]] = field(default_factory=dict)
    clarification_bonuses: Dict[str, float] = field(default_factory=dict)
    clarification_analysis_history: List[Dict] = field(default_factory=list)
    # НОВЫЕ ПОЛЯ ДЛЯ НОВЫХ МЕТРИК
    context_switching_violations: List[Dict] = field(default_factory=list)   # История нарушений context switching
    code_readability_scores: Dict[int, Dict] = field(default_factory=dict)   # task_id: {score, violations}
    conflict_behavior_violations: List[Dict] = field(default_factory=list)   # История конфликтного поведения
    anticheat_violations: List[Dict] = field(default_factory=list)           # Античит нарушения

session = InterviewSession()

# FUNCTION CALLING TOOLS
# Здесь мы загружаем инструменты для function calling из JSON конфигурации
TOOLS = CONFIG["tools"]

# LLM CLIENT
client = None
if API_KEY and API_BASE_URL and OPENAI_AVAILABLE:
    try:
        client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL)
        print(f" LLM подключен: {MODEL_NAME}")
    except Exception as e:
        print(f" Ошибка LLM: {e}")

def clean_response(text: str) -> str:
    """Эффективно очищает ответ от рассуждений и мета-тегов с контролем длины"""
    # 1. Агрессивное удаление всех возможных тегов рассуждений
    patterns = [
        r'<think\b[^<]*(?:(?!<\/think>)<[^<]*)*<\/think\s*>',
        r'<thinking\b[^<]*(?:(?!<\/thinking>)<[^<]*)*<\/thinking\s*>',
        r'<internal\b[^<]*(?:(?!<\/internal>)<[^<]*)*<\/internal\s*>',
        r'<reasoning\b[^<]*(?:(?!<\/reasoning>)<[^<]*)*<\/reasoning\s*>',
        r'<!--.*?-->',
        r'\{thinking:.*?\}',
        r'\[thinking:.*?\]',
        r'\(thinking:.*?\)',
        r'\/\/ thinking:',
        r'# thinking:',
    ]
    
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 2. Удаление преамбул и указаний на рассуждения
    preambles = [
        r'^(?:Хорошо|Ладно|Окей|Отлично|Понятно|Ясно|Хм|Итак|Так|Ну что ж|Да|Нет),?\s*[^\n]*\n\s*',
        r'^(?:Давай|Надо|Стоит|Мне нужно|Я должен|Я хочу|Я могу|Я попробую|Я думаю|По-моему|Возможно|Наверное|Кажется|Предположу|Рассмотрю|Проанализирую|Проверю|Убедюсь|Уточню|Подумаю|Подожду|Попробую|Попытаюсь).*[.!?]\s*',
        r'^\*[^*]+\*\s*',  # Удаление действий в *звездачках*
        r'^\[[^\]]+\]\s*',  # Удаление действий в [скобках]
        r'^\([^)]+\)\s*',   # Удаление действий в (скобках)
        r'^Пользователь спрашивает о.*\n',
        r'^Текущий запрос:.*\n',
        r'^Я интервьюер, и моя задача.*\n',
        r'^Сначала я.*\n',
        r'^Затем я.*\n',
        r'^В итоге я.*\n',
        r'^Ответ на это.*\n',
        r'^Я решил.*\n',
        r'^Мой ответ будет таким:.*\n',
    ]
    
    for pattern in preambles:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # 3. Принудительное ограничение на 3 предложения
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if len(sentences) > 3:
        text = ' '.join(sentences[:3])
        # Добавляем многоточие, если обрезали текст
        if not text.endswith(('...', '…', '.', '!', '?')):
            text += '…'
    
    # 4. Удаление оставшихся тегов HTML/XML
    text = re.sub(r'<[^>]+>', '', text)
    
    # 5. Удаление множественных пустых строк
    text = re.sub(r'\n\s*\n', '\n', text)
    
    return text.strip()

def get_agent_system_prompt(agent: Agent, phase: str) -> str:
    """Системный промпт для агента"""
    # Здесь мы формируем системный промт из шаблона в JSON конфигурации
    return CONFIG["prompts"]["system"]["agent_system"].format(
        agent_name=agent.name,
        agent_title=agent.title,
        agent_personality=agent.personality,
        agent_focus_areas=", ".join(agent.focus_areas),
        phase=phase,
        level=session.level
    )

def call_llm_with_tools(messages: List[Dict], agent: Agent) -> Dict:
    """Вызов LLM с function calling и защитой от режима thinking"""
    if not client:
        return {"content": "LLM не доступен", "tool_calls": []}
    
    system_prompt = get_agent_system_prompt(agent, session.phase)
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    
    max_attempts = 2  # Максимум попыток получения правильного формата
    for attempt in range(max_attempts):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=full_messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=2000,
                temperature=0.7
            )
            message = response.choices[0].message
            content = clean_response(message.content or "")
            tool_calls = message.tool_calls or []
            
            # Проверка на наличие запрещенных паттернов после очистки
            forbidden_patterns = [
                r'<think', r'<internal', r'<reason', r'<!--', r'{thinking', 
                r'\[thinking', r'\(thinking', r'\/\/ thinking', r'# thinking',
                r'мое рассуждение', r'я подумаю', r'я решил', r'мой ответ будет',
                r'я интервьюер', r'моя задача', r'я должен спросить'
            ]
            
            found_forbidden = any(re.search(pattern, content, re.IGNORECASE) for pattern in forbidden_patterns)
            
            # Если найдены запрещенные паттерны и это не последняя попытка
            if found_forbidden and attempt < max_attempts - 1:
                # Добавляем сообщение с просьбой переформулировать ответ
                correction_message = {
                    "role": "system",
                    "content": "ВНИМАНИЕ: В твоем предыдущем ответе были обнаружены мета-рассуждения или внутренние мысли. "
                    "ПОМНИ: Ты должен общаться с кандидатом ТОЛЬКО прямой речью без каких-либо тегов, комментариев о "
                    "своих мыслях или процессе рассуждений. Твой ответ должен содержать МАКСИМУМ 3 предложения. "
                    "Переформулируй ответ без нарушения этих правил."
                }
                full_messages.append({"role": "assistant", "content": content})
                full_messages.append(correction_message)
                continue
                
            return {
                "content": content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "function": tc.function.name,
                        "arguments": json.loads(tc.function.arguments)
                    }
                    for tc in tool_calls
                ]
            }
            
        except Exception as e:
            print(f"LLM error: {e}")
            return {"content": f"Ошибка: {e}", "tool_calls": []}
    
    # Если все попытки исчерпаны, возвращаем очищенный контент
    return {
        "content": content,
        "tool_calls": [
            {
                "id": tc.id,
                "function": tc.function.name,
                "arguments": json.loads(tc.function.arguments)
            }
            for tc in tool_calls
        ]
    }

def call_llm_simple(prompt: str, system: str = None) -> str:
    """Простой вызов LLM без tools"""
    if not client:
        return "LLM не доступен"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            max_tokens=300,
            temperature=0.7
        )
        return clean_response(response.choices[0].message.content or "")
    except Exception as e:
        return f"Ошибка: {e}"

# TOOL HANDLERS
def handle_tool_call(tool_name: str, args: Dict) -> Dict:
    """Обработка вызова инструмента"""
    if tool_name == "get_next_task":
        adjustment = args.get("difficulty_adjustment", "same")
        current_score = sum(session.coding_scores.values()) / max(len(session.coding_scores), 1) if session.coding_scores else 0.5
        if adjustment == "easier":
            current_score = max(0, current_score - 0.3)
        elif adjustment == "harder":
            current_score = min(1, current_score + 0.3)
        task = get_adaptive_task(session.level, current_score, session.used_task_ids)
        if task:
            session.used_task_ids.append(task['id'])
            session.coding_tasks.append(task)
            return {"success": True, "task": task}
        return {"success": False, "error": "Нет доступных задач"}
    elif tool_name == "get_theory_question":
        questions = get_theory_by_level(session.level)
        if session.current_theory_idx < len(questions):
            q = questions[session.current_theory_idx]
            session.theory_questions.append(q)
            return {"success": True, "question": q}
        return {"success": False, "error": "Нет доступных вопросов"}
    elif tool_name == "evaluate_theory_answer":
        score = args.get("score", 5) / 10.0
        if session.theory_questions:
            q_id = session.theory_questions[-1]['id']
            session.theory_scores[q_id] = score
            session.current_theory_idx += 1
        return {"success": True, "score": score}
    elif tool_name == "add_penalty":
        penalty_type = args.get("type")
        # Используем веса по уровню если доступны
        if session.level and penalty_type in CONFIG["penalty_weights"].get(session.level, {}):
            points = CONFIG["penalty_weights"][session.level][penalty_type]
        else:
            points = CONFIG["penalty_types"].get(penalty_type, 5)
        penalty = Penalty(type=penalty_type, points=points, reason=args.get("reason", ""))
        session.penalties.append(penalty)
        return {"success": True, "penalty": asdict(penalty)}
    elif tool_name == "add_agent_note":
        agent_key = session.current_agent.value
        if agent_key not in session.agent_notes:
            session.agent_notes[agent_key] = []
        session.agent_notes[agent_key].append({
            "note": args.get("note"),
            "sentiment": args.get("sentiment", "neutral")
        })
        return {"success": True}
    elif tool_name == "switch_agent":
        new_agent = AgentRole(args.get("agent"))
        session.current_agent = new_agent
        return {"success": True, "agent": AGENTS[new_agent].name}
    elif tool_name == "change_phase":
        new_phase = args.get("phase")
        session.phase = new_phase
        session.phase_start_time = datetime.now()
        return {"success": True, "phase": new_phase}
    elif tool_name == "finish_interview":
        return {"success": True, "action": "finish"}
    return {"success": False, "error": "Unknown tool"}

# СОВЕЩАНИЕ АГЕНТОВ (ИСПРАВЛЕНО)
def conduct_agent_meeting() -> Dict:
    """Проведение совещания всех агентов с обсуждением и финальным решением"""
    # Собираем базовую статистику
    total_penalties = sum(p.points for p in session.penalties)
    coding_avg = sum(session.coding_scores.values()) / max(len(session.coding_scores), 1) if session.coding_scores else 0
    theory_avg = sum(session.theory_scores.values()) / max(len(session.theory_scores), 1) if session.theory_scores else 0
    
    # Базовый скор
    base_score = (coding_avg * 0.5 + theory_avg * 0.3 + 0.2) * 100
    
    # ========== РАСЧЕТ БОНУСОВ ==========
    total_bonuses = 0.0
    bonus_details = []
    avg_learning_agility = 0.0  # Инициализация по умолчанию
    
    # 1. Learning Agility бонус
    if hasattr(session, 'learning_agility_scores') and session.learning_agility_scores:
        avg_learning_agility = sum(session.learning_agility_scores.values()) / len(session.learning_agility_scores)
        if avg_learning_agility > 0.7:
            learning_bonus = min(10, avg_learning_agility * 10)
            total_bonuses += learning_bonus
            bonus_details.append(f"Learning Agility: +{learning_bonus:.1f}")
            handle_tool_call("add_agent_note", {
                "note": f"Кандидат отлично учится на фидбеке (Learning Agility: {avg_learning_agility:.2f})",
                "sentiment": "positive"
            })
    
    # 2. Proactive Clarification бонус
    if hasattr(session, 'clarification_bonuses') and session.clarification_bonuses:
        clarification_bonus = sum(session.clarification_bonuses.values())
        total_bonuses += clarification_bonus
        bonus_details.append(f"Уточняющие вопросы: +{clarification_bonus:.1f}")
        if hasattr(session, 'clarification_analysis_history') and session.clarification_analysis_history:
            clarifications = [item for item in session.clarification_analysis_history if item.get("is_clarification")]
            if clarifications:
                avg_confidence = sum(item["confidence"] for item in clarifications) / len(clarifications)
                if avg_confidence > 0.8:
                    handle_tool_call("add_agent_note", {
                        "note": f"Кандидат задает качественные уточняющие вопросы (уверенность: {avg_confidence:.2f})",
                        "sentiment": "positive"
                    })
    
    # ========== ДЕТАЛИЗАЦИЯ ШТРАФОВ (БЕЗ ПОВТОРНОГО СЧЁТА) ==========
    # ВАЖНО: Все штрафы УЖЕ в session.penalties, здесь только формируем детали для отчёта
    penalty_details = []
    
    # Подсчёт по категориям для отчёта (не добавляем к total_penalties!)
    if hasattr(session, 'context_switching_violations') and session.context_switching_violations:
        cs_count = len(session.context_switching_violations)
        penalty_details.append(f"Смена темы: {cs_count} нарушений")
    
    if hasattr(session, 'code_readability_scores') and session.code_readability_scores:
        readability_issues = sum(v.get("violations_count", 0) for v in session.code_readability_scores.values())
        if readability_issues > 0:
            penalty_details.append(f"Качество кода (PEP8): {readability_issues} замечаний")
    
    if hasattr(session, 'conflict_behavior_violations') and session.conflict_behavior_violations:
        conflict_count = len(session.conflict_behavior_violations)
        penalty_details.append(f"Деструктивное поведение: {conflict_count} нарушений")
        # Критическое нарушение = автоматический NO_HIRE
        critical_violations = [v for v in session.conflict_behavior_violations if v.get("severity") == "critical"]
        if critical_violations:
            handle_tool_call("add_agent_note", {
                "note": f"КРИТИЧЕСКОЕ НАРУШЕНИЕ: {critical_violations[0].get('reason', 'деструктивное поведение')}",
                "sentiment": "negative"
            })
    
    # Античит нарушения
    if hasattr(session, 'anticheat_violations') and session.anticheat_violations:
        anticheat_count = len(session.anticheat_violations)
        penalty_details.append(f"Античит: {anticheat_count} нарушений")
    
    # ========== ФИНАЛЬНЫЙ РАСЧЕТ ==========
    # total_penalties уже содержит ВСЕ штрафы, НЕ добавляем повторно!
    final_score = base_score - total_penalties + total_bonuses
    final_score = max(0, min(100, final_score))  # Ограничение 0-100
    
    # ========== ФОРМИРУЕМ КОНТЕКСТ ДЛЯ АГЕНТОВ ==========
    context = CONFIG["prompts"]["agent_meeting"]["context"].format(
        level=session.level,
        coding_completed=len(session.coding_scores),
        coding_total=len(session.coding_tasks),
        coding_avg=round(coding_avg * 100),
        theory_avg=round(theory_avg * 100),
        penalties_count=len(session.penalties),
        total_penalties=total_penalties,
        bonus_details="\n📈 Бонусы: " + ', '.join(bonus_details) if bonus_details else "",
        penalty_details="\n📉 Дополнительные штрафы: " + ', '.join(penalty_details) if penalty_details else "",
        learning_agility_details=f"\n🎯 Способность к обучению: {avg_learning_agility:.2f}/1.0" if hasattr(session, 'learning_agility_scores') and session.learning_agility_scores else "",
        code_readability_details=f"\n📝 Читаемость кода: {sum(v.get('readability_score', 0) for v in session.code_readability_scores.values()) / max(len(session.code_readability_scores), 1):.2f}/1.0" if hasattr(session, 'code_readability_scores') and session.code_readability_scores else "",
        final_score=round(final_score),
        agent_notes=json.dumps(session.agent_notes, ensure_ascii=False, indent=2)
    )
    
    # Получаем фидбек от каждого агента
    agent_decisions = {}
    for role, agent in AGENTS.items():
        prompt = CONFIG["prompts"]["agent_meeting"]["prompt"].format(
            context=context,
            agent_title=agent.title,
            focus_areas=", ".join(agent.focus_areas)
        )
        system = CONFIG["prompts"]["agent_meeting"]["system"].format(
            agent_name=agent.name,
            agent_title=agent.title
        )
        response = call_llm_simple(prompt, system)
        session.agent_feedback[role.value] = response
        # Парсим решение
        if "STRONG_HIRE" in response.upper():
            agent_decisions[role.value] = "strong_hire"
            session.agent_scores[role.value] = 95
        elif "NO_HIRE" in response.upper():
            agent_decisions[role.value] = "no_hire"
            session.agent_scores[role.value] = 30
        elif "MAYBE" in response.upper():
            agent_decisions[role.value] = "maybe"
            session.agent_scores[role.value] = 60
        else:
            agent_decisions[role.value] = "hire"
            session.agent_scores[role.value] = 80
    
    # Проверка на критические нарушения conflict behavior
    has_critical_violation = False
    if hasattr(session, 'conflict_behavior_violations'):
        has_critical_violation = any(v.get("severity") == "critical" for v in session.conflict_behavior_violations)
    
    # Финальное решение (голосование)
    if has_critical_violation:
        final_decision = "NO HIRE ⛔"  # Автоматический отказ при критическом нарушении
    else:
        decisions = list(agent_decisions.values())
        if decisions.count("strong_hire") >= 2:
            final_decision = "STRONG HIRE ⭐"
        elif decisions.count("no_hire") >= 2:
            final_decision = "NO HIRE ❌"
        elif decisions.count("hire") + decisions.count("strong_hire") >= 2:
            final_decision = "HIRE ✅"
        else:
            final_decision = "MAYBE 🤔"
    
    return {
        "final_score": round(final_score),
        "final_decision": final_decision,
        "agent_feedback": session.agent_feedback,
        "agent_scores": session.agent_scores,
        "penalties": [asdict(p) for p in session.penalties],
        "statistics": {
            "coding_tasks_completed": len(session.coding_scores),
            "coding_avg": round(coding_avg * 100),
            "theory_avg": round(theory_avg * 100),
            "total_penalties": round(total_penalties, 1),
            "total_bonuses": round(total_bonuses, 1)
        },
        # Детальная информация по новым метрикам
        "new_metrics": {
            "learning_agility": {
                "avg_score": round(sum(session.learning_agility_scores.values()) / max(len(session.learning_agility_scores), 1), 2) if session.learning_agility_scores else 0,
                "questions_analyzed": len(session.learning_agility_scores)
            },
            "context_switching": {
                "violations_count": len(session.context_switching_violations) if hasattr(session, 'context_switching_violations') else 0,
                "total_penalty": round(sum(v.get("penalty_score", 0) for v in session.context_switching_violations), 2) if hasattr(session, 'context_switching_violations') else 0
            },
            "code_readability": {
                "avg_score": round(sum(v.get("readability_score", 0) for v in session.code_readability_scores.values()) / max(len(session.code_readability_scores), 1), 2) if hasattr(session, 'code_readability_scores') and session.code_readability_scores else 0,
                "total_violations": sum(v.get("violations_count", 0) for v in session.code_readability_scores.values()) if hasattr(session, 'code_readability_scores') else 0
            },
            "conflict_behavior": {
                "violations_count": len(session.conflict_behavior_violations) if hasattr(session, 'conflict_behavior_violations') else 0,
                "has_critical": has_critical_violation
            },
            "clarification_bonus": round(sum(session.clarification_bonuses.values()), 2) if session.clarification_bonuses else 0
        }
    }

# FASTAPI APP
app = FastAPI(title="AI Interviewer v2 - Multi-Agent System")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class StartRequest(BaseModel):
    level: str
    candidate_name: Optional[str] = "Кандидат"

class SubmitCodeRequest(BaseModel):
    code: str
    task_id: int

class ChatRequest(BaseModel):
    message: str

class TheoryAnswerRequest(BaseModel):
    answer: str
    question_id: int

class AnticheatViolationRequest(BaseModel):
    type: str
    reason: str

# API ENDPOINTS
@app.on_event("startup")
async def startup():
    """Инициализация БД при старте"""
    init_database()
    seed_coding_tasks()
    seed_theory_questions()

@app.get("/")
def root():
    return {"status": "ok", "version": "2.1", "agents": [a.name for a in AGENTS.values()]}

@app.post("/api/start")
def start_interview(req: StartRequest):
    """Начать интервью"""
    global session
    session = InterviewSession()
    session.level = req.level
    session.start_time = datetime.now()
    session.phase_start_time = datetime.now()
    session.current_agent = AgentRole.HR_MANAGER
    session.phase = "intro"
    # Загружаем начальные задачи и вопросы
    session.coding_tasks = get_tasks_by_level(req.level, limit=3)
    session.theory_questions = get_theory_by_level(req.level, limit=2)
    for task in session.coding_tasks:
        session.used_task_ids.append(task['id'])
    # Приветствие от HR
    agent = AGENTS[AgentRole.HR_MANAGER]
    # Здесь мы используем шаблон из JSON конфигурации для приветствия
    greeting = call_llm_simple(
        CONFIG["prompts"]["initial"]["greeting"].format(
            candidate_name=req.candidate_name,
            level=req.level
        ),
        CONFIG["prompts"]["initial"]["agent_greeting_system"].format(
            agent_name=agent.name,
            agent_title=agent.title
        )
    )
    return {
        "success": True,
        "greeting": greeting,
        "agent": {
            "name": agent.name,
            "title": agent.title,
            "role": agent.role.value
        },
        "phase": session.phase,
        "total_coding_tasks": len(session.coding_tasks),
        "total_theory_questions": len(session.theory_questions)
    }

@app.get("/api/task")
def get_current_task():
    """Получить текущую задачу на код"""
    if session.current_task_idx >= len(session.coding_tasks):
        return {"success": False, "error": "Нет задач", "finished": True}
    task = session.coding_tasks[session.current_task_idx]
    return {
        "success": True,
        "task": {
            "id": task["id"],
            "title": task["title"],
            "description": task["description"],
            "examples": task["examples"],
            "starter_code": task["starter_code"],
            "time_limit": task["time_limit"],
            "difficulty": task["difficulty"]
        },
        "current": session.current_task_idx + 1,
        "total": len(session.coding_tasks)
    }

@app.get("/api/theory")
def get_current_theory():
    """Получить текущий теоретический вопрос"""
    if session.current_theory_idx >= len(session.theory_questions):
        return {"success": False, "error": "Нет вопросов", "finished": True}
    q = session.theory_questions[session.current_theory_idx]
    return {
        "success": True,
        "question": {
            "id": q["id"],
            "category": q["category"],
            "question": q["question"],
            "time_limit": q.get("time_limit", 5)
        },
        "current": session.current_theory_idx + 1,
        "total": len(session.theory_questions)
    }

@app.post("/api/submit-code")
def submit_code(req: SubmitCodeRequest):
    """Отправить решение задачи С ПРОВЕРКОЙ CODE READABILITY"""
    task = next((t for t in session.coding_tasks if t["id"] == req.task_id), None)
    if not task:
        return {"success": False, "error": "Задача не найдена"}
    # Считаем попытки
    task_key = f"coding_{req.task_id}"
    session.attempts[task_key] = session.attempts.get(task_key, 0) + 1
    # Штраф за множественные попытки
    if session.attempts[task_key] > 1:
        penalty = Penalty(
            type="multiple_attempts",
            points=CONFIG["penalty_weights"].get(session.level, CONFIG["penalty_weights"]["middle"])["multiple_attempts"],
            reason=f"Попытка #{session.attempts[task_key]} для задачи {task['title']}"
        )
        session.penalties.append(penalty)
    # ========== НОВОЕ: ПРОВЕРКА CODE READABILITY ==========
    readability_analysis = analyze_code_readability(req.code, session.level)
    session.code_readability_scores[req.task_id] = readability_analysis
    # Добавляем штраф за плохую читаемость если есть
    if readability_analysis["penalty_score"] > 0:
        penalty = Penalty(
            type="poor_code_readability",
            points=readability_analysis["penalty_score"],
            reason=f"Нарушения PEP8 в задаче {task['title']}: {readability_analysis['violations_count']} проблем"
        )
        session.penalties.append(penalty)
    # Запускаем тесты
    results = run_tests(req.code, task)
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    # Сохраняем скор
    score = passed / total if total > 0 else 0
    session.coding_scores[req.task_id] = score
    # Получаем фидбек от текущего агента
    agent = AGENTS[session.current_agent]
    if score == 1.0:
        # Здесь мы используем шаблон из JSON конфигурации для успешного фидбека
        feedback_prompt = CONFIG["prompts"]["coding"]["feedback_success"].format(
            task_title=task['title'],
            attempts_count=session.attempts[task_key]
        )
    else:
        # Здесь мы используем шаблон из JSON конфигурации для частичного фидбека
        feedback_prompt = CONFIG["prompts"]["coding"]["feedback_partial"].format(
            task_title=task['title'],
            passed=passed,
            total=total
        )
    feedback = call_llm_simple(
        feedback_prompt, 
        CONFIG["prompts"]["coding"]["agent_feedback_system"].format(
            agent_name=agent.name,
            agent_title=agent.title
        )
    )
    # Добавляем информацию о читаемости кода в фидбек
    if readability_analysis["violations_count"] > 0:
        feedback += f"\n📝 Качество кода: {readability_analysis['feedback']}"
        if readability_analysis["violations"][:3]:  # Показываем первые 3 проблемы
            feedback += "\nОсновные замечания:"
            for v in readability_analysis["violations"][:3]:
                feedback += f"\n  • {v['message']}"
    response = {
        "success": True,
        "results": results,
        "passed": passed,
        "total": total,
        "all_passed": passed == total,
        "feedback": feedback,
        "attempts": session.attempts[task_key],
        "agent": {"name": agent.name, "title": agent.title},
        # НОВОЕ: данные о читаемости кода
        "code_readability": {
            "score": readability_analysis["readability_score"],
            "violations_count": readability_analysis["violations_count"],
            "penalty_applied": readability_analysis["penalty_score"]
        }
    }
    # Если все тесты прошли - переходим к следующей задаче
    if passed == total:
        session.current_task_idx += 1
        if session.current_task_idx < len(session.coding_tasks):
            response["next_task"] = True
        else:
            response["coding_finished"] = True
    return response

@app.post("/api/submit-theory")
def submit_theory_answer(req: TheoryAnswerRequest):
    """Отправить ответ на теоретический вопрос С LEARNING AGILITY АНАЛИЗОМ"""
    q = next((q for q in session.theory_questions if q["id"] == req.question_id), None)
    if not q:
        return {"success": False, "error": "Вопрос не найден"}
    agent = AGENTS[session.current_agent]
    # 1. Проверяем, был ли предыдущий ответ на этот же вопрос
    has_previous_answer = req.question_id in session.previous_answers
    previous_answer = session.previous_answers.get(req.question_id, "")
    previous_feedback = session.feedback_received.get(req.question_id, "")
    # 2. Анализируем глубину ответа через LLM (ADR анализ)
    adr_analysis = calculate_adr_with_llm(
        answer=req.answer,
        question=q['question'],
        expected_topics=q.get('expected_topics', [])
    )
    adr_score = adr_analysis["adr_score"]
    adr_quality = "высокая" if adr_score > 0.6 else "средняя" if adr_score > 0.3 else "низкая"
    # 3. Основная оценка через LLM
    # Здесь мы используем шаблон из JSON конфигурации для оценки теоретического ответа
    eval_prompt = CONFIG["prompts"]["theory"]["evaluation"].format(
        question=q['question'],
        answer=req.answer,
        expected_topics=", ".join(q.get('expected_topics', [])),
        adr_score=adr_score,
        adr_quality=adr_quality
    )
    eval_response = call_llm_simple(
        eval_prompt, 
        CONFIG["prompts"]["theory"]["evaluator_system"]
    )
    # 4. Парсим оценку
    score_match = re.search(r'ОЦЕНКА:\s*(\d+)', eval_response)
    base_score = int(score_match.group(1)) if score_match else 5
    base_score = min(10, max(0, base_score)) / 10.0
    # 5. Рассчитываем Learning Agility Score ЕСЛИ был предыдущий ответ и фидбек
    learning_agility_score = 0.0
    learning_analysis = {}
    if has_previous_answer and previous_feedback:
        learning_analysis = calculate_learning_agility(
            previous_answer=previous_answer,
            new_answer=req.answer,
            feedback=previous_feedback
        )
        learning_agility_score = learning_analysis.get("score", 0.0)
        print(f"🎯 Learning Agility Score: {learning_agility_score:.2f}")
    # 6. Корректируем оценку на основе ADR и Learning Agility
    final_score = base_score
    # ADR коррекция
    if adr_score > 0.7:
        final_score = min(1.0, final_score + 0.15)  # +15% за отличную глубину
    elif adr_score > 0.3:
        final_score = max(0.0, final_score - 0.1)  # -10% за недостаточную глубину
    else:
        final_score = max(0.0, final_score - 0.25)  # -25% за поверхностный ответ
    # 7. Добавляем штраф за очень низкий ADR
    if adr_score < 0.25:
        penalty_points = CONFIG["penalty_weights"][session.level]["poor_communication"]
        penalty = Penalty(
            type="poor_communication",
            points=penalty_points,
            reason=f"Слишком поверхностный ответ с 'водой' (ADR={adr_score:.2f})"
        )
        session.penalties.append(penalty)
    # 8. Сохраняем результаты
    session.theory_scores[req.question_id] = final_score
    # 9. Сохраняем текущий ответ для будущего анализа Learning Agility
    session.previous_answers[req.question_id] = req.answer
    # 10. Формируем фидбек
    feedback_match = re.search(r'ФИДБЕК:\s*(.+)', eval_response, re.DOTALL)
    base_feedback = feedback_match.group(1).strip() if feedback_match else eval_response
    # 11. Улучшаем фидбек данными от ADR и Learning Agility анализов
    enhanced_feedback = f"{base_feedback}\n🔍 Глубина ответа: {adr_score:.2f}/1.0\n💡 {adr_analysis['feedback']}"
    if adr_analysis["issues"]:
        issues_str = ", ".join(adr_analysis["issues"])
        enhanced_feedback += f"\n⚠️ Проблемы: {issues_str}"
    # 12. Добавляем фидбек по Learning Agility если применимо
    if has_previous_answer and learning_agility_score > 0.3:
        enhanced_feedback += f"\n🎯 Способность к обучению: {learning_agility_score:.2f}/1.0"
        enhanced_feedback += f"\n✨ {learning_analysis.get('feedback', 'Хорошее улучшение')}"
        if learning_analysis.get("improved_areas"):
            improved = ", ".join(learning_analysis["improved_areas"])
            enhanced_feedback += f"\n✅ Улучшено: {improved}"
        # Сохраняем фидбек для будущих сравнений
        session.feedback_received[req.question_id] = enhanced_feedback
    # 13. Сохраняем Learning Agility Score
    session.learning_agility_scores[req.question_id] = learning_agility_score
    # 14. Продолжаем логику
    session.current_theory_idx += 1
    response = {
        "success": True,
        "score": round(final_score * 100),
        "adr_score": round(adr_score * 100),
        "learning_agility_score": round(learning_agility_score * 100),
        "feedback": clean_response(enhanced_feedback),
        "agent": {"name": agent.name, "title": agent.title}
    }
    if session.current_theory_idx >= len(session.theory_questions):
        response["theory_finished"] = True
    else:
        response["next_question"] = True
    return response

@app.post("/api/chat")
def chat(req: ChatRequest):
    """Чат с текущим агентом С АНАЛИЗОМ ВСЕХ НОВЫХ МЕТРИК"""
    agent = AGENTS[session.current_agent]
    # 1. Проверяем время реакции на предыдущий фидбек
    penalty = check_feedback_response_time(session)
    if penalty:
        session.penalties.append(penalty)
    # 2. Определяем текущий контекст
    current_context = "Введение в интервью"
    context_type = "intro"
    context_id = "intro"
    if session.phase == "theory" and session.current_theory_idx < len(session.theory_questions):
        current_question = session.theory_questions[session.current_theory_idx]
        current_context = f"Теоретический вопрос по {current_question['category']}: {current_question['question']}"
        context_type = "theory"
        context_id = f"theory_{current_question['id']}"
    elif session.phase == "coding" and session.current_task_idx < len(session.coding_tasks):
        current_task = session.coding_tasks[session.current_task_idx]
        current_context = f"Задача на код: {current_task['title']} - {current_task['description']}"
        context_type = "coding"
        context_id = f"coding_{current_task['id']}"
    # ========== НОВОЕ: АНАЛИЗ CONFLICT BEHAVIOR ==========
    conflict_analysis = analyze_conflict_behavior(
        message=req.message,
        chat_history=session.chat_history,
        level=session.level
    )
    if conflict_analysis["is_violation"]:
        session.conflict_behavior_violations.append(conflict_analysis)
        # Добавляем штраф
        penalty = Penalty(
            type="conflict_behavior",
            points=conflict_analysis["penalty_score"],
            reason=f"Деструктивное поведение ({conflict_analysis['behavior_type']}): {conflict_analysis['reason']}"
        )
        session.penalties.append(penalty)
        # Добавляем заметку агенту
        handle_tool_call("add_agent_note", {
            "note": f"⚠️ Деструктивное поведение: {conflict_analysis['reason'][:100]}",
            "sentiment": "negative"
        })
    # ========== НОВОЕ: АНАЛИЗ CONTEXT SWITCHING ==========
    context_switching_analysis = analyze_context_switching(
        current_message=req.message,
        chat_history=session.chat_history,
        current_context=current_context,
        level=session.level
    )
    if context_switching_analysis["is_violation"]:
        session.context_switching_violations.append(context_switching_analysis)
        # Добавляем штраф
        penalty = Penalty(
            type="context_switching",
            points=context_switching_analysis["penalty_score"],
            reason=f"Смена темы/нелогичный ответ: {context_switching_analysis['reason']}"
        )
        session.penalties.append(penalty)
        handle_tool_call("add_agent_note", {
            "note": f"Попытка смены темы: {context_switching_analysis['reason'][:80]}",
            "sentiment": "negative"
        })
    # 3. Анализируем сообщение на предмет уточняющего вопроса
    clarification_analysis = is_clarification_question_llm(req.message, current_context)
    is_clarification = clarification_analysis["is_clarification"]
    confidence = clarification_analysis["confidence"]
    # 4. Если это уточняющий вопрос с высокой уверенностью (>0.7) - даем бонус
    clarification_bonus = 0.0
    if is_clarification and confidence > 0.7:
        context_key = f"{context_type}_{context_id.split('_')[-1]}"
        if context_key not in session.clarification_requests:
            session.clarification_requests[context_key] = []
        session.clarification_requests[context_key].append({
            "question": req.message,
            "confidence": confidence,
            "timestamp": datetime.now().isoformat(),
            "reason": clarification_analysis["reason"]
        })
        question_count = len(session.clarification_requests[context_key])
        if question_count == 1:
            clarification_bonus = 3.0
        else:
            clarification_bonus = 1.0
        session.clarification_bonuses[context_key] = session.clarification_bonuses.get(context_key, 0.0) + clarification_bonus
        session.clarification_analysis_history.append({
            "message": req.message,
            "is_clarification": True,
            "confidence": confidence,
            "context": current_context,
            "bonus": clarification_bonus,
            "timestamp": datetime.now().isoformat()
        })
        handle_tool_call("add_agent_note", {
            "note": f"Кандидат задал уточняющий вопрос с уверенностью {confidence:.2f}",
            "sentiment": "positive"
        })
    # 5. Добавляем в историю
    session.chat_history.append({"role": "user", "content": req.message})
    # 6. Сбрасываем флаги времени реакции
    session.last_feedback_time = None
    session.feedback_response_penalty_applied = False
    # 7. Формируем контекст для агента
    # Здесь мы используем шаблон из JSON конфигурации для контекста чата
    context = CONFIG["prompts"]["chat"]["context"].format(
        phase=session.phase,
        level=session.level,
        coding_completed=len(session.coding_scores),
        coding_total=len(session.coding_tasks),
        theory_completed=len(session.theory_scores),
        theory_total=len(session.theory_questions),
        current_context=current_context
    )
    # 8. Если это уточняющий вопрос, используем подсказку
    if is_clarification and confidence > 0.7 and clarification_analysis.get("suggested_response"):
        context = CONFIG["prompts"]["chat"]["context_with_feedback"].format(
            phase=session.phase,
            level=session.level,
            coding_completed=len(session.coding_scores),
            coding_total=len(session.coding_tasks),
            theory_completed=len(session.theory_scores),
            theory_total=len(session.theory_questions),
            current_context=current_context,
            suggested_response=clarification_analysis['suggested_response']
        )
    # Если было деструктивное поведение, агент должен отреагировать
    if conflict_analysis["is_violation"] and conflict_analysis["severity"] in ["moderate", "severe", "critical"]:
        context = CONFIG["prompts"]["chat"]["context_with_conflict"].format(
            phase=session.phase,
            level=session.level,
            coding_completed=len(session.coding_scores),
            coding_total=len(session.coding_tasks),
            theory_completed=len(session.theory_scores),
            theory_total=len(session.theory_questions),
            current_context=current_context
        )
    messages = [
        {"role": "system", "content": context},
        *session.chat_history[-10:]
    ]
    # 9. Вызываем LLM
    result = call_llm_with_tools(messages, agent)
    # 10. Обрабатываем tool calls
    tool_results = []
    for tc in result.get("tool_calls", []):
        tr = handle_tool_call(tc["function"], tc["arguments"])
        tool_results.append({"tool": tc["function"], "result": tr})
    response_content = result.get("content", "")
    # 11. Определяем, является ли ответ фидбеком
    criticism_keywords = [
        "ошибка", "проблема", "улучшить", "неправильно", "некорректно",
        "совет", "рекомендую", "стоит", "лучше", "попробуй", "обрати внимание"
    ]
    is_feedback = any(keyword in response_content.lower() for keyword in criticism_keywords)
    if is_feedback:
        feedback_type = "theory" if session.phase == "theory" else "coding"
        session.last_feedback_time = datetime.now()
        session.last_feedback_type = feedback_type
        if feedback_type == "theory":
            time_limits = {"junior": 3, "middle": 2, "senior": 1.5}
        else:
            time_limits = {"junior": 15, "middle": 10, "senior": 8}
        time_limit_minutes = time_limits.get(session.level, 5)
        session.feedback_response_deadline = session.last_feedback_time + timedelta(minutes=time_limit_minutes)
        session.feedback_response_penalty_applied = False
    # 12. Добавляем ответ агента в историю
    session.chat_history.append({"role": "assistant", "content": response_content})
    # 13. Формируем ответ
    response_data = {
        "success": True,
        "response": response_content,
        "agent": {"name": agent.name, "title": agent.title, "role": agent.role.value},
        "tool_calls": tool_results,
        "phase": session.phase,
        "clarification_analysis": {
            "is_clarification": is_clarification,
            "confidence": round(confidence, 2),
            "reason": clarification_analysis["reason"],
            "bonus_applied": round(clarification_bonus, 1) if clarification_bonus > 0 else 0
        },
        "feedback_tracking": {
            "is_feedback": is_feedback,
            "last_feedback_time": session.last_feedback_time.isoformat() if session.last_feedback_time else None,
            "feedback_type": session.last_feedback_type,
            "deadline": session.feedback_response_deadline.isoformat() if session.feedback_response_deadline else None,
            "penalty_applied": session.feedback_response_penalty_applied
        },
        # НОВОЕ: результаты анализа новых метрик
        "behavior_analysis": {
            "conflict_detected": conflict_analysis["is_violation"],
            "conflict_severity": conflict_analysis.get("severity", "none"),
            "context_switching_detected": context_switching_analysis["is_violation"],
            "context_switching_severity": context_switching_analysis.get("severity", "none")
        }
    }
    if context_id in session.clarification_bonuses:
        response_data["total_clarification_bonus"] = round(session.clarification_bonuses[context_id], 1)
    return response_data

@app.post("/api/hint")
def get_hint():
    """Получить подсказку (со штрафом)"""
    if session.current_task_idx >= len(session.coding_tasks):
        return {"success": False, "error": "Нет текущей задачи"}
    task = session.coding_tasks[session.current_task_idx]
    hints = task.get("hints", [])
    task_key = f"hint_{task['id']}"
    hint_idx = session.attempts.get(task_key, 0)
    if hint_idx >= len(hints):
        return {"success": True, "hint": "Больше подсказок нет. Попробуй решить самостоятельно!"}
    # Штраф за подсказку
    penalty = Penalty(
        type="hint_used",
        points=CONFIG["penalty_weights"].get(session.level, CONFIG["penalty_weights"]["middle"])["hint_used"],
        reason=f"Подсказка для задачи {task['title']}"
    )
    session.penalties.append(penalty)
    session.attempts[task_key] = hint_idx + 1
    return {
        "success": True,
        "hint": f"💡 {hints[hint_idx]}",
        "penalty_applied": True,
        "hints_remaining": len(hints) - hint_idx - 1
    }

@app.post("/api/switch-agent")
def switch_agent(agent_role: str):
    """Переключить агента"""
    try:
        new_role = AgentRole(agent_role)
        session.current_agent = new_role
        agent = AGENTS[new_role]
        # Здесь мы используем шаблон из JSON конфигурации для представления нового агента
        intro = call_llm_simple(
            CONFIG["prompts"]["agent_switch"]["intro"].format(level=session.level),
            CONFIG["prompts"]["agent_switch"]["system"].format(
                agent_name=agent.name,
                agent_title=agent.title
            )
        )
        return {
            "success": True,
            "agent": {"name": agent.name, "title": agent.title, "role": agent.role.value},
            "intro": intro
        }
    except ValueError:
        return {"success": False, "error": "Неверная роль агента"}

@app.post("/api/finish")
def finish_interview():
    """Завершить интервью и получить результаты совещания"""
    session.phase = "final"
    report = conduct_agent_meeting()
    return {
        "success": True,
        "report": report
    }

@app.get("/api/status")
def get_status():
    """Текущий статус интервью"""
    agent = AGENTS[session.current_agent]
    return {
        "level": session.level,
        "phase": session.phase,
        "current_agent": {
            "name": agent.name,
            "title": agent.title,
            "role": agent.role.value
        },
        "coding": {
            "current": session.current_task_idx + 1,
            "total": len(session.coding_tasks),
            "completed": len(session.coding_scores)
        },
        "theory": {
            "current": session.current_theory_idx + 1,
            "total": len(session.theory_questions),
            "completed": len(session.theory_scores)
        },
        "penalties_count": len(session.penalties),
        "time_elapsed": (datetime.now() - session.start_time).seconds if session.start_time else 0,
        # НОВОЕ: статус новых метрик
        "new_metrics_status": {
            "context_switching_violations": len(session.context_switching_violations) if hasattr(session, 'context_switching_violations') else 0,
            "conflict_behavior_violations": len(session.conflict_behavior_violations) if hasattr(session, 'conflict_behavior_violations') else 0,
            "code_readability_checks": len(session.code_readability_scores) if hasattr(session, 'code_readability_scores') else 0
        }
    }

@app.get("/api/agents")
def get_agents():
    """Список всех агентов"""
    return {
        "agents": [
            {
                "role": agent.role.value,
                "name": agent.name,
                "title": agent.title,
                "personality": agent.personality,
                "focus_areas": agent.focus_areas
            }
            for agent in AGENTS.values()
        ],
        "current": session.current_agent.value
    }

@app.get("/api/metrics-info")
def get_metrics_info():
    """Информация о всех метриках системы"""
    return {
        "metrics": CONFIG["metrics_info"],
        "penalty_weights_by_level": CONFIG["penalty_weights"]
    }

# CODE EXECUTION
def run_tests(code: str, task: dict) -> list:
    """Запуск тестов для задачи"""
    results = []
    for test in task.get("tests", []):
        test_input = json.loads(test["input"]) if isinstance(test["input"], str) else test["input"]
        expected = json.loads(test["expected"]) if isinstance(test["expected"], str) else test["expected"]
        result = {
            "num": len(results) + 1,
            "passed": False,
            "expected": expected,
            "actual": None,
            "error": None,
            "hidden": bool(test.get("is_hidden", 0))
        }
        try:
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            namespace = {}
            exec(code, {"__builtins__": __builtins__}, namespace)
            if "solution" in namespace:
                actual = namespace["solution"](*test_input)
                result["actual"] = actual
                # Сравнение
                if isinstance(expected, list) and isinstance(actual, list):
                    try:
                        result["passed"] = sorted(expected) == sorted(actual)
                    except:
                        result["passed"] = expected == actual
                else:
                    result["passed"] = expected == actual
            else:
                result["error"] = "Функция 'solution' не найдена"
        except Exception as e:
            result["error"] = str(e)
        finally:
            sys.stdout = old_stdout
        results.append(result)
    return results

# АНТИЧИТ ENDPOINT
@app.post("/api/anticheat-violation")
def report_anticheat_violation(req: AnticheatViolationRequest):
    """Получение нарушения античита от фронтенда"""
    if not session.level:
        return {"success": False, "error": "Сессия не начата"}
    
    # Добавляем нарушение в историю
    violation = {
        "type": req.type,
        "reason": req.reason,
        "timestamp": datetime.now().isoformat()
    }
    session.anticheat_violations.append(violation)
    
    # Добавляем штраф
    penalty_weights = CONFIG["penalty_weights"].get(session.level, CONFIG["penalty_weights"]["middle"])
    penalty_points = penalty_weights.get(req.type, 10)
    
    penalty = Penalty(
        type=req.type,
        points=penalty_points,
        reason=f"Античит: {req.reason}"
    )
    session.penalties.append(penalty)
    
    # Добавляем заметку агенту
    handle_tool_call("add_agent_note", {
        "note": f"⚠️ Античит нарушение: {req.type} - {req.reason}",
        "sentiment": "negative"
    })
    
    return {
        "success": True,
        "penalty_applied": penalty_points,
        "total_violations": len(session.anticheat_violations)
    }

# MAIN
if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print(" AI Technical Interviewer v2.1 - Multi-Agent System")
    print(" + Context Switching, Code Readability, Conflict Behavior")
    print("="*60)
    print(f" Server: http://localhost:8000")
    print(f" Docs: http://localhost:8000/docs")
    print(f" Agents: {', '.join(a.name for a in AGENTS.values())}")
    print(f" LLM: {'Connected' if client else 'Not connected'}")
    print("="*60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)