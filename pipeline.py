import os
import json
import pandas as pd
from difflib import SequenceMatcher

# Настройки
ARCHIVE_FOLDER = "test_cases"
EXCEL_FILE = "table.xlsx"
EXCEL_SHEET = "Sheet1"

# Правила для определения роли
ROLE_KEYWORDS = {
    "Разработчик": {
        "алгоритм": 3, "сортировка": 3, "перепиши": 3,
        "функцию": 2, "класс": 2, "оптимизируй": 2, "реализуй": 2,
        "код": 1, "напиши": 1, "программа": 1
    },
    "Аналитик": {
        "sql": 3, "json": 3, "витрина": 3,
        "запрос": 2, "отчёт": 2, "дашборд": 2, "выборка": 2,
        "данные": 1, "отчет": 1, "анализ": 1
    },
    "Тестировщик": {
        "юнит-тест": 3, "баг": 3, "тест-кейс": 3,
        "проверь": 2, "отладка": 2, "дебаг": 2,
        "тест": 1, "найди": 1, "ошибку": 1
    }
}

LEARNING_FILE = "learned_rules.json"

def load_learned_rules():
    if os.path.exists(LEARNING_FILE):
        with open(LEARNING_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"keywords": {}}

def save_learned_rules(rules):
    with open(LEARNING_FILE, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

def determine_role(description, learned_rules):
    if not description:
        return None

    desc_lower = description.lower()

    all_keywords = {}
    for role, keywords in ROLE_KEYWORDS.items():
        all_keywords[role] = keywords.copy()

    # добавляем изученные правила с весом 2
    learned = learned_rules.get("keywords", {})
    for keyword, role in learned.items():
        if role not in all_keywords:
            all_keywords[role] = {}
        all_keywords[role][keyword] = 2

    scores = {}
    for role, keywords in all_keywords.items():
        score = 0
        matched = []
        for word, weight in keywords.items():
            if word in desc_lower:
                score += weight
                matched.append(f"{word}({weight})")
        if score > 0:
            scores[role] = {"score": score, "matches": matched}

    if not scores:
        return None

    best_role = max(scores, key=lambda r: scores[r]["score"])
    return best_role

def find_similar_row(df, description, threshold=0.5):
    if "Описание задачи" not in df.columns:
        print("В таблице нет колонки 'Описание задачи'")
        return None, 0

    best_match = None
    best_ratio = 0

    for idx, row in df.iterrows():
        task_desc = str(row["Описание задачи"]) if pd.notna(row["Описание задачи"]) else ""
        if not task_desc:
            continue
        ratio = SequenceMatcher(None, description.lower(), task_desc.lower()).ratio()
        if ratio > best_ratio and ratio > threshold:
            best_ratio = ratio
            best_match = idx

    return best_match, best_ratio

def read_description_from_folder(folder_path):
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if os.path.isdir(item_path) and item.startswith("01_"):
            for file in os.listdir(item_path):
                if file.endswith(".txt"):
                    with open(os.path.join(item_path, file), 'r', encoding='utf-8') as f:
                        return f.read().strip()
    return None

def add_basket_to_cell(existing, new_basket):
    if pd.isna(existing) or existing == "":
        return new_basket
    existing_str = str(existing)
    if new_basket in existing_str:
        return existing_str
    return f"{existing_str}, {new_basket}"

def learn_from_manual(description, role, learned_rules):
    words = description.lower().split()
    for word in words:
        if len(word) > 4 and word not in learned_rules["keywords"]:
            learned_rules["keywords"][word] = role
            save_learned_rules(learned_rules)
            print(f"запомнил правило: '{word}' → {role}")
            break

def main():
    df = pd.read_excel(EXCEL_FILE, sheet_name=EXCEL_SHEET)
    print(f"загружена таблица: {len(df)} строк")

    learned_rules = load_learned_rules()
    print(f"загружено изученных правил: {len(learned_rules.get('keywords', {}))}")

    folders = [
        f for f in os.listdir(ARCHIVE_FOLDER)
        if os.path.isdir(os.path.join(ARCHIVE_FOLDER, f))
    ]
    print(f"найдено папок: {len(folders)}")

    stats = {"auto": 0, "manual": 0, "new_row": 0, "skipped": 0}

    for i, folder_name in enumerate(folders, 1):
        folder_path = os.path.join(ARCHIVE_FOLDER, folder_name)
        print(f"\n[{i}/{len(folders)}] папка: {folder_name}")

        description = read_description_from_folder(folder_path)
        if not description:
            print("не найдено описание задачи, пропускаем")
            stats["skipped"] += 1
            continue
        print(f"описание: {description[:100]}...")

        role = determine_role(description, learned_rules)
        if role:
            print(f"автоопределение: {role}")
            stats["auto"] += 1
        else:
            print("не удалось определить роль автоматически")
            print("варианты:")
            print("  1 - Разработчик")
            print("  2 - Аналитик")
            print("  3 - Тестировщик")

            while True:
                choice = input("твой выбор (1/2/3): ").strip()
                if choice == '1':
                    role = "Разработчик"
                    break
                elif choice == '2':
                    role = "Аналитик"
                    break
                elif choice == '3':
                    role = "Тестировщик"
                    break

            # запоминаем новое правило
            learn_from_manual(description, role, learned_rules)
            stats["manual"] += 1

        match_idx, match_ratio = find_similar_row(df, description)

        if match_idx is not None:
            print(f"найдена похожая строка (совпадение {match_ratio:.0%})")
            row_idx = match_idx
        else:
            print("похожих строк не найдено, создаём новую")
            new_row = {col: None for col in df.columns}
            new_row["Описание задачи"] = f"New {description[:100]}"
            new_row["Роли для сценария"] = role
            new_row["Корзины"] = folder_name
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            row_idx = len(df) - 1
            stats["new_row"] += 1

        if "Корзины" in df.columns:
            current_baskets = df.at[row_idx, "Корзины"]
            df.at[row_idx, "Корзины"] = add_basket_to_cell(current_baskets, folder_name)

        if "Роли для сценария" in df.columns:
            current_role = df.at[row_idx, "Роли для сценария"]
            if pd.isna(current_role) or current_role == "":
                df.at[row_idx, "Роли для сценария"] = role

        df.to_excel(EXCEL_FILE, sheet_name=EXCEL_SHEET, index=False)
        print(f"сохранено в строку {row_idx + 1}")

    print("\nстатистика:")
    print(f"автоопределено: {stats['auto']}")
    print(f"вручную: {stats['manual']}")
    print(f"новых строк: {stats['new_row']}")
    print(f"пропущено: {stats['skipped']}")
    print(f"всего: {i}")
    print(f"таблица сохранена в {EXCEL_FILE}")
    print(f"правила сохранены в {LEARNING_FILE}")

if __name__ == "__main__":
    main()