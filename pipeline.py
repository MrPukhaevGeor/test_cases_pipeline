import os
import json
import logging
import pandas as pd
import yaml
import re
import subprocess
from difflib import SequenceMatcher

# Настройки
CASES_FOLDER = "test_cases/test_buckets/cases"
EXCEL_FILE = "table.xlsx"
EXCEL_SHEET = "Sheet1"
LEARNING_FILE = "learned_rules.json"
LOG_FILE = "pipeline.log"
SIMILARITY_THRESHOLD = 0.55

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

ROLE_KEYWORDS = {
    "Разработчик": {
        "алгоритм": 3, "сортировка": 3, "перепиши": 3,
        "функцию": 2, "класс": 2, "оптимизируй": 2, "реализуй": 2,
        "senior": 2, "добавь функционал": 2,
        "код": 1, "напиши": 1, "программа": 1
    },
    "Аналитик": {
        "sql": 3, "json": 3, "витрина": 3,
        "запрос": 2, "отчёт": 2, "дашборд": 2, "выборка": 2,
        "бизнес-атрибут": 3, "обогащение": 2, "наименован": 2,
        "данные": 1, "анализ": 1
    },
    "Тестировщик": {
        "юнит-тест": 3, "баг": 3, "тест-кейс": 3,
        "автотест": 3, "sql-инъекц": 2,
        "проверь": 2, "отладка": 2,
        "тест": 1, "найди": 1, "ошибку": 1
    }
}

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
    for keyword, role in learned_rules.get("keywords", {}).items():
        if role not in all_keywords:
            all_keywords[role] = {}
        all_keywords[role][keyword] = 2
    scores = {}
    for role, keywords in all_keywords.items():
        score = sum(w for word, w in keywords.items() if word in desc_lower)
        if score > 0:
            scores[role] = score
    if not scores:
        return None
    return max(scores, key=scores.get)

def llm_fallback_role(description):
    try:
        prompt = f"Определи роль специалиста который выполняет задачу. Варианты только: Разработчик, Аналитик, Тестировщик. Ответь одним словом без пояснений.\n\nЗадача: {description[:300]}"
        result = subprocess.run(
            ["gigacode", prompt],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8"
        )
        answer = result.stdout.strip()
        log.info(f"gigacode ответил: {answer}")
        for role in ["Разработчик", "Аналитик", "Тестировщик"]:
            if role in answer:
                return role
        log.warning(f"gigacode вернул неожиданный ответ: {answer}")
    except Exception as e:
        log.warning(f"gigacode fallback не сработал: {e}")
    return None

def parse_yaml_description(content):
    try:
        data = yaml.safe_load(content)
        if isinstance(data, dict):
            for key in ["description", "instruction", "task", "scenario", "name", "title"]:
                if key in data and isinstance(data[key], str):
                    return data[key].strip()
            texts = [str(v) for v in data.values() if isinstance(v, str) and len(v) > 10]
            if texts:
                return " ".join(texts[:3])
    except Exception as e:
        log.warning(f"не удалось распарсить yaml: {e}")
    return content.strip()

def clean_text(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^a-zа-яё0-9\s\.\,]', '', text)
    return text.strip()

def read_description(folder_path):
    for item in sorted(os.listdir(folder_path)):
        item_path = os.path.join(folder_path, item)
        if os.path.isdir(item_path) and item.startswith("01_"):
            txt_files = [f for f in os.listdir(item_path) if f.endswith(".txt")]
            if not txt_files:
                yaml_files = [f for f in os.listdir(item_path) if f.endswith(".yaml") or f.endswith(".yml")]
                if yaml_files:
                    file_path = os.path.join(item_path, yaml_files[0])
                    with open(file_path, encoding='utf-8') as f:
                        raw = f.read()
                    return parse_yaml_description(raw)
                return None
            for file in txt_files:
                if file.lower().endswith("task.txt"):
                    file_path = os.path.join(item_path, file)
                    with open(file_path, encoding='utf-8') as f:
                        content = f.read().strip()
                    content = clean_text(content)
                    if "задача" in content:
                        parts = content.split("задача", 1)
                        result = parts[1] if len(parts) > 1 else content
                        result = result.lstrip(':').lstrip().lstrip('\n')
                        next_header = re.search(r'\n#{1,3}', result)
                        if next_header:
                            result = result[:next_header.start()]
                        lines = result.split('\n')
                        result = ' '.join([l for l in lines if 'важно' not in l.lower()])
                        return result.strip()
            for file in txt_files:
                if file.lower().endswith("question.txt"):
                    file_path = os.path.join(item_path, file)
                    with open(file_path, encoding='utf-8') as f:
                        first_line = f.readline().strip()
                    return clean_text(first_line)
            all_texts = []
            for file in txt_files:
                file_path = os.path.join(item_path, file)
                with open(file_path, encoding='utf-8') as f:
                    all_texts.append(f.read().strip())
            return clean_text(" ".join(all_texts))
    return None

def find_row_by_basket(df, folder_name):
    if "Корзины" not in df.columns:
        return None
    for idx, row in df.iterrows():
        cell = str(row["Корзины"]) if pd.notna(row["Корзины"]) else ""
        if folder_name in cell:
            return idx
    return None

def find_row_by_text(df, description, threshold=SIMILARITY_THRESHOLD):
    if "Описание задачи" not in df.columns:
        return None, 0
    best_match = None
    best_ratio = 0
    for idx, row in df.iterrows():
        task_desc = str(row["Описание задачи"]) if pd.notna(row["Описание задачи"]) else ""
        if not task_desc or task_desc.startswith("New "):
            continue
        ratio = SequenceMatcher(None, description.lower(), task_desc.lower()).ratio()
        if ratio > best_ratio and ratio > threshold:
            best_ratio = ratio
            best_match = idx
    return best_match, best_ratio

def add_basket_to_cell(existing, new_basket):
    if pd.isna(existing) or str(existing).strip() == "":
        return new_basket
    existing_str = str(existing)
    if new_basket in existing_str:
        return existing_str
    return f"{existing_str}, {new_basket}"

def learn_from_manual(description, role, learned_rules):
    words = [w for w in description.lower().split() if len(w) > 4]
    words = [w for w in words if w not in learned_rules["keywords"]]
    added = 0
    for word in words:
        if added >= 3:
            break
        learned_rules["keywords"][word] = role
        log.info(f"запомнил: '{word}' → {role}")
        added += 1
    save_learned_rules(learned_rules)

def save_excel_safe(df, filepath, sheet):
    df.to_excel(filepath, index=False)

def main():
    if not os.path.exists(EXCEL_FILE):
        log.error(f"файл {EXCEL_FILE} не найден")
        return
    if not os.path.exists(CASES_FOLDER):
        log.error(f"папка {CASES_FOLDER} не найдена")
        return

    df = pd.read_excel(EXCEL_FILE, sheet_name=EXCEL_SHEET)
    log.info(f"загружена таблица: {len(df)} строк")

    learned_rules = load_learned_rules()
    log.info(f"загружено правил: {len(learned_rules.get('keywords', {}))}")

    folders = [
        f for f in sorted(os.listdir(CASES_FOLDER))
        if os.path.isdir(os.path.join(CASES_FOLDER, f))
    ]
    log.info(f"найдено папок: {len(folders)}\n")

    stats = {"auto": 0, "manual": 0, "new_row": 0, "skipped": 0}
    total = 0

    for i, folder_name in enumerate(folders, 1):
        total = i
        folder_path = os.path.join(CASES_FOLDER, folder_name)
        log.info(f"[{i}/{len(folders)}] {folder_name}")

        description = read_description(folder_path)
        if not description:
            log.warning(f"  описание не найдено, пропускаем")
            stats["skipped"] += 1
            continue

        log.info(f"  описание: {description[:80]}...")

        role = determine_role(description, learned_rules)
        if role:
            log.info(f"  роль (авто): {role}")
            stats["auto"] += 1
        else:
            role = llm_fallback_role(description)
            if role:
                log.info(f"  роль (gigacode): {role}")
                stats["auto"] += 1
            else:
                log.info("  роль не определена, спрашиваем вручную")
                print(f"\n[{folder_name}] выбери роль:")
                print("  1 - Разработчик")
                print("  2 - Аналитик")
                print("  3 - Тестировщик")
                while True:
                    choice = input("  выбор (1/2/3): ").strip()
                    if choice == '1':
                        role = "Разработчик"
                        break
                    elif choice == '2':
                        role = "Аналитик"
                        break
                    elif choice == '3':
                        role = "Тестировщик"
                        break
                learn_from_manual(description, role, learned_rules)
                stats["manual"] += 1

        row_idx = find_row_by_basket(df, folder_name)
        if row_idx is not None:
            log.info(f"  найдена по названию → строка {row_idx + 1}")
        else:
            row_idx, ratio = find_row_by_text(df, description)
            if row_idx is not None:
                log.info(f"  найдена по тексту ({ratio:.0%}) → строка {row_idx + 1}")
            else:
                log.info(f"  строка не найдена, создаём новую")
                new_row = {col: None for col in df.columns}
                new_row["Описание задачи"] = description[:100] if description else ""
                new_row["Роли для сценария"] = role if role else ""
                new_row["Корзины"] = folder_name
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                row_idx = len(df) - 1
                stats["new_row"] += 1

        if "Корзины" in df.columns:
            df.at[row_idx, "Корзины"] = add_basket_to_cell(
                df.at[row_idx, "Корзины"], folder_name
            )
        if "Роли для сценария" in df.columns:
            current_role = df.at[row_idx, "Роли для сценария"]
            if pd.isna(current_role) or str(current_role).strip() == "":
                df.at[row_idx, "Роли для сценария"] = role

        save_excel_safe(df, EXCEL_FILE, EXCEL_SHEET)
        log.info(f"  сохранено\n")

    log.info("готово!")
    log.info(f"авто: {stats['auto']}")
    log.info(f"вручную: {stats['manual']}")
    log.info(f"новых строк: {stats['new_row']}")
    log.info(f"пропущено: {stats['skipped']}")
    log.info(f"всего: {total}")

if __name__ == "__main__":
    main()
