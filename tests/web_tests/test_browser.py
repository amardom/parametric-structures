from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

WEBSITE = Path(__file__).resolve().parents[2]/"website"

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,format,*args):
        pass

@pytest.fixture
def website_url():
    if not any(WEBSITE.glob("*cases.js")):
        pytest.skip("Generate the website with python website/build_data.py.")
    handler = partial(QuietHandler,directory=str(WEBSITE))
    with ThreadingHTTPServer(("127.0.0.1",0),handler) as server:
        thread = Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join()

@pytest.mark.browser
def test_all_generated_projects_render_in_chromium(website_url):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        if not Path(runtime.chromium.executable_path).is_file():
            pytest.skip("Install Chromium with python -m playwright install chromium.")
        with runtime.chromium.launch() as browser:
            page = browser.new_page()
            errors = []
            page.on("pageerror",lambda error:errors.append(str(error)))
            page.on("response",lambda response:errors.append(f"{response.status} {response.url}")
                    if response.status >= 400 and not response.url.endswith("/favicon.ico") else None)
            page.goto(website_url)
            nav = page.locator('nav a[href^="#"]')
            routes = nav.evaluate_all("links => links.map(link => link.hash)")
            assert len(routes) == 12
            for route in routes:
                page.locator(f'nav a[href="{route}"]').click()
                page.locator("#plans").click()
                page.wait_for_function(
                    "route => {const img = document.querySelector('#plan-sheet'); "
                    "return img.src.includes('/plans/' + route.slice(1) + '/') && img.complete && img.naturalWidth > 0;}",
                    arg=route,
                )
                page.locator("#cad").click()
                page.locator("#viewport").wait_for(state="visible")
                page.wait_for_function("parts.length > 0 && parts.every(part => part.points.length > 0)")
                page.locator("#result").click()
                page.wait_for_function("!document.querySelector('#readout').hidden && "
                                       "document.querySelector('#readout').textContent.trim().length > 0")
                before = page.locator("#width").input_value()
                choices = page.locator("#width option").evaluate_all("items => items.map(item => item.value)")
                alternative = next(choice for choice in choices if choice != before)
                page.locator("#width").select_option(alternative)
                assert page.evaluate("project.selected[0]") == alternative,route
                assert page.evaluate("parts.length > 0 && parts.every(part => part.points.length > 0)"),route
                page.locator("#plans").click()
                page.wait_for_function(
                    "() => {const img = document.querySelector('#plan-sheet'); "
                    "return img.complete && img.naturalWidth > 0 && img.src.endsWith(project.selected.join('-') + '-plan.svg');}"
                )
                assert not errors,(route,errors)
