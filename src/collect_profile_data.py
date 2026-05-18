import sys
import time
import csv
import json
import re
import random
from urllib.parse import urlparse
import undetected_chromedriver as uc
from bs4 import BeautifulSoup

class ProfiFinalUltra:
    DEFAULT_URL = (
        "https://profi.ru/hub/repetitor/profiles/"
        "?seamless=1&tabName=PROFILES"
    )

    def __init__(self):
        print("🚀 Запуск парсера...")
        options = uc.ChromeOptions()
        options.add_argument('--start-maximized')
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

        try:
            self.driver = uc.Chrome(options=options, version_main=147)
        except Exception as e:
            print(f"❌ Ошибка запуска: {e}")
            exit()

        self.all_data = []
        self.seen_urls = set()
        self.all_fieldnames = set()

    def clean_html(self, text):
        if not text:
            return ""
        soup = BeautifulSoup(str(text), 'html.parser')
        return soup.get_text(separator=' ', strip=True)

    def serialize_value(self, value):
        if value is None:
            return ""
        if isinstance(value, (bool, int, float, str)):
            return value
        return json.dumps(value, ensure_ascii=False)

    def extract_experience_and_years(self, info_list):
        exp_total = "—"
        years_on_profi = "—"

        for item in info_list:
            content = item.get('content', '')
            if not content:
                continue

            clean = self.clean_html(content)

            match = re.search(r"На Профи\.ру с \d{4}", clean, re.IGNORECASE)
            if match:
                years_on_profi = match.group(0)
                continue

            match = re.search(r"На сервисе с \d{4}", clean, re.IGNORECASE)
            if match:
                years_on_profi = match.group(0)
                continue

            lines = clean.split('\n')
            for line in lines:
                if re.search(r"Опыт\s*(работы)?\s*[–—-]\s*.+", line, re.IGNORECASE):
                    if not re.search(r"Образование", line, re.IGNORECASE):
                        exp_total = re.sub(r"Опыт\s*(работы)?\s*[–—-]\s*", "", line, flags=re.IGNORECASE).strip()
                        break

        return exp_total, years_on_profi

    def parse_any_json(self, obj, parent_obj=None):
        count = 0
        if isinstance(obj, dict):
            alias = obj.get('id') or obj.get('alias')
            name_obj = obj.get('name')

            if alias and name_obj and isinstance(alias, str) and len(alias) > 5:
                name = name_obj.get('full') if isinstance(name_obj, dict) else name_obj
                if not name:
                    name = obj.get('fullName') or obj.get('shortName')

                is_specialist = (
                    obj.get('model') == 'SPECIALIST' or
                    bool(obj.get('fullName')) or
                    (isinstance(name_obj, dict) and 'full' in name_obj)
                )

                alias_is_digit_only = alias.isdigit()

                forbidden_keywords = ['установка', 'ремонт', 'монтаж', 'подключение']
                name_lower = name.lower() if name else ''
                has_forbidden = any(kw in name_lower for kw in forbidden_keywords)

                if (is_specialist and not alias_is_digit_only and not has_forbidden
                        and "profile" not in alias.lower()):
                    url = f"https://profi.ru/profile/{alias}/"
                    if url not in self.seen_urls:
                        row = {}
                        for key, val in obj.items():
                            row[key] = self.serialize_value(val)

                        info_list = obj.get('assembledInfoListing') or []
                        exp_total, years_on_profi = self.extract_experience_and_years(info_list)
                        row['_Стаж'] = exp_total
                        row['_Лет_на_сайте'] = years_on_profi
                        row['_Ссылка'] = url

                        self.all_data.append(row)
                        self.seen_urls.add(url)
                        self.all_fieldnames.update(row.keys())
                        count += 1

            for v in obj.values():
                if isinstance(v, (dict, list)):
                    count += self.parse_any_json(v, parent_obj=obj)

        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    count += self.parse_any_json(item, parent_obj=None)
        return count

    def get_data_from_page_source(self):
        try:
            raw_data = self.driver.execute_script("return JSON.stringify(window.__NEXT_DATA__)")
            if raw_data:
                data = json.loads(raw_data)
                return self.parse_any_json(data)
        except:
            return 0
        return 0

    def find_masters_in_logs(self):
        try:
            logs = self.driver.get_log('performance')
        except:
            return 0

        found_in_step = 0
        for entry in logs:
            try:
                message = json.loads(entry['message'])['message']
                if message['method'] == 'Network.responseReceived':
                    url = message['params']['response']['url']
                    if "graphql" in url or "api" in url:
                        request_id = message['params']['requestId']
                        body = self.driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                        content = json.loads(body['body'])
                        found_in_step += self.parse_any_json(content)
            except:
                continue
        return found_in_step

    def _ensure_url_params(self, url):
        sep = "&" if "?" in url else "?"
        if "seamless=1" not in url:
            url = f"{url}{sep}seamless=1"
            sep = "&"
        if "tabName=PROFILES" not in url:
            url = f"{url}{sep}tabName=PROFILES"
        return url

    def _url_to_filename(self, url):
        parts = [p for p in urlparse(url).path.strip('/').split('/') if p]
        slug = '_'.join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else 'masters')
        return f"profi_{slug}.csv"

    SCROLL_JS = r"""
    (function() {
        window.scrollTo(0, document.body.scrollHeight);
        const scrollables = Array.from(document.querySelectorAll('*')).filter(el => {
            const s = getComputedStyle(el);
            const oy = s.overflowY;
            return (oy === 'auto' || oy === 'scroll' || oy === 'overlay')
                && el.scrollHeight - el.clientHeight > 20
                && el.clientHeight > 150;
        });
        scrollables.forEach(el => { el.scrollTop = el.scrollHeight; });
        return scrollables.length;
    })();
    """

    CLICK_MORE_JS = r"""
    (function() {
        const re = /показать\s*ещ[её]|показать\s*больше|загрузить\s*ещ[её]|^ещ[её]\b|показать\s*все[хъ]?|show\s*more|load\s*more/i;
        const candidates = document.querySelectorAll('button, [role="button"], a');
        for (const el of candidates) {
            if (el.disabled) continue;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;
            const text = (el.innerText || el.textContent || '').trim();
            if (text.length === 0 || text.length > 60) continue;
            if (re.test(text)) {
                el.scrollIntoView({block: 'center'});
                el.click();
                return text;
            }
        }
        return null;
    })();
    """

    def auto_scroll(self):
        print("🔄 Автоматическая прокрутка страницы...")
        no_progress = 0
        max_no_progress = 4
        prev_count = len(self.all_data)

        for step in range(1, 401):
            try:
                self.driver.execute_script(self.SCROLL_JS)
            except Exception:
                pass
            time.sleep(random.uniform(1.2, 2.4))

            try:
                clicked = self.driver.execute_script(self.CLICK_MORE_JS)
            except Exception:
                clicked = None
            if clicked:
                time.sleep(random.uniform(1.8, 3.2))

            self.find_masters_in_logs()
            time.sleep(random.uniform(0.3, 0.9))

            current_count = len(self.all_data)
            newly_found = current_count - prev_count
            suffix = f"  [клик: «{clicked}»]" if clicked else ""
            print(f"  Шаг {step}: +{newly_found} (всего: {current_count}){suffix}")

            if newly_found > 0 or clicked:
                no_progress = 0
            else:
                no_progress += 1
            prev_count = current_count

            if no_progress >= max_no_progress:
                print("  ✅ Новых профилей нет, кнопок нет — прокрутка завершена.")
                break

    def run(self, url):
        url = self._ensure_url_params(url)
        filename = self._url_to_filename(url)

        print(f"🌐 Загрузка: {url}")
        self.driver.get(url)
        time.sleep(random.uniform(4.5, 6.5))
        print("✅ Страница открыта.")

        self.get_data_from_page_source()
        self.auto_scroll()
        self.get_data_from_page_source()

        print(f"✨ Найдено профилей: {len(self.all_data)}")
        self.save(filename)

    def save(self, filename="profi_masters_all_fields_new.csv"):
        if not self.all_data:
            print("📭 Данные отсутствуют.")
            return

        fieldnames = sorted(self.all_fieldnames)

        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in self.all_data:
                writer.writerow({key: row.get(key, "") for key in fieldnames})

        print(f"🏁 Файл сохранен: {filename}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        user_input = input("URL категории [Enter = default]: ").strip()
        url = user_input if user_input else ProfiFinalUltra.DEFAULT_URL

    scraper = ProfiFinalUltra()
    try:
        scraper.run(url)
    except KeyboardInterrupt:
        print("\nПрервано.")
    finally:
        scraper.driver.quit()
