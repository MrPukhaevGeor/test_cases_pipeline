import os
import json
import pandas as pd

# -------------------------------------------------------
# ЗАГЛУШКА: замени путь на реальный когда будешь на варме
# cases_path = "путь_до_папки_cases"
# for root, dirs, files in os.walk(cases_path):
#     if "case.json" in files:
#         with open(os.path.join(root, "case.json")) as f:
#             test_cases.append(json.load(f))
# -------------------------------------------------------
test_cases = [
    {
        "id": "b2b_case_01",
        "language": "java",
        "task_domain": "banking-backend",
        "difficulty": "medium (~45 min)",
        "instruction": "Добавь функционал в b3-адаптер ППРБ согласно задаче BTHREE-608",
        "evaluation": {"method": "execution_test"}
    },
    {
        "id": "b2c_case_01",
        "language": "python",
        "task_domain": "ml-platform",
        "difficulty": "easy",
        "instruction": "Ты — опытный разработчик уровня senior. Напиши функцию для обработки данных",
        "evaluation": {"method": "execution_test"}
    },
    {
        "id": "b2c_case_02",
        "language": "java",
        "task_domain": "analytics",
        "difficulty": "hard",
        "instruction": "Обогащение бизнес-атрибутов их техническими наименованиями",
        "evaluation": {"method": "manual"}
    },
    {
        "id": "b2c_case_03",
        "language": "python",
        "task_domain": "qa-platform",
        "difficulty": "medium",
        "instruction": "Напиши автотест для проверки SQL-инъекций в форме авторизации",
        "evaluation": {"method": "execution_test"}
    },
]

# маркеры с весами
role_markers = {
    "Разработчик": [
        ("senior", 3), ("разработчик", 3), ("напиши функцию", 2),
        ("сгенерируй код", 2), ("добавь функционал", 2), ("ревью", 1),
    ],
    "Аналитик": [
        ("бизнес-атрибут", 3), ("аналитик", 3), ("наименован", 2), ("обогащение", 2),
    ],
    "Тестировщик": [
        ("тест", 3), ("автотест", 3), ("баг", 2), ("sql-инъекц", 2), ("qa", 2),
    ]
}

domain_hints = {
    "qa-platform": "Тестировщик",
    "analytics": "Аналитик",
}

def determine_role(case):
    instruction = case["instruction"].lower()
    scores = {"Разработчик": 0, "Аналитик": 0, "Тестировщик": 0}
    for role, markers in role_markers.items():
        for marker, weight in markers:
            if marker.lower() in instruction:
                scores[role] += weight
    if case["task_domain"].lower() in domain_hints:
        scores[domain_hints[case["task_domain"].lower()]] += 2
    best_role = max(scores, key=scores.get)
    return best_role if scores[best_role] > 0 else "needs_review"

def determine_scenario(case):
    instruction = case["instruction"].lower()
    if any(w in instruction for w in ["напиши", "сгенерируй", "добавь функционал"]):
        return "text2code"
    elif any(w in instruction for w in ["объясни", "что делает", "опиши"]):
        return "code2text"
    elif any(w in instruction for w in ["исправь", "ревью", "исправления"]):
        return "code2code"
    elif any(w in instruction for w in ["автотест", "json", "xml", "обогащение"]):
        return "code2structured_output"
    return "needs_review"

def build_system_prompt(role, language):
    templates = {
        "Разработчик": f"Ты — опытный разработчик уровня senior, специализирующийся на {language}. Твоя задача — писать чистый, эффективный код.",
        "Аналитик": f"Ты — опытный бизнес-аналитик. Твоя задача — анализировать данные и формировать структурированные выводы.",
        "Тестировщик": f"Ты — опытный QA-инженер, специализирующийся на {language}. Твоя задача — находить баги и писать автотесты.",
    }
    return templates.get(role, "Ты — опытный специалист. Выполни задачу.")

def call_model(system_prompt, user_prompt, model, params):
    # -------------------------------------------------------
    # ЗАГЛУШКА: вставить реальный вызов API GigaChat
    # import requests
    # response = requests.post(
    #     "https://api.gigachat.ru/v1/chat/completions",
    #     headers={"Authorization": f"Bearer {API_KEY}"},
    #     json={
    #         "model": model,
    #         "messages": [
    #             {"role": "system", "content": system_prompt},
    #             {"role": "user", "content": user_prompt}
    #         ],
    #         **params
    #     }
    # )
    # return response.json()["choices"][0]["message"]["content"]
    # -------------------------------------------------------
    return None

# настройки модели
# по ТЗ нужна конкретная версия с объёмом параметров
model = "GigaChat-Max-2"  # уточни точное название у Тони
params = {"temperature": 0.7, "top_p": 0.9}

rows = []
needs_review_cases = []

for case in test_cases:
    role = determine_role(case)
    scenario = determine_scenario(case)
    system_prompt = build_system_prompt(role, case["language"])
    user_prompt = case["instruction"]
    answer = call_model(system_prompt, user_prompt, model, params)
    needs_review = role == "needs_review" or scenario == "needs_review"

    if needs_review:
        needs_review_cases.append(case["id"])

    # estimation и annotator_id заполняются вручную разметчиком
    # по ТЗ LLM-as-a-judge запрещён
    rows.append({
        "id": case["id"],
        "role": role,
        "scenario": scenario,
        "language": case["language"],
        "difficulty": case["difficulty"],
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "answer": answer,
        "model": model,
        "params": str(params),
        "estimation": None,       # заполняет разметчик вручную
        "annotator_id": None,     # id разметчика — заполняется при оценке
        "needs_review": needs_review
    })

df = pd.DataFrame(rows)
df.to_excel("output.xlsx", index=False)

print(f"готово — {len(rows)} кейсов обработано")
print(f"needs_review: {needs_review_cases if needs_review_cases else 'нет'}")
print("output.xlsx сохранён")