import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

class Renderer:
    def __init__(self):
        self.playwright = None
        self.browser = None

    async def __aenter__(self):
        logger.info("Starting Playwright browser...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logger.info("Closing Playwright browser...")
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def render_png_bytes(self, html_content: str) -> bytes:
        """
        Render HTML string to PNG bytes (no filesystem writes).
        """
        page = None
        try:
            # Create page with specific viewport for Instagram Story/Carousel
            page = await self.browser.new_page(viewport={"width": 1080, "height": 1350})

            # Set content and wait for network idle (images/fonts loaded)
            await page.set_content(html_content, wait_until="networkidle")

            png_bytes = await page.screenshot(type="png")
            return png_bytes
        except Exception as e:
            logger.error(f"Failed to render slide: {e}")
            raise
        finally:
            if page:
                await page.close()

    async def render(self, html_content: str, output_path: str):
        """
        Renders HTML string to a PNG file at output_path.
        """
        try:
            png_bytes = await self.render_png_bytes(html_content)
            with open(output_path, "wb") as f:
                f.write(png_bytes)
            logger.info(f"Rendered: {output_path}")
        except Exception:
            # render_png_bytes already logged context
            raise




