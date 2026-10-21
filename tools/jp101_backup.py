"""Local, interactive backup of user-selected JapanesePod101 pages and download links."""
import hashlib
import json
import re
import time
import queue
import threading
from collections import deque
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1] / ".jp101-local"
MEDIA = {".mp3", ".m4a", ".mp4", ".pdf", ".zip", ".csv", ".tsv", ".xlsx"}


def list_site_tabs(context):
    """Do not evaluate titles: a tab can navigate while its menu is displayed."""
    pages = [page for page in context.pages if not page.is_closed() and site_url(page.url)]
    for index, page in enumerate(pages, 1):
        parsed = urlsplit(page.url)
        print(f"{index}: {parsed.hostname}{parsed.path}")
    return pages


def read_selected_page(page, action, browser_error):
    """Retry a read-only operation if navigation destroys its JavaScript context."""
    for attempt in range(3):
        if page.is_closed():
            print("Tab da dong. Hay mo lai trang va nhap lai lenh.")
            return False
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            if not site_url(page.url):
                print("Tab da chuyen sang trang khac. Hay quay lai JapanesePod101 va thu lai.")
                return False
            action(page)
            return True
        except browser_error as exc:
            transient = any(message in str(exc).lower() for message in (
                "execution context was destroyed", "cannot find context", "frame was detached",
            ))
            if not transient or attempt == 2:
                print("Chua doc duoc trang. Hay doi trang tai xong roi nhap lai lenh; cua so Edge van duoc giu mo.")
                return False
            print("Trang dang chuyen huong, dang thu doc lai...")
    return False


def browser_input(context, prompt):
    """Keep Playwright processing browser events while the terminal awaits input."""
    results = queue.Queue()

    def read():
        try:
            results.put((input(prompt), None))
        except Exception as exc:
            results.put((None, exc))

    threading.Thread(target=read, daemon=True).start()
    while True:
        try:
            value, error = results.get_nowait()
            if error:
                raise error
            return value
        except queue.Empty:
            pages = [page for page in context.pages if not page.is_closed()]
            if pages:
                page = pages[0]
                try:
                    page.wait_for_timeout(100)
                except Exception:
                    if not page.is_closed():
                        raise
            else:
                time.sleep(0.1)


def learning_url(url):
    """Follow discovered learning routes, never account actions or arbitrary query actions."""
    if not site_url(url):
        return None
    parsed = urlsplit(url)
    path = unquote(parsed.path).lower()
    if not re.match(
        r"^/(dashboard|lesson|lessons|lesson-library|learning-paths?|pathways?|"
        r"vocabulary|wordbank|word-bank|flashcards?|my-vocabulary|my-wordbank|"
        r"my-flashcards|my-progress|progress|learning-center|japanese-vocabulary-lists)(/|$)", path
    ):
        return None
    if re.search(r"(?:^|[/_-])(delete|remove|reset|logout|purchase|subscribe|complete|mark)(?:$|[/_-])", path):
        return None
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    # Unknown query parameters can invoke state-changing endpoints. Only retain
    # known navigation parameters; do not transform an action URL into a page.
    navigation = {"page", "p", "level", "category", "category_id", "season", "season_id",
                  "lesson_id", "id", "list_id", "pathway_id", "sort", "order", "limit", "offset"}
    if any(key.lower() not in navigation and not key.lower().startswith("utm_") for key, _ in pairs):
        return None
    pairs = sorted((key, value) for key, value in pairs if not key.lower().startswith("utm_"))
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", urlencode(pairs), ""))


def site_url(url):
    parsed = urlsplit(url)
    return parsed.scheme == "https" and (
        parsed.hostname == "japanesepod101.com"
        or (parsed.hostname or "").endswith(".japanesepod101.com")
    )


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")[:100]
    if not value or value.split(".")[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        value = "file_" + value
    return value


def download_candidate(link):
    parsed = urlsplit(link["url"])
    if parsed.scheme != "https":
        return False
    suffix = Path(unquote(parsed.path)).suffix.lower()
    return suffix in MEDIA or link.get("download", False) or bool(
        re.search(r"\bdownload\b", link.get("text", ""), re.I)
    )


def write_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def export_structure(page):
    """Collect DOM shapes without account text, input values, cookies or URL values."""
    if not site_url(page.url):
        print("Hay mo trang JapanesePod101 truoc.")
        return
    data = page.evaluate("""() => {
      const labels = ['download', 'export', 'next', 'more', 'lesson', 'vocabulary',
                      'flashcard', 'progress', 'word bank', 'load more'];
      function selector(el) {
        const parts = [];
        while (el && el !== document.body) {
          const tag = el.tagName.toLowerCase();
          const siblings = [...el.parentElement.children].filter(x => x.tagName === el.tagName);
          parts.unshift(tag + ':nth-of-type(' + (siblings.indexOf(el) + 1) + ')');
          el = el.parentElement;
        }
        return 'body > ' + parts.join(' > ');
      }
      return {
        counts: Object.fromEntries(['a', 'button', 'table', 'iframe', 'video', 'audio', 'select']
          .map(tag => [tag, document.querySelectorAll(tag).length])),
        controls: [...document.querySelectorAll('a,button,[role="button"]')].slice(0, 2500).map(el => {
          const text = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
          return {selector: selector(el), tag: el.tagName.toLowerCase(),
            categories: labels.filter(label => text.includes(label)),
            visible: !!el.getClientRects().length,
            download_attribute: el.hasAttribute('download')};
        }),
        // URLs are sanitized in Python and are never written as received.
        hrefs: [...document.querySelectorAll('a[href]')].map(a => a.href)
      };
    }""")
    routes = set()
    for url in data.pop("hrefs"):
        if not site_url(url):
            continue
        parsed = urlsplit(url)
        # Keep only known route names; all other segments and all values disappear.
        known = {"dashboard", "lesson", "lessons", "lesson-library", "learning-paths",
                 "pathway", "pathways", "vocabulary", "wordbank", "word-bank", "flashcards",
                 "my-vocabulary", "my-wordbank", "my-flashcards", "progress", "my-progress",
                 "learning-center", "japanese-vocabulary-lists"}
        parts = [part if part in known else ":segment" for part in parsed.path.split("/") if part]
        keys = sorted({key for key, _ in parse_qsl(parsed.query)
                       if key in {"page", "p", "id", "lesson_id", "category_id", "level", "offset"}})
        routes.add("/" + "/".join(parts) + ("?" + "&".join(key + "=:value" for key in keys) if keys else ""))
    data["route_shapes"] = sorted(routes)
    folder = ROOT / "structures"
    folder.mkdir(exist_ok=True)
    target = folder / f"structure-{time.time_ns()}.json"
    write_json(target, data)
    print(f"Da luu cau truc da luoc bo thong tin dang nhap: {target}")


def capture(page, manifest):
    if not site_url(page.url):
        print("Chi quet trang HTTPS cua JapanesePod101.")
        return
    page.wait_for_timeout(500)
    data = page.evaluate("""() => ({
      title: document.title,
      text: document.body.innerText,
      tables: [...document.querySelectorAll('table')].map(t =>
        [...t.rows].map(r => [...r.cells].map(c => c.innerText))),
      links: [...document.querySelectorAll('a[href]')].map(a => ({
        url: a.href, text: a.innerText || a.getAttribute('aria-label') || '',
        download: a.hasAttribute('download')
      }))
    })""")
    key = hashlib.sha256(page.url.encode()).hexdigest()[:16]
    folder = ROOT / "pages" / key
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "content.txt").write_text(data["text"], encoding="utf-8")
    write_json(folder / "page.json", {"url": page.url, **data})
    manifest["pages"][page.url] = {"title": data["title"], "folder": str(folder.relative_to(ROOT))}
    count = 0
    for link in data["links"]:
        link["url"] = urljoin(page.url, link["url"])
        if download_candidate(link):
            old = manifest["downloads"].get(link["url"], {})
            manifest["downloads"][link["url"]] = {**link, "source": page.url, **old}
            count += 1
    write_json(ROOT / "manifest.json", manifest)
    print(f"Da luu noi dung hien thi va bang du lieu; tim thay {count} lien ket tai.")
    return data["links"]


def auto_backup(context, manifest, max_pages=5000):
    """Resume a persistent queue of links actually exposed by learning pages."""
    state_path = ROOT / "crawl.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
        "pending": [], "done": [], "errors": {}, "scroll_limits": []
    }
    state.setdefault("scroll_limits", [])
    done = set(state["done"])
    queue = deque(state["pending"])
    known = set(queue) | done

    def enqueue(url):
        candidate = learning_url(url)
        if candidate and candidate not in known:
            known.add(candidate)
            queue.append(candidate)

    for tab in context.pages:
        enqueue(tab.url)
    enqueue("https://www.japanesepod101.com/dashboard")
    # Reuse links collected manually, including vocabulary/progress starting pages.
    for record in manifest["pages"].values():
        saved = ROOT / record["folder"] / "page.json"
        if saved.exists():
            for link in json.loads(saved.read_text(encoding="utf-8")).get("links", []):
                enqueue(link["url"])

    def checkpoint():
        state["pending"] = list(queue)
        state["done"] = sorted(done)
        write_json(state_path, state)

    checkpoint()
    page = context.new_page()
    visited = 0
    stop_reason = "queue_exhausted"
    try:
        while queue and visited < max_pages:
            url = queue[0]  # Remove only after successful capture, so interruption is resumable.
            print(f"Tu dong: da luu {len(done)} trang; con {len(queue)} lien ket cho.")
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
                if response and response.status in (401, 403, 429):
                    stop_reason = f"http_{response.status}"
                    break
                if response and response.status >= 400:
                    raise RuntimeError(f"HTTP {response.status}")
                if not learning_url(page.url) or page.locator('input[type="password"]:visible').count():
                    stop_reason = "login_or_redirect_requires_attention"
                    break
                # Collect links during scrolling, including virtualized lists.
                previous = None
                stable = 0
                for _ in range(20):
                    snapshot = page.evaluate("""() => ({
                      height: document.documentElement.scrollHeight,
                      links: [...document.querySelectorAll('a[href]')].map(a => a.href)
                    })""")
                    for link in snapshot["links"]:
                        enqueue(link)
                    signature = (snapshot["height"], tuple(snapshot["links"]))
                    stable = stable + 1 if signature == previous else 0
                    if stable >= 2:
                        break
                    previous = signature
                    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                    page.wait_for_timeout(1000)
                else:
                    if url not in state["scroll_limits"]:
                        state["scroll_limits"].append(url)
                links = capture(page, manifest) or []
                for link in links:
                    enqueue(link["url"])
                done.add(url)
                state["errors"].pop(url, None)
                queue.popleft()
                visited += 1
            except Exception as exc:
                state["errors"][url] = type(exc).__name__
                stop_reason = "page_error_retry_on_next_run"
                print(f"Tam dung do loi {type(exc).__name__}; hang doi da duoc giu lai.")
                break
            finally:
                checkpoint()
            time.sleep(2)
        if queue and visited >= max_pages:
            stop_reason = "page_limit_run_auto_again_to_continue"
    except KeyboardInterrupt:
        stop_reason = "interrupted_resume_with_auto"
    finally:
        checkpoint()
        page.close()
        write_json(ROOT / "coverage.json", {
            "saved_learning_pages": len(done), "pending_learning_pages": len(queue),
            "stop_reason": stop_reason, "errors": len(state["errors"]),
            "pages_reaching_scroll_limit": len(state["scroll_limits"]),
            "full_account_export_verified": False,
            "limitations": ["Only discovered HTML learning links are followed",
                            "JavaScript-only pagination, exports and hidden API data are not collected",
                            "Flashcards and progress are readable snapshots, not a restorable export"],
        })
    print(f"Da dung quet: {stop_reason}. Xem coverage.json de biet pham vi da luu.")
    if stop_reason == "queue_exhausted" or stop_reason.startswith("page_limit"):
        download_all(context, manifest)
    else:
        print("Chua tai tiep. Xu ly dang nhap/loi roi nhap auto de tiep tuc.")


def download_all(context, manifest):
    folder = ROOT / "downloads"
    folder.mkdir(exist_ok=True)
    for url, item in manifest["downloads"].items():
        if item.get("file") and (ROOT / item["file"]).is_file():
            continue
        response = None
        try:
            response = context.request.get(url, timeout=120000)
            if response.status in (401, 403, 429):
                print(f"Dung tai: HTTP {response.status}. Kiem tra quyen tai/dang nhap hoac thu lai sau.")
                break
            if not response.ok:
                raise RuntimeError(f"HTTP {response.status}")
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type or "application/json" in content_type:
                raise RuntimeError("Lien ket tra ve trang/API, khong phai tep tai xuong")
            name = safe_name(unquote(Path(urlsplit(url).path).name))
            digest = hashlib.sha256(url.encode()).hexdigest()[:12]
            target = folder / f"{digest}-{name}"
            body = response.body()
            if not body:
                raise RuntimeError("Tep rong")
            temporary = target.with_suffix(target.suffix + ".part")
            temporary.write_bytes(body)
            temporary.replace(target)
            item["file"] = str(target.relative_to(ROOT))
            item["bytes"] = len(body)
            item.pop("error", None)
            print(f"Da tai: {target.name}")
        except Exception as exc:
            # Do not print signed URLs or request details from exceptions.
            item["error"] = type(exc).__name__
            print(f"Khong tai duoc mot tep ({type(exc).__name__}); da ghi trang thai de thu lai.")
        finally:
            if response is not None:
                response.dispose()
            write_json(ROOT / "manifest.json", manifest)
        time.sleep(2)


def main():
    from playwright.sync_api import Error as BrowserError, sync_playwright

    ROOT.mkdir(exist_ok=True)
    manifest_path = ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        "pages": {}, "downloads": {}
    }
    print("Dang nhap truc tiep trong cua so Microsoft Edge. Khong nhap mat khau vao terminal.")
    print("Phien ban: Edge / navigation-retry-v1")
    print("Day la ho so Edge rieng: ban can dang nhap lai, du da dang nhap trong Edge thuong.")
    print("Neu dang nhap loi, dung lai va ghi thong bao loi. Chua nhap auto khi chua dang nhap xong.")
    print("Mo trang bai hoc/tu vung/tien do, mo muc Download va cuon tai het du lieu can luu.")
    print("Lenh: auto = tu dong quet va tai; scan = luu mot tab; structure = xuat cau truc; download = tai tep; quit = thoat.")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(ROOT / "edge-profile"), channel="msedge", headless=False, accept_downloads=True,
            downloads_path=str(ROOT / "downloads"),
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto("https://www.japanesepod101.com/dashboard", wait_until="domcontentloaded")
            except BrowserError:
                print("Chua mo duoc dashboard. Ban co the mo trang thu cong trong Edge roi tiep tuc.")
            while True:
                command = browser_input(context, "auto / scan / structure / download / quit > ").strip().lower()
                if command == "quit":
                    break
                if command == "auto":
                    auto_backup(context, manifest)
                elif command == "download":
                    download_all(context, manifest)
                elif command in {"scan", "structure"}:
                    pages = list_site_tabs(context)
                    if not pages:
                        print("Chua co tab JapanesePod101.")
                        continue
                    selection = browser_input(context, "So tab can luu [1]: ").strip() or "1"
                    if selection.isdigit() and 1 <= int(selection) <= len(pages):
                        selected = pages[int(selection) - 1]
                        if command == "structure":
                            read_selected_page(selected, export_structure, BrowserError)
                        else:
                            read_selected_page(selected, lambda tab: capture(tab, manifest), BrowserError)
        finally:
            context.close()
    print(f"Du lieu da luu tai: {ROOT}")


if __name__ == "__main__":
    main()
