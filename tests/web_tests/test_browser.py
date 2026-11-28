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
            assert len(routes) == 16
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

@pytest.mark.browser
def test_auditorium_plays_both_treatments_from_the_middle_rows(website_url):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        if not Path(runtime.chromium.executable_path).is_file():
            pytest.skip("Install Chromium with python -m playwright install chromium.")
        with runtime.chromium.launch() as browser:
            page = browser.new_page()
            page.goto(website_url+"#auditorium")
            page.locator("#result").click()
            page.locator("#third-parameter").select_option("middle")
            for roof in ("flat","folded"):
                page.locator("#width").select_option(roof)
                for button in ("#auditorium-play","#auditorium-compare"):
                    page.locator(button).click()
                    page.wait_for_function("auditoriumAudio?.currentTime > 0")
                    assert page.locator("#auditorium-audio-status").text_content() == ""
                    page.locator(button).click()

@pytest.mark.browser
def test_updated_result_views_follow_project_parameters(website_url):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        if not Path(runtime.chromium.executable_path).is_file():
            pytest.skip("Install Chromium with python -m playwright install chromium.")
        with runtime.chromium.launch() as browser:
            page = browser.new_page()
            page.goto(website_url+"#bridge")
            page.locator("#result").click()
            comparison = page.locator("#hanger-loss-comparison")
            assert comparison.is_hidden()
            page.locator("#bridge-condition").select_option("loss")
            assert comparison.is_visible()
            assert comparison.locator("tbody tr").count() == 4
            assert page.evaluate("""() => {
              const marker = parts.at(-1);
              const intact = bridge.cases[project.selected.join("-")].result;
              const remaining = parts.find(part => part.hangerChanges);
              return marker.color && marker.faces.every(face => face.length === 2)
                && new Set(marker.points.filter((_,index) => index % 3 === 2)).size === 1
                && remaining.faces.length === intact.faces.filter(face => face.length === 2).length - 1;
            }""")
            page.locator("#bridge-condition").select_option("intact")
            assert comparison.is_hidden()

            page.locator('nav a[href="#facade"]').click()
            page.locator("#result").click()
            page.locator("#thickness").select_option("excavation")
            assert "A ↑" in page.locator("#readout").inner_text()
            assert "B ↓" in page.locator("#readout").inner_text()
            page.locator("#thickness").select_option("permanent")
            assert "accumulated during excavation" in page.locator("#facade-stage-note").inner_text()

            page.locator('nav a[href="#slab"]').click()
            page.locator("#result").click()
            for opening,description in (("none","25%"),("near","interrupts"),("far","outside")):
                page.locator("#width").select_option(opening)
                assert description in page.locator("#slab-cut-reading").inner_text()
                assert page.locator("#slab-shares tr").count() == 4
                assert page.evaluate("""() => {
                  const cut = parts.find(part => part.cornerStress);
                  return cut.faces.length === cut.cornerStress.length
                    && cut.cornerStress.some(face => new Set(face).size > 1)
                    && parts.some(part => part.material === "slabEast");
                }""")
