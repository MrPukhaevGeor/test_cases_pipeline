import os
import re
import json
import yaml
import time
import logging
import pandas as pd
from pathlib import Path

# Настройки
BASE_PATH = Path("test_buckets/cases")
OUTPUT_FILE = "test_buckets_report.xlsx"
LEARNING_FILE = "learned_rules.json"
LOG_FILE = "pipeline.log"

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
        "алгоритм": 3, "сортировка": 3, "перепиши": 3, "senior": 3, "principal": 3,
        "функцию": 2, "класс": 2, "оптимизируй": 2, "реализуй": 2,
        "добавь функционал": 2, "валидацию": 2, "рефактор": 2, "ревью": 2,
        "код": 1, "напиши": 1, "программа": 1, "интеграц": 1, "разработ": 1
    },
    "Аналитик (Б+С)": {
        "sql": 3, "витрина": 3, "бизнес-атрибут": 3, "аналитик": 3,
        "запрос": 2, "отчёт": 2, "дашборд": 2, "выборка": 2,
        "обогащение": 2, "наименован": 2, "требован": 2,
        "данные": 1, "анализ": 1
    },
    "Тестировщик": {
        "юнит-тест": 3, "баг": 3, "тест-кейс": 3, "автотест": 3,
        "sql-инъекц": 2, "проверь": 2, "отладка": 2, "уязвимост": 2,
        "тест": 1, "найди": 1, "ошибку": 1, "qa": 1
    },
    "Dpeople": {
        "data science": 3, "machine learning": 3, "нейросет": 3,
        "датасет": 2, "модель обуч": 2, "исследоват": 2, "выборк": 1
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

def determine_role(text, learned_rules):
    if not text:
        return None
    t = text.lower()
    all_kw = {}
    for role, kw in ROLE_KEYWORDS.items():
        all_kw[role] = kw.copy()
    for word, role in learned_rules.get("keywords", {}).items():
        if role not in all_kw:
            all_kw[role] = {}
        all_kw[role][word] = 2
    scores = {}
    for role, kw in all_kw.items():
        score = sum(w for word, w in kw.items() if word in t)
        if score > 0:
            scores[role] = score
    if not scores:
        return None
    return max(scores, key=scores.get)

def llm_fallback_role(description, learned_rules):
    try:
        from zai import ZaiClient
        import httpx

        client = ZaiClient(
            api_key="d840f0ee19834bf89e2e1e5d73b2f679.bgW44QKU0xHBBjRx",
            http_client=httpx.Client(verify=False)
        )

        for attempt in range(3):
            try:
                time.sleep(2 + attempt * 3)
                response = client.chat.completions.create(
                    model="glm-4.7-flash",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Ты определяешь роль IT специалиста по описанию задачи. "
                                "Разработчик — пишет код, ревьюит, рефакторит, добавляет функционал. "
                                "Аналитик (Б+С) — работает с данными, SQL, требованиями, бизнес-атрибутами. "
                                "Тестировщик — пишет тесты, ищет баги, проверяет уязвимости. "
                                "Dpeople — data science, ML, нейросети. "
                                "Другие — если не подходит ни одна роль. "
                                "Ответь строго одним из: Разработчик, Аналитик (Б+С), Тестировщик, Dpeople, Другие."
                            )
                        },
                        {
                            "role": "user",
                            "content": f"Задача: {description[:500]}"
                        }
                    ]
                )
                answer = response.choices[0].message.content.strip()
                log.info(f"  llm ответил: {answer}")
                for role in ["Разработчик", "Аналитик (Б+С)", "Тестировщик", "Dpeople", "Другие"]:
                    if role in answer:
                        learn_from_llm(description, role, learned_rules)
                        return role
                break
            except Exception as e:
                if "429" in str(e):
                    wait = 5 * (attempt + 1)
                    log.warning(f"  429 лимит, ждём {wait} сек")
                    time.sleep(wait)
                else:
                    log.warning(f"  llm не сработал: {e}")
                    return None

    except Exception as e:
        log.warning(f"  llm недоступен: {e}")
    return None

def learn_from_llm(description, role, learned_rules):
    words = [w for w in description.lower().split() if len(w) > 4]
    words = [w for w in words if w not in learned_rules["keywords"]]
    for word in words[:3]:
        learned_rules["keywords"][word] = role
        log.info(f"  запомнил от llm: '{word}' → {role}")
    save_learned_rules(learned_rules)

def learn_from_manual(description, role, learned_rules):
    words = [w for w in description.lower().split() if len(w) > 4]
    words = [w for w in words if w not in learned_rules["keywords"]]
    for word in words[:3]:
        learned_rules["keywords"][word] = role
        log.info(f"  запомнил от человека: '{word}' → {role}")
    save_learned_rules(learned_rules)

def get_role(text, learned_rules):
    role = determine_role(text, learned_rules)
    if role:
        return role, "markers"
    role = llm_fallback_role(text, learned_rules)
    if role:
        return role, "llm"
    print(f"\nне удалось определить роль для: {text[:80]}")
    print("1 - Разработчик\n2 - Аналитик (Б+С)\n3 - Тестировщик\n4 - Dpeople\n5 - Другие")
    while True:
        choice = input("выбор (1-5): ").strip()
        roles = {
            "1": "Разработчик", "2": "Аналитик (Б+С)",
            "3": "Тестировщик", "4": "Dpeople", "5": "Другие"
        }
        if choice in roles:
            role = roles[choice]
            learn_from_manual(text, role, learned_rules)
            return role, "manual"

def get_priority(yaml_data):
    if not isinstance(yaml_data, dict):
        return ""
    cat = str(yaml_data.get("testability_category", "")).strip().upper()
    return {"A": "0", "B": "1", "C": "2", "D": "3"}.get(cat, "")

def get_scenario(yaml_data):
    if not isinstance(yaml_data, dict):
        return "Не определено"
    sys_p = str(yaml_data.get("system", yaml_data.get("system_prompt", "")))
    usr_p = str(yaml_data.get("user", yaml_data.get("user_prompt", "")))
    if not sys_p and not usr_p and "prompts" in yaml_data:
        p = yaml_data["prompts"]
        sys_p = str(p.get("system", p.get("system_prompt", "")))
        usr_p = str(p.get("user", p.get("user_prompt", "")))
    combined = f"{sys_p} {usr_p}".lower()
    if re.search(r'json|xml|yaml|csv|структурир|extract', combined):
        return "code2structured_output"
    if re.search(r'рефактор|оптимиз|исправ|refactor|migrate', combined):
        return "code2code"
    if re.search(r'напиши|сгенерируй|реализуй|write|implement', combined):
        return "text2code"
    if re.search(r'объясн|опиши|документ|ревью|explain|review|анализ', combined):
        return "code2text"
    return "Не определено"

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'[*_#~`]', '', str(text))
    text = re.sub(r'[^\w\sа-яА-ЯёЁ:,\.\-\(\)\/]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def load_yaml(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return yaml.safe_load(f)
    except Exception:
        return None

def load_json_file(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None

def get_description_04(in_dir):
    task_files = [f for f in in_dir.iterdir() if f.is_file() and 'in_task' in f.name.lower() and f.suffix == '.txt']
    if not task_files:
        return "", ""
    content = open(task_files[0], encoding="utf-8-sig").read()
    lines = content.splitlines()
    role_text = ""
    task_text = ""
    for line in lines:
        clean = re.sub(r'[*_#~`]', '', line).lower().strip()
        if 'роль' in clean and not role_text:
            parts = clean.split('роль', 1)
            role_text = parts[1].strip().lstrip(':* ')
        if 'задача' in clean and not task_text:
            parts = clean.split('задача', 1)
            task_text = parts[1].strip().lstrip(':* ')
    return clean_text(role_text), clean_text(task_text)

def get_description_05(json_data):
    instr = str(json_data.get("instruction", "")) if json_data else ""
    if not instr:
        return ""
    first = instr.find('\n')
    if first == -1:
        return ""
    second = instr.find('\n', first + 1)
    if second == -1:
        return ""
    return clean_text(instr[first + 1:second])

def calc_metric(case_type, in_dir, yaml_data):
    if case_type in ("01", "02", "03", "06"):
        xlsx_files = [f for f in in_dir.iterdir() if f.suffix == '.xlsx']
        xlsx_files.sort(key=lambda x: 0 if 'test_bucket' in x.name.lower() else 1)
        if xlsx_files:
            try:
                df = pd.read_excel(xlsx_files[0])
                col = next((c for c in df.columns if str(c).strip().lower() in ('grade', 'estimate')), None)
                if col:
                    val = str(df[col].dropna().iloc[0]).strip().lower()
                    return 1 if val in ('1', 'true', 'pass', 'да', 'yes') else 0, True
            except Exception:
                pass
    elif case_type in ("04", "05"):
        ans_files = list(in_dir.glob("*_answer.txt"))
        if ans_files and isinstance(yaml_data, dict):
            true_ans = yaml_data.get("true_answer")
            if true_ans:
                try:
                    content = open(ans_files[0], encoding="utf-8-sig").read()
                    match = re.sub(r'\s+', ' ', content).strip().lower() == re.sub(r'\s+', ' ', str(true_ans)).strip().lower()
                    return (1 if match else 0), True
                except Exception:
                    pass
    return 0, False

def main():
    if not BASE_PATH.exists():
        log.error(f"папка {BASE_PATH} не найдена")
        return

    learned_rules = load_learned_rules()
    log.info(f"загружено правил: {len(learned_rules.get('keywords', {}))}")

    cases = sorted([d for d in BASE_PATH.iterdir() if d.is_dir()])
    log.info(f"найдено папок: {len(cases)}")

    aggregated = {}

    for case_dir in cases:
        m = re.search(r'case_(\d{2})', case_dir.name)
        if not m:
            continue
        case_type = m.group(1)
        if case_type not in ("01", "02", "03", "04", "05", "06"):
            continue

        log.info(f"обрабатываем: {case_dir.name}")

        in_dir = case_dir / "01_in"
        int_dir = case_dir / "02_intermediate"
        out_dir = case_dir / "03_out"

        if not in_dir.exists():
            log.warning(f"  нет папки 01_in, пропускаем")
            continue

        yaml_data = None
        if int_dir.exists():
            y_files = [f for f in int_dir.iterdir() if f.suffix.lower() in ('.yaml', '.yml')]
            if y_files:
                yaml_data = load_yaml(y_files[0])

        json_data = None
        lang = ""
        if out_dir.exists():
            j_files = [f for f in out_dir.iterdir() if f.suffix.lower() == '.json']
            j_files.sort(key=lambda x: 0 if x.name == 'case.json' else 1)
            if j_files:
                json_data = load_json_file(j_files[0])
                if json_data:
                    lang = str(json_data.get("language", "")).strip()

        role_text = ""
        desc = ""

        if case_type == "04":
            role_text, desc = get_description_04(in_dir)
        elif case_type == "05":
            desc = get_description_05(json_data)
            if yaml_data and isinstance(yaml_data, dict):
                y_instr = yaml_data.get("instruction", "")
                if isinstance(y_instr, list):
                    y_instr = " ".join(str(i) for i in y_instr)
                role_text = str(y_instr)
        else:
            txt_files = [f for f in in_dir.iterdir() if f.is_file() and f.suffix == '.txt' and 'case' in f.name.lower()]
            if txt_files:
                desc = clean_text(open(txt_files[0], encoding="utf-8-sig").read().strip())
                role_text = desc

        if not desc:
            desc = "Без описания"

        role, method = get_role(role_text or desc, learned_rules)
        log.info(f"  роль ({method}): {role}")

        priority = get_priority(yaml_data)
        if role == "Другие":
            priority = ""

        scenario = get_scenario(yaml_data) if yaml_data else "Нет YAML"

        materials = ""
        md_files = list(in_dir.glob("*.md"))
        if md_files:
            materials = md_files[0].name

        metric_score, has_metric = calc_metric(case_type, in_dir, yaml_data)

        key = (
            role.lower(), scenario.lower(), lang.lower(),
            desc.lower()[:100], materials.lower(), priority
        )

        if key not in aggregated:
            aggregated[key] = {
                "baskets": [], "role": role, "scenario": scenario,
                "lang": lang, "desc": desc, "materials": materials,
                "priority": priority, "metric_sum": 0.0, "has_metric": False
            }
        aggregated[key]["baskets"].append(case_dir.name)
        if has_metric:
            aggregated[key]["metric_sum"] += metric_score
            aggregated[key]["has_metric"] = True

    rows = []
    for data in aggregated.values():
        vol = len(data["baskets"])
        metric_str = ""
        if data["has_metric"] and vol > 0:
            avg = data["metric_sum"] / vol
            metric_str = f"{avg:.10f} (pass@1)"

        rows.append({
            "Приоритет для использования в GC тестах": data["priority"],
            "Роль для сценария": data["role"],
            "Сценарий": data["scenario"],
            "Язык программирования": data["lang"],
            "Описание задачи": data["desc"],
            "Объём": vol,
            "Материалы для оценки качества корзины": data["materials"],
            "Корзины": ", ".join(sorted(data["baskets"])),
            "Оценка качества (метрика)": metric_str,
            "Контакт для связи": ""
        })

    df = pd.DataFrame(rows, columns=[
        "Приоритет для использования в GC тестах", "Роль для сценария", "Сценарий",
        "Язык программирования", "Описание задачи", "Объём",
        "Материалы для оценки качества корзины", "Корзины",
        "Оценка качества (метрика)", "Контакт для связи"
    ])
    df.to_excel(OUTPUT_FILE, index=False)
    log.info(f"готово — {len(df)} строк в {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
