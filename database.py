"""
База данных для AI Technical Interviewer
Содержит задачи (код + теория), тесты, и историю интервью
"""

import sqlite3
import json
from pathlib import Path

DB_PATH = "interviewer.db"


def init_database():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица задач на код
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS coding_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,  -- junior, middle, senior
            difficulty INTEGER DEFAULT 1,  -- 1-10
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            examples TEXT NOT NULL,
            starter_code TEXT NOT NULL,
            hints TEXT NOT NULL,  -- JSON array
            tags TEXT,  -- JSON array: ["arrays", "algorithms", "dp"]
            time_limit INTEGER DEFAULT 15,  -- минуты
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица тестов для задач
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            input TEXT NOT NULL,  -- JSON
            expected TEXT NOT NULL,  -- JSON
            is_hidden INTEGER DEFAULT 0,
            weight REAL DEFAULT 1.0,
            FOREIGN KEY (task_id) REFERENCES coding_tasks(id)
        )
    ''')
    
    # Таблица теоретических вопросов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS theory_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,
            difficulty INTEGER DEFAULT 1,
            category TEXT NOT NULL,  -- python, algorithms, system_design, etc
            question TEXT NOT NULL,
            expected_topics TEXT NOT NULL,  -- JSON: ключевые темы для проверки
            follow_up TEXT,  -- JSON: дополнительные вопросы
            tags TEXT,
            time_limit INTEGER DEFAULT 5
        )
    ''')
    
    # Таблица сессий интервью
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interview_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT,
            level TEXT NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP,
            total_score REAL,
            hr_score REAL,
            tech_lead_score REAL,
            senior_dev_score REAL,
            hr_feedback TEXT,
            tech_lead_feedback TEXT,
            senior_dev_feedback TEXT,
            final_decision TEXT,
            penalties TEXT  -- JSON: список штрафов
        )
    ''')
    
    # Таблица ответов кандидата
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS candidate_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question_type TEXT NOT NULL,  -- coding, theory
            question_id INTEGER NOT NULL,
            answer TEXT NOT NULL,
            score REAL,
            attempts INTEGER DEFAULT 1,
            time_spent INTEGER,  -- секунды
            feedback TEXT,
            FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("База данных инициализирована")


def seed_coding_tasks():
    """Заполнение задач на код"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Проверяем, есть ли уже данные
    cursor.execute("SELECT COUNT(*) FROM coding_tasks")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return
    
    tasks = [
        
        {
            "level": "junior",
            "difficulty": 1,
            "title": "Сумма двух чисел",
            "description": "Напишите функцию solution(a, b), которая возвращает сумму двух чисел.",
            "examples": "solution(2, 3) → 5\nsolution(-1, 1) → 0\nsolution(100, 200) → 300",
            "starter_code": "def solution(a, b):\n    # Ваш код здесь\n    pass",
            "hints": json.dumps(["Используйте оператор +", "return a + b"]),
            "tags": json.dumps(["basics", "math"]),
            "time_limit": 5,
            "tests": [
                {"input": [2, 3], "expected": 5, "hidden": False},
                {"input": [-1, 1], "expected": 0, "hidden": False},
                {"input": [100, 200], "expected": 300, "hidden": False},
                {"input": [0, 0], "expected": 0, "hidden": True},
            ]
        },
        {
            "level": "junior",
            "difficulty": 2,
            "title": "Переворот строки",
            "description": "Напишите функцию solution(s), которая возвращает перевёрнутую строку.",
            "examples": "solution('hello') → 'olleh'\nsolution('abc') → 'cba'\nsolution('') → ''",
            "starter_code": "def solution(s):\n    # Ваш код здесь\n    pass",
            "hints": json.dumps(["Используйте срез [::-1]", "Или цикл в обратном порядке"]),
            "tags": json.dumps(["strings", "basics"]),
            "time_limit": 5,
            "tests": [
                {"input": ["hello"], "expected": "olleh", "hidden": False},
                {"input": ["abc"], "expected": "cba", "hidden": False},
                {"input": [""], "expected": "", "hidden": False},
                {"input": ["a"], "expected": "a", "hidden": True},
            ]
        },
        {
            "level": "junior",
            "difficulty": 3,
            "title": "Подсчёт гласных",
            "description": "Напишите функцию solution(s), которая возвращает количество гласных букв (a, e, i, o, u) в строке. Регистр не важен.",
            "examples": "solution('hello') → 2\nsolution('AEIOU') → 5\nsolution('xyz') → 0",
            "starter_code": "def solution(s):\n    # Ваш код здесь\n    pass",
            "hints": json.dumps(["Преобразуйте в нижний регистр", "Используйте множество гласных"]),
            "tags": json.dumps(["strings", "counting"]),
            "time_limit": 7,
            "tests": [
                {"input": ["hello"], "expected": 2, "hidden": False},
                {"input": ["AEIOU"], "expected": 5, "hidden": False},
                {"input": ["xyz"], "expected": 0, "hidden": False},
                {"input": [""], "expected": 0, "hidden": True},
            ]
        },
        {
            "level": "junior",
            "difficulty": 3,
            "title": "Чётные числа",
            "description": "Напишите функцию solution(nums), которая возвращает список только чётных чисел из входного списка.",
            "examples": "solution([1,2,3,4,5,6]) → [2,4,6]\nsolution([1,3,5]) → []\nsolution([2,4]) → [2,4]",
            "starter_code": "def solution(nums):\n    # Ваш код здесь\n    pass",
            "hints": json.dumps(["Используйте % 2 == 0", "List comprehension упростит код"]),
            "tags": json.dumps(["arrays", "filtering"]),
            "time_limit": 7,
            "tests": [
                {"input": [[1,2,3,4,5,6]], "expected": [2,4,6], "hidden": False},
                {"input": [[1,3,5]], "expected": [], "hidden": False},
                {"input": [[2,4]], "expected": [2,4], "hidden": False},
                {"input": [[]], "expected": [], "hidden": True},
            ]
        },
        
        
        {
            "level": "middle",
            "difficulty": 4,
            "title": "Two Sum",
            "description": "Дан список nums и число target. Верните индексы двух чисел, сумма которых равна target. Гарантируется единственное решение.",
            "examples": "solution([2,7,11,15], 9) → [0,1]\nsolution([3,2,4], 6) → [1,2]\nsolution([3,3], 6) → [0,1]",
            "starter_code": "def solution(nums, target):\n    # Ваш код здесь\n    # Подсказка: используйте словарь\n    pass",
            "hints": json.dumps(["Используйте словарь для хранения индексов", "Ключ - число, значение - индекс", "O(n) решение лучше O(n²)"]),
            "tags": json.dumps(["arrays", "hash_table", "classic"]),
            "time_limit": 10,
            "tests": [
                {"input": [[2,7,11,15], 9], "expected": [0,1], "hidden": False},
                {"input": [[3,2,4], 6], "expected": [1,2], "hidden": False},
                {"input": [[3,3], 6], "expected": [0,1], "hidden": False},
                {"input": [[1,5,3,7], 8], "expected": [1,2], "hidden": True},
            ]
        },
        {
            "level": "middle",
            "difficulty": 5,
            "title": "Valid Parentheses",
            "description": "Проверьте, является ли строка скобок валидной. Скобки: (), [], {}. Каждая открывающая должна быть закрыта соответствующей закрывающей в правильном порядке.",
            "examples": "solution('()[]{}') → True\nsolution('(]') → False\nsolution('([])') → True\nsolution('([)]') → False",
            "starter_code": "def solution(s):\n    # Ваш код здесь\n    pass",
            "hints": json.dumps(["Используйте стек", "Словарь для соответствия скобок", "В конце стек должен быть пустым"]),
            "tags": json.dumps(["stack", "strings", "classic"]),
            "time_limit": 10,
            "tests": [
                {"input": ["()[]{}"], "expected": True, "hidden": False},
                {"input": ["(]"], "expected": False, "hidden": False},
                {"input": ["([])"], "expected": True, "hidden": False},
                {"input": ["([)]"], "expected": False, "hidden": True},
                {"input": [""], "expected": True, "hidden": True},
            ]
        },
        {
            "level": "middle",
            "difficulty": 5,
            "title": "Анаграммы",
            "description": "Напишите функцию, которая проверяет, являются ли две строки анаграммами (состоят из одинаковых букв). Игнорируйте пробелы и регистр.",
            "examples": "solution('listen', 'silent') → True\nsolution('hello', 'world') → False\nsolution('Dormitory', 'dirty room') → True",
            "starter_code": "def solution(s1, s2):\n    # Ваш код здесь\n    pass",
            "hints": json.dumps(["Уберите пробелы и приведите к одному регистру", "Отсортируйте буквы или используйте Counter"]),
            "tags": json.dumps(["strings", "sorting", "hash_table"]),
            "time_limit": 10,
            "tests": [
                {"input": ["listen", "silent"], "expected": True, "hidden": False},
                {"input": ["hello", "world"], "expected": False, "hidden": False},
                {"input": ["Dormitory", "dirty room"], "expected": True, "hidden": False},
                {"input": ["a", "a"], "expected": True, "hidden": True},
            ]
        },
        {
            "level": "middle",
            "difficulty": 6,
            "title": "Merge Intervals",
            "description": "Дан список интервалов, объедините все пересекающиеся интервалы. Интервал [a,b] пересекается с [c,d] если c <= b.",
            "examples": "solution([[1,3],[2,6],[8,10],[15,18]]) → [[1,6],[8,10],[15,18]]\nsolution([[1,4],[4,5]]) → [[1,5]]",
            "starter_code": "def solution(intervals):\n    # Ваш код здесь\n    pass",
            "hints": json.dumps(["Сначала отсортируйте по началу интервала", "Сравнивайте конец предыдущего с началом текущего"]),
            "tags": json.dumps(["arrays", "sorting", "intervals"]),
            "time_limit": 15,
            "tests": [
                {"input": [[[1,3],[2,6],[8,10],[15,18]]], "expected": [[1,6],[8,10],[15,18]], "hidden": False},
                {"input": [[[1,4],[4,5]]], "expected": [[1,5]], "hidden": False},
                {"input": [[[1,4],[2,3]]], "expected": [[1,4]], "hidden": True},
            ]
        },
        
        
        {
            "level": "senior",
            "difficulty": 7,
            "title": "LRU Cache",
            "description": "Реализуйте LRU (Least Recently Used) кэш с операциями get и put за O(1). При превышении capacity удаляется наименее недавно использованный элемент.",
            "examples": "cache = LRUCache(2)\ncache.put(1, 1)\ncache.put(2, 2)\ncache.get(1) → 1\ncache.put(3, 3)  # удаляет ключ 2\ncache.get(2) → -1",
            "starter_code": "class LRUCache:\n    def __init__(self, capacity: int):\n        pass\n    \n    def get(self, key: int) -> int:\n        pass\n    \n    def put(self, key: int, value: int) -> None:\n        pass\n\n# Для тестирования создайте solution как обёртку\ndef solution(operations, args):\n    cache = None\n    results = []\n    for op, arg in zip(operations, args):\n        if op == 'LRUCache':\n            cache = LRUCache(arg[0])\n            results.append(None)\n        elif op == 'get':\n            results.append(cache.get(arg[0]))\n        elif op == 'put':\n            cache.put(arg[0], arg[1])\n            results.append(None)\n    return results",
            "hints": json.dumps(["OrderedDict упрощает реализацию", "Или используйте двусвязный список + хеш-таблицу", "move_to_end() для OrderedDict"]),
            "tags": json.dumps(["design", "hash_table", "linked_list", "classic"]),
            "time_limit": 20,
            "tests": [
                {"input": [["LRUCache","put","put","get","put","get","put","get","get","get"], [[2],[1,1],[2,2],[1],[3,3],[2],[4,4],[1],[3],[4]]], 
                 "expected": [None,None,None,1,None,-1,None,-1,3,4], "hidden": False},
            ]
        },
        {
            "level": "senior",
            "difficulty": 7,
            "title": "Maximum Subarray (Kadane)",
            "description": "Найдите непрерывный подмассив с максимальной суммой и верните эту сумму. Используйте алгоритм Кадана за O(n).",
            "examples": "solution([-2,1,-3,4,-1,2,1,-5,4]) → 6  # [4,-1,2,1]\nsolution([1]) → 1\nsolution([5,4,-1,7,8]) → 23",
            "starter_code": "def solution(nums):\n    # Алгоритм Кадана\n    # Ваш код здесь\n    pass",
            "hints": json.dumps(["Отслеживайте текущую и максимальную сумму", "current = max(num, current + num)", "Сложность должна быть O(n)"]),
            "tags": json.dumps(["arrays", "dp", "classic"]),
            "time_limit": 10,
            "tests": [
                {"input": [[-2,1,-3,4,-1,2,1,-5,4]], "expected": 6, "hidden": False},
                {"input": [[1]], "expected": 1, "hidden": False},
                {"input": [[5,4,-1,7,8]], "expected": 23, "hidden": False},
                {"input": [[-1]], "expected": -1, "hidden": True},
            ]
        },
        {
            "level": "senior",
            "difficulty": 8,
            "title": "Word Break",
            "description": "Дана строка s и словарь wordDict. Определите, можно ли разбить s на последовательность слов из словаря. Слова можно использовать многократно.",
            "examples": "solution('leetcode', ['leet','code']) → True\nsolution('applepenapple', ['apple','pen']) → True\nsolution('catsandog', ['cats','dog','sand','and','cat']) → False",
            "starter_code": "def solution(s, wordDict):\n    # Используйте DP\n    # Ваш код здесь\n    pass",
            "hints": json.dumps(["Динамическое программирование", "dp[i] = можно ли разбить s[:i]", "Проверяйте все возможные окончания"]),
            "tags": json.dumps(["dp", "strings", "hash_table"]),
            "time_limit": 15,
            "tests": [
                {"input": ["leetcode", ["leet","code"]], "expected": True, "hidden": False},
                {"input": ["applepenapple", ["apple","pen"]], "expected": True, "hidden": False},
                {"input": ["catsandog", ["cats","dog","sand","and","cat"]], "expected": False, "hidden": False},
                {"input": ["a", ["a"]], "expected": True, "hidden": True},
            ]
        },
        {
            "level": "senior",
            "difficulty": 9,
            "title": "Median of Two Sorted Arrays",
            "description": "Даны два отсортированных массива nums1 и nums2. Найдите медиану объединённого массива. Сложность должна быть O(log(m+n)).",
            "examples": "solution([1,3], [2]) → 2.0\nsolution([1,2], [3,4]) → 2.5",
            "starter_code": "def solution(nums1, nums2):\n    # Binary search approach\n    # Ваш код здесь\n    pass",
            "hints": json.dumps(["Бинарный поиск по меньшему массиву", "Найдите правильную точку разбиения", "Сложность O(log(min(m,n)))"]),
            "tags": json.dumps(["binary_search", "arrays", "hard"]),
            "time_limit": 25,
            "tests": [
                {"input": [[1,3], [2]], "expected": 2.0, "hidden": False},
                {"input": [[1,2], [3,4]], "expected": 2.5, "hidden": False},
                {"input": [[0,0], [0,0]], "expected": 0.0, "hidden": True},
            ]
        },
    ]
    
    for task in tasks:
        tests = task.pop("tests")
        cursor.execute('''
            INSERT INTO coding_tasks (level, difficulty, title, description, examples, starter_code, hints, tags, time_limit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (task["level"], task["difficulty"], task["title"], task["description"], 
              task["examples"], task["starter_code"], task["hints"], task["tags"], task["time_limit"]))
        
        task_id = cursor.lastrowid
        
        for test in tests:
            cursor.execute('''
                INSERT INTO task_tests (task_id, input, expected, is_hidden)
                VALUES (?, ?, ?, ?)
            ''', (task_id, json.dumps(test["input"]), json.dumps(test["expected"]), int(test.get("hidden", False))))
    
    conn.commit()
    conn.close()
    print(f"Добавлено {len(tasks)} задач на код")


def seed_theory_questions():
    """Заполнение теоретических вопросов"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM theory_questions")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return
    
    questions = [
    
        {
            "level": "junior",
            "difficulty": 1,
            "category": "python_basics",
            "question": "Чем отличается список (list) от кортежа (tuple) в Python?",
            "expected_topics": json.dumps(["изменяемость/неизменяемость", "mutable/immutable", "синтаксис [] vs ()", "производительность"]),
            "follow_up": json.dumps(["Когда лучше использовать кортеж?", "Можно ли изменить элемент кортежа?"]),
            "tags": json.dumps(["python", "data_structures"]),
        },
        {
            "level": "junior",
            "difficulty": 1,
            "category": "python_basics",
            "question": "Что такое list comprehension? Приведите пример.",
            "expected_topics": json.dumps(["синтаксис [expr for item in iterable]", "создание списков", "фильтрация с if", "читаемость"]),
            "follow_up": json.dumps(["Чем отличается от generator expression?", "Когда лучше использовать обычный цикл?"]),
            "tags": json.dumps(["python", "syntax"]),
        },
        {
            "level": "junior",
            "difficulty": 2,
            "category": "python_basics",
            "question": "Объясните разницу между == и is в Python.",
            "expected_topics": json.dumps(["== сравнивает значения", "is сравнивает идентичность объектов", "id()", "кэширование малых целых"]),
            "follow_up": json.dumps(["Что вернёт `a = [1,2]; b = [1,2]; a == b; a is b`?"]),
            "tags": json.dumps(["python", "operators"]),
        },
        {
            "level": "junior",
            "difficulty": 2,
            "category": "algorithms",
            "question": "Что такое временная сложность алгоритма? Что означает O(n)?",
            "expected_topics": json.dumps(["Big O notation", "рост времени с размером входа", "O(n) - линейная сложность", "примеры"]),
            "follow_up": json.dumps(["Какая сложность у поиска в списке? В словаре?"]),
            "tags": json.dumps(["algorithms", "complexity"]),
        },
        
        
        {
            "level": "middle",
            "difficulty": 4,
            "category": "python_advanced",
            "question": "Что такое декораторы в Python? Как они работают?",
            "expected_topics": json.dumps(["функция высшего порядка", "обёртка функций", "@decorator синтаксис", "functools.wraps", "примеры использования"]),
            "follow_up": json.dumps(["Напишите декоратор для измерения времени выполнения", "Что такое декоратор с параметрами?"]),
            "tags": json.dumps(["python", "decorators", "functions"]),
        },
        {
            "level": "middle",
            "difficulty": 4,
            "category": "python_advanced",
            "question": "Объясните GIL (Global Interpreter Lock). Как он влияет на многопоточность?",
            "expected_topics": json.dumps(["один поток исполняет байткод", "проблема CPU-bound задач", "multiprocessing как альтернатива", "IO-bound задачи работают"]),
            "follow_up": json.dumps(["Когда использовать threading, когда multiprocessing?", "Как обойти GIL?"]),
            "tags": json.dumps(["python", "concurrency", "threading"]),
        },
        {
            "level": "middle",
            "difficulty": 5,
            "category": "algorithms",
            "question": "Объясните разницу между BFS и DFS. Когда какой использовать?",
            "expected_topics": json.dumps(["BFS - поиск в ширину, очередь", "DFS - поиск в глубину, стек/рекурсия", "BFS для кратчайшего пути", "DFS для обхода всех путей"]),
            "follow_up": json.dumps(["Какая сложность по памяти у каждого?", "Реализуйте DFS для графа"]),
            "tags": json.dumps(["algorithms", "graphs", "traversal"]),
        },
        {
            "level": "middle",
            "difficulty": 5,
            "category": "databases",
            "question": "Чем отличается SQL от NoSQL баз данных? Когда что использовать?",
            "expected_topics": json.dumps(["реляционные vs документные", "ACID vs BASE", "схема vs бессхемность", "масштабирование", "примеры: PostgreSQL, MongoDB"]),
            "follow_up": json.dumps(["Что такое ACID?", "Приведите пример, когда лучше NoSQL"]),
            "tags": json.dumps(["databases", "sql", "nosql"]),
        },
        {
            "level": "middle",
            "difficulty": 5,
            "category": "system_design",
            "question": "Что такое REST API? Какие основные принципы?",
            "expected_topics": json.dumps(["stateless", "HTTP методы GET/POST/PUT/DELETE", "ресурсы и URI", "коды ответов", "JSON"]),
            "follow_up": json.dumps(["Чем REST отличается от GraphQL?", "Что такое идемпотентность?"]),
            "tags": json.dumps(["api", "rest", "http"]),
        },
        
        
        {
            "level": "senior",
            "difficulty": 7,
            "category": "system_design",
            "question": "Как бы вы спроектировали систему сокращения URL (типа bit.ly)?",
            "expected_topics": json.dumps(["хеширование/base62", "БД для маппинга", "кэширование Redis", "масштабирование", "обработка коллизий", "аналитика кликов"]),
            "follow_up": json.dumps(["Как обеспечить уникальность коротких URL?", "Как масштабировать на миллионы запросов?"]),
            "tags": json.dumps(["system_design", "scaling", "databases"]),
        },
        {
            "level": "senior",
            "difficulty": 7,
            "category": "python_advanced",
            "question": "Объясните метаклассы в Python. Когда они нужны?",
            "expected_topics": json.dumps(["класс классов", "type как метакласс", "__new__ и __init__", "кастомизация создания классов", "ORM, Django models"]),
            "follow_up": json.dumps(["Напишите метакласс для автоматической регистрации классов", "Альтернативы метаклассам?"]),
            "tags": json.dumps(["python", "metaclasses", "advanced"]),
        },
        {
            "level": "senior",
            "difficulty": 8,
            "category": "system_design",
            "question": "Как обеспечить согласованность данных в распределённой системе?",
            "expected_topics": json.dumps(["CAP теорема", "eventual consistency", "strong consistency", "distributed transactions", "saga pattern", "2PC"]),
            "follow_up": json.dumps(["Что такое CAP теорема?", "Как работает Saga pattern?"]),
            "tags": json.dumps(["distributed_systems", "consistency", "architecture"]),
        },
        {
            "level": "senior",
            "difficulty": 8,
            "category": "architecture",
            "question": "Расскажите о паттернах проектирования, которые вы используете. Приведите примеры.",
            "expected_topics": json.dumps(["Singleton, Factory, Strategy, Observer", "SOLID принципы", "когда применять", "антипаттерны"]),
            "follow_up": json.dumps(["Когда Singleton — антипаттерн?", "Объясните Dependency Injection"]),
            "tags": json.dumps(["patterns", "architecture", "oop"]),
        },
        {
            "level": "senior",
            "difficulty": 9,
            "category": "system_design",
            "question": "Спроектируйте систему обработки платежей с высокой доступностью.",
            "expected_topics": json.dumps(["идемпотентность", "транзакции", "retry с backoff", "очереди", "мониторинг", "PCI DSS", "распределённые блокировки"]),
            "follow_up": json.dumps(["Как обработать двойное списание?", "Как обеспечить exactly-once семантику?"]),
            "tags": json.dumps(["system_design", "payments", "reliability"]),
        },
    ]
    
    for q in questions:
        cursor.execute('''
            INSERT INTO theory_questions (level, difficulty, category, question, expected_topics, follow_up, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (q["level"], q["difficulty"], q["category"], q["question"], 
              q["expected_topics"], q.get("follow_up"), q.get("tags")))
    
    conn.commit()
    conn.close()
    print(f" Добавлено {len(questions)} теоретических вопросов")


def get_tasks_by_level(level: str, limit: int = 5) -> list:
    """Получить задачи по уровню"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM coding_tasks WHERE level = ? ORDER BY difficulty LIMIT ?
    ''', (level, limit))
    
    tasks = [dict(row) for row in cursor.fetchall()]
    
    for task in tasks:
        cursor.execute('SELECT * FROM task_tests WHERE task_id = ?', (task['id'],))
        task['tests'] = [dict(row) for row in cursor.fetchall()]
        task['hints'] = json.loads(task['hints'])
        task['tags'] = json.loads(task['tags']) if task['tags'] else []
    
    conn.close()
    return tasks


def get_theory_by_level(level: str, limit: int = 3) -> list:
    """Получить теоретические вопросы по уровню"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM theory_questions WHERE level = ? ORDER BY difficulty LIMIT ?
    ''', (level, limit))
    
    questions = [dict(row) for row in cursor.fetchall()]
    
    for q in questions:
        q['expected_topics'] = json.loads(q['expected_topics'])
        q['follow_up'] = json.loads(q['follow_up']) if q['follow_up'] else []
        q['tags'] = json.loads(q['tags']) if q['tags'] else []
    
    conn.close()
    return questions


def get_adaptive_task(level: str, current_score: float, used_task_ids: list) -> dict:
    """Получить адаптивную задачу на основе текущего результата"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Определяем сложность на основе текущего скора
    if current_score >= 0.8:
        difficulty_range = (6, 10)  
    elif current_score >= 0.5:
        difficulty_range = (4, 7)   
    else:
        difficulty_range = (1, 4)   
    
    # Исключаем уже использованные задачи
    placeholders = ','.join('?' * len(used_task_ids)) if used_task_ids else '-1'
    
    cursor.execute(f'''
        SELECT * FROM coding_tasks 
        WHERE level = ? AND difficulty BETWEEN ? AND ? AND id NOT IN ({placeholders})
        ORDER BY RANDOM() LIMIT 1
    ''', (level, difficulty_range[0], difficulty_range[1], *used_task_ids))
    
    row = cursor.fetchone()
    if not row:
        cursor.execute(f'''
            SELECT * FROM coding_tasks 
            WHERE level = ? AND id NOT IN ({placeholders})
            ORDER BY RANDOM() LIMIT 1
        ''', (level, *used_task_ids))
        row = cursor.fetchone()
    
    if not row:
        conn.close()
        return None
    
    task = dict(row)
    cursor.execute('SELECT * FROM task_tests WHERE task_id = ?', (task['id'],))
    task['tests'] = [dict(r) for r in cursor.fetchall()]
    task['hints'] = json.loads(task['hints'])
    
    conn.close()
    return task


if __name__ == "__main__":
    init_database()
    seed_coding_tasks()
    seed_theory_questions()
    
    print("\n Статистика БД:")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT level, COUNT(*) FROM coding_tasks GROUP BY level")
    print("\nЗадачи на код:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")
    
    cursor.execute("SELECT level, COUNT(*) FROM theory_questions GROUP BY level")
    print("\nТеоретические вопросы:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")
    
    conn.close()
