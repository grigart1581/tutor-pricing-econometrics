import sys
import csv
import re
import time
import random
import urllib.request
import urllib.error
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


PROFILE_RE = re.compile(r"/profile/([A-Za-z0-9_-]+)")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0 Safari/537.36"
)
EMPTY_PAGE_BYTES = 50_000  # трешхолд для определения пустой страницы

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_aliases(html):
    found = set()
    for m in PROFILE_RE.finditer(html):
        alias = m.group(1)
        if len(alias) < 3:
            continue
        found.add(alias)
    return found


def with_page_param(url, page):
    parsed = urlparse(url)
    qs = [(k, v) for (k, v) in parse_qsl(parsed.query) if k != "p"]
    qs.append(("p", str(page)))
    return urlunparse(parsed._replace(query=urlencode(qs)))


def url_to_filename(url):
    parts = [p for p in urlparse(url).path.strip("/").split("/") if p]
    if "hub" in parts:
        idx = parts.index("hub")
        slug = parts[idx + 1] if idx + 1 < len(parts) else "hub"
    else:
        slug = parts[-1] if parts else "hub"
    return f"profi_links_{slug}.csv"


def save(aliases, filename):
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["alias", "url"])
        for alias in sorted(aliases):
            writer.writerow([alias, f"https://profi.ru/profile/{alias}/"])


def collect(base_url, max_pages=500):
    all_aliases = set()
    consecutive_empty = 0
    max_consecutive_empty = 2

    for page in range(1, max_pages + 1):
        page_url = with_page_param(base_url, page)
        try:
            html = fetch(page_url)
        except urllib.error.HTTPError as e:
            print(f"  p={page}: HTTP {e.code} — стоп.")
            break
        except Exception as e:
            print(f"  p={page}: ошибка ({e}) — стоп.")
            break

        size = len(html)
        if size < EMPTY_PAGE_BYTES:
            consecutive_empty += 1
            print(f"  p={page}: пустая страница ({size:,} байт)")
            if consecutive_empty >= max_consecutive_empty:
                print("Пагинация исчерпана.")
                break
            continue

        page_aliases = extract_aliases(html)
        new = page_aliases - all_aliases
        all_aliases |= page_aliases

        print(f"  p={page}: +{len(new):,} новых (всего {len(all_aliases):,})")

        if not new:
            consecutive_empty += 1
            if consecutive_empty >= max_consecutive_empty:
                print("Новых ссылок нет — завершаем сбор")
                break
        else:
            consecutive_empty = 0

        # вежливая задержка между запросами
        time.sleep(random.uniform(0.4, 1.1))

    return all_aliases


def main():
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        user_input = input("URL категории [Enter = repetitor]: ").strip()
        url = user_input or "https://profi.ru/hub/repetitor/profiles/"

    aliases = collect(url)

    if not aliases:
        print("Ссылки не найдены.")
        return

    filename = url_to_filename(url)
    save(aliases, filename)
    print(f"Сохранено {len(aliases):,} ссылок в {filename}")


if __name__ == "__main__":
    main()
