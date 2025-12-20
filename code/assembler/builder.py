import os
import re
import base64
import logging
import mimetypes
from bs4 import BeautifulSoup
from db_utils import get_thumbnail_data

logger = logging.getLogger(__name__)

# Constants
CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(CODE_DIR, "template_design", "chosen_templates")
IMG_DIR = os.path.join(CODE_DIR, "template_design", "img")

class SlideBuilder:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        # Ensure assets dir exists
        self.assets_dir = os.path.join(output_dir, "assets")
        os.makedirs(self.assets_dir, exist_ok=True)

    def _file_to_data_uri(self, file_path: str) -> str:
        """
        Convert a local image file to a data URI so Playwright can render it reliably.
        """
        try:
            if not file_path or not os.path.exists(file_path):
                return ""
            mime, _ = mimetypes.guess_type(file_path)
            if not mime:
                # Default; most of our assets are pngs.
                mime = "image/png"
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except Exception as e:
            logger.error(f"Failed to encode image as data URI: {file_path} ({e})")
            return ""

    def _resolve_template_path(self, template_name: str) -> str:
        # Map template enum/names to filenames
        # e.g. "cover3" -> "cover3.html"
        filename = f"{template_name}.html"
        path = os.path.join(TEMPLATE_DIR, filename)
        if not os.path.exists(path):
            # Fallback or error
            logger.error(f"Template not found: {path}")
            raise FileNotFoundError(f"Template {filename} not found")
        return path

    def _save_image_asset(self, url_or_id: str) -> str:
        """
        Resolves an image reference.
        - If it's a local template asset (logo/arrow/background), embed as data URI.
        - If it's a thumbnail API URL, fetch base64 from DB and embed as data URI.
        - If it's http URL, return as-is (Playwright handles it).
        
        Returns: A renderable src string (data:... or http(s)://...).
        """
        if not url_or_id:
            return ""

        # Check for TBU thumbnail API pattern
        # e.g. /api/thumbnails/UUID/image
        thumb_match = re.search(r'/api/thumbnails/([a-f0-9-]+)/image', url_or_id)
        if thumb_match:
            thumbnail_id = thumb_match.group(1)
            b64_data = get_thumbnail_data(thumbnail_id)
            if b64_data:
                # Stored as raw base64 in DB; thumbnails are PNGs in our pipeline.
                return f"data:image/png;base64,{b64_data}"
        
        # If it's a local static path (from pre-assembler context)
        # e.g. /template-assets/img/foo.png
        if url_or_id.startswith("/template-assets/img/"):
            filename = url_or_id.replace("/template-assets/img/", "")
            local_path = os.path.join(IMG_DIR, filename)
            if os.path.exists(local_path):
                data_uri = self._file_to_data_uri(local_path)
                return data_uri or ""
                
        # If it's already an absolute path or http
        if url_or_id.startswith("http"):
            return url_or_id

        if url_or_id.startswith("file://"):
            local_path = url_or_id.replace("file://", "")
            data_uri = self._file_to_data_uri(local_path)
            return data_uri or ""
            
        return url_or_id

    def _clamp_number(self, value, min_v: float, max_v: float, fallback: float) -> float:
        try:
            n = float(value)
        except Exception:
            return fallback
        if n != n:  # NaN
            return fallback
        return max(min_v, min(max_v, n))

    def build_slide(self, slide_data: dict, index: int, *, slide_number: int, total_slides: int) -> str:
        """
        Injects content into template and returns the HTML string.
        """
        template_name = slide_data.get("template")
        if not template_name:
            logger.warning(f"Slide {index} has no template specified. Skipping.")
            return ""

        try:
            template_path = self._resolve_template_path(template_name)
            with open(template_path, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f, "html.parser")
        except Exception as e:
            logger.error(f"Failed to load template {template_name}: {e}")
            return ""

        content = slide_data.get("content", {})

        # 1. Fix relative asset paths in the template itself
        # e.g. src="../img/logo.png" -> data:image/... (embedded)
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src.startswith("../img/"):
                filename = src.replace("../img/", "")
                abs_path = os.path.join(IMG_DIR, filename)
                data_uri = self._file_to_data_uri(abs_path)
                if data_uri:
                    img["src"] = data_uri

        # 2. Inject Content based on slide type/template
        
        # Common: Domain Tag
        domain = content.get("domain_tag")
        if domain:
            # Prefer templates that expose a dedicated span for domain tag
            domain_span = soup.select_one(".domain-tag-line")
            if domain_span:
                domain_span.string = str(domain).upper()
            else:
                meta = soup.select_one(".meta-data")
                if meta:
                    # Replace existing content (usually comments)
                    meta.clear()
                    meta.string = str(domain).upper()

        # Page Number (Common)
        # Pre-assembler sets these dynamically in the browser; for server-side rendering
        # we must inject them ourselves.
        if isinstance(slide_number, int) and isinstance(total_slides, int) and total_slides > 0:
            # Editorial/photos templates: "02 / 08"
            pn = soup.select_one(".page-number")
            if pn:
                if slide_number == total_slides:
                    pn.string = f"FINAL // {total_slides}"
                else:
                    pn.string = f"{slide_number:02d} / {total_slides:02d}"

            # Cover template: left footer contains "01/08<br>SWIPE FOR MORE"
            footer_left = soup.select_one(".footer-left")
            if footer_left:
                # Final slide should display "FINAL // N" only (closing template uses .footer-final).
                if slide_number == total_slides:
                    footer_final = soup.select_one(".footer-final") or footer_left
                    footer_final.clear()
                    footer_final.string = f"FINAL // {total_slides}"
                else:
                    # Preserve the second line if present.
                    # Typical structure:
                    #   01/08<br>
                    #   SWIPE FOR MORE
                    second_line = "SWIPE FOR MORE"
                    # Extract existing text lines if any
                    existing_text = footer_left.get_text("\n").strip()
                    lines = [ln.strip() for ln in existing_text.split("\n") if ln.strip()]
                    if len(lines) >= 2:
                        second_line = lines[1]
                    footer_left.clear()
                    footer_left.append(BeautifulSoup(f"{slide_number:02d}/{total_slides:02d}<br>{second_line}", "html.parser"))

        # Closing slide primary sources (closing1.html)
        if str(template_name).lower().startswith("closing"):
            sources = content.get("primary_sources") or []
            urls = content.get("primary_source_urls") or []

            container = soup.select_one(".sources-container")
            list_el = soup.select_one(".sources-list")
            label = soup.select_one(".sources-label")

            # If no primary sources, hide/remove the entire section.
            if not sources:
                if container:
                    container.decompose()
                elif label:
                    # Fallback: remove label + list if present
                    label.decompose()
                    if list_el:
                        list_el.decompose()
            else:
                if list_el:
                    list_el.clear()
                    for i, src in enumerate(sources):
                        span = soup.new_tag("span")
                        span["class"] = "source-item"
                        text = str(src).strip()
                        # If a URL exists, we still render as text (PNG), but include it for clarity.
                        url = urls[i] if i < len(urls) else None
                        if url and str(url).strip():
                            span.string = f"{text}"
                        else:
                            span.string = text
                        list_el.append(span)
        
        # TEXT Slides (Editorial)
        if slide_data.get("type") == "text":
            text_body = content.get("text")
            if text_body:
                # Match the pre-assembler wrapper behavior:
                # - Prefer .text-column (editorial3) and render paragraphs split on double newlines.
                # - Fallback: inject with <br> if we only have a single <p>-style container.
                col = soup.select_one(".text-column")
                if col:
                    col.clear()
                    raw = str(text_body)
                    paragraphs = [p.strip() for p in re.split(r"\n\n+", raw) if p.strip()]
                    for para in paragraphs:
                        p = soup.new_tag("p")
                        p.string = para
                        col.append(p)
                else:
                    # Editorial1/2 might use .content-body or .content-text
                    target = (
                        soup.select_one(".content-text")
                        or soup.select_one("p.body")
                        or soup.find("p")
                    )
                    if target:
                        html_content = str(text_body).replace("\n", "<br>")
                        target.clear()
                        target.append(BeautifulSoup(html_content, "html.parser"))
                    else:
                        logger.warning(f"Could not find text container for template {template_name}")

        # COVER Slides
        elif slide_data.get("type") == "cover":
            title = content.get("title")
            subtitle = content.get("subtitle")
            thumb_url = content.get("thumbnail_url")
            zoom_raw = content.get("thumbnail_zoom")
            x_raw = content.get("thumbnail_offset_x")
            y_raw = content.get("thumbnail_offset_y")

            if title:
                h1 = soup.select_one("h1.main-title")
                if h1:
                    # Match the in-browser wrapper behavior: allow newlines.
                    h1.clear()
                    title_html = str(title).replace("\n", "<br>")
                    h1.append(BeautifulSoup(title_html, "html.parser"))
                else:
                    logger.warning(f"Could not find h1.main-title in {template_name}")
            
            if subtitle is not None:
                p = soup.select_one("p.subtitle")
                if p:
                    p.string = str(subtitle)
            
            if thumb_url:
                bg = soup.select_one("img.bg-image")
                if bg:
                    abs_url = self._save_image_asset(thumb_url)
                    if abs_url:
                        bg["src"] = abs_url

                    # Apply non-destructive "crop" controls (zoom + pan) exactly like the
                    # pre-assembler iframe wrapper does.
                    zoom = self._clamp_number(zoom_raw, 1.0, 4.0, 1.0)
                    x = self._clamp_number(x_raw, -2000.0, 2000.0, 0.0)
                    y = self._clamp_number(y_raw, -2000.0, 2000.0, 0.0)
                    # NOTE: CSS transform functions are applied right-to-left; this ordering keeps
                    # translate values from being scaled.
                    extra_style = f"transform-origin: center center; transform: translate({x}px, {y}px) scale({zoom}); will-change: transform;"
                    existing_style = bg.get("style", "")
                    bg["style"] = (existing_style + ("; " if existing_style else "") + extra_style).strip()

        # PHOTO Slides
        elif slide_data.get("type") == "photo":
            image_url = content.get("image_url")
            caption = content.get("caption")
            source = content.get("source")

            if image_url:
                # Photos templates usually have a .photo-frame img or .display-photo
                img = soup.select_one(".photo-frame img") or soup.select_one("img.display-photo") or soup.select_one("img.main-photo")
                if img:
                    abs_url = self._save_image_asset(image_url)
                    if abs_url:
                        img["src"] = abs_url
            
            if caption:
                cap = soup.select_one(".caption-text") or soup.select_one("#caption-text") or soup.select_one(".caption")
                if cap:
                    cap.string = caption
            
            if source:
                src_el = soup.select_one(".source-text") or soup.select_one("#source-text") or soup.select_one(".source")
                if src_el:
                    src_el.string = source

        # CLOSING Slides
        elif slide_data.get("type") == "text" and "closing" in str(template_name):
            # Closing1 has primary sources list
            sources = content.get("primary_sources") or []
            urls = content.get("primary_source_urls") or []
            
            list_container = soup.select_one(".sources-list") or soup.select_one("ul")
            if list_container and sources:
                list_container.clear()
                for i, s in enumerate(sources):
                    li = soup.new_tag("li")
                    if i < len(urls) and urls[i]:
                        li.string = s
                    else:
                        li.string = s
                    list_container.append(li)

        return str(soup)

