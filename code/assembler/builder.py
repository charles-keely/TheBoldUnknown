import os
import logging
from typing import Optional, Any, Dict

from bs4 import BeautifulSoup
import re
import base64

logger = logging.getLogger(__name__)


def _repo_root() -> str:
    # assembler/ -> repo root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _normalize_src(src: str, template_dir: str, repo_root: str) -> str:
    """
    Convert known asset URL patterns to something Playwright can load when using page.set_content.

    - http(s)://... stays as-is
    - data:... stays as-is
    - file://... stays as-is
    - /template-assets/... maps to template_design/... (file://)
    - relative paths are left relative (resolved via injected <base href="file://.../chosen_templates/">)
    """
    if not src:
        return src

    s = src.strip()
    if s.startswith(("http://", "https://", "data:", "file://")):
        return s

    if s.startswith("/template-assets/"):
        # Pre-Assembler serves template assets from template_design/
        # /template-assets/img/foo.png -> template_design/img/foo.png
        rel = s[len("/template-assets/") :]
        abs_path = os.path.join(repo_root, "template_design", rel)
        return f"file://{abs_path}"

    if s.startswith("/"):
        abs_path = os.path.join(repo_root, s.lstrip("/"))
        return f"file://{abs_path}"

    # Relative paths like ../img/TBU_Logo4.png:
    # In practice, Chromium + page.set_content can be finicky about resolving
    # relative URLs (even with a <base href="file://..."> tag), so we eagerly
    # convert to absolute file:// URLs.
    abs_path = os.path.normpath(os.path.join(template_dir, s))
    return f"file://{abs_path}"


_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(?P<url>[^'\"\)]+)\1\s*\)", re.IGNORECASE)


def _guess_mime_type(path: str) -> str:
    ext = (os.path.splitext(path)[1] or "").lower()
    if ext == ".png":
        return "image/png"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    if ext == ".gif":
        return "image/gif"
    if ext == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"


def _file_url_to_data_url(url: str) -> str | None:
    """
    Convert file:// URLs into data: URLs.

    Why:
    Chromium + Playwright `page.set_content()` can be inconsistent about loading file:// resources
    referenced by <img src="file://..."> or CSS url(file://...). Inlining template assets
    (logos/arrows/overlays) makes rendering deterministic.
    """
    if not url or not isinstance(url, str) or not url.startswith("file://"):
        return None
    path = url[len("file://") :]
    if not path or not os.path.exists(path) or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            data = f.read()
        mime = _guess_mime_type(path)
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None


def _normalize_css_urls(css_text: str, template_dir: str, repo_root: str) -> str:
    """
    Normalize url(...) references inside CSS strings (style tags and inline style attrs).

    We only rewrite absolute-like paths that Playwright cannot resolve under page.set_content:
    - /template-assets/... -> file://<repo_root>/template_design/...
    - /... -> file://<repo_root>/...

    We leave relative urls alone so they resolve via <base href="file://...chosen_templates/">.
    """
    if not css_text:
        return css_text

    def _repl(m: re.Match) -> str:
        raw = (m.group("url") or "").strip()
        normalized = _normalize_src(raw, template_dir, repo_root)
        inlined = _file_url_to_data_url(normalized)
        if inlined:
            normalized = inlined
        # Preserve original quoting style
        q = m.group(1) or ""
        return f"url({q}{normalized}{q})"

    return _CSS_URL_RE.sub(_repl, css_text)


class SlideBuilder:
    """
    Build a single-slide HTML string from a chosen template + slide content.

    IMPORTANT: This implementation does not write any temporary image files.
    """

    def __init__(self, working_dir: Optional[str] = None):
        self.working_dir = working_dir
        self.repo_root = _repo_root()
        self.template_dir = os.path.join(self.repo_root, "template_design", "chosen_templates")

    def build_slide(self, slide: Dict[str, Any], index: int) -> str:
        template_key = (slide or {}).get("template") or ""
        if not template_key:
            raise ValueError("Slide is missing 'template'")

        template_file = template_key if template_key.endswith(".html") else f"{template_key}.html"
        template_path = os.path.join(self.template_dir, template_file)
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template not found: {template_path}")

        with open(template_path, "r", encoding="utf-8") as f:
            html = f.read()

        soup = BeautifulSoup(html, "html.parser")

        # Ensure relative assets resolve by default (../img/...)
        if soup.head and not soup.head.find("base"):
            base = soup.new_tag("base", href=f"file://{self.template_dir}/")
            soup.head.insert(0, base)

        # Normalize static asset references inside the template (logos, overlays, etc.)
        # Many templates use absolute paths like /template-assets/img/... which will NOT
        # resolve under page.set_content unless we rewrite them to file:// paths.
        for tag in soup.find_all(src=True):
            try:
                normalized = _normalize_src(str(tag.get("src", "")), self.template_dir, self.repo_root)
                # Inline local template assets (logos/arrows/etc.) so they always render.
                inlined = _file_url_to_data_url(normalized)
                tag["src"] = inlined or normalized
            except Exception:
                # best-effort; don't fail rendering due to a single bad src
                continue

        for tag in soup.find_all(href=True):
            try:
                tag["href"] = _normalize_src(str(tag.get("href", "")), self.template_dir, self.repo_root)
            except Exception:
                continue

        # Normalize CSS url(...) references for absolute paths
        for style_tag in soup.find_all("style"):
            if style_tag.string:
                style_tag.string.replace_with(
                    _normalize_css_urls(str(style_tag.string), self.template_dir, self.repo_root)
                )

        for tag in soup.find_all(style=True):
            try:
                tag["style"] = _normalize_css_urls(str(tag.get("style", "")), self.template_dir, self.repo_root)
            except Exception:
                continue

        content = (slide or {}).get("content") or {}
        slide_type = (slide or {}).get("type") or ""

        # Best-effort domain tag injection (some templates leave this for postMessage)
        domain_tag = content.get("domain_tag")
        if domain_tag:
            meta = soup.select_one(".meta-data") or soup.select_one(".domain-tag-line")
            if meta and not meta.get_text(strip=True):
                meta.string = str(domain_tag)

        if slide_type == "cover":
            title = content.get("title") or ""
            subtitle = content.get("subtitle") or ""
            h1 = soup.select_one("h1.main-title")
            if h1 is not None:
                h1.string = str(title)
            p = soup.select_one("p.subtitle")
            if p is not None:
                p.string = str(subtitle)

            thumb = content.get("thumbnail_url") or content.get("image_url")
            if thumb:
                bg = soup.select_one("img.bg-image")
                if bg is not None:
                    bg["src"] = _normalize_src(str(thumb), self.template_dir, self.repo_root)

                    # Apply non-destructive crop/zoom if present
                    # Matches logic in pre_assembler/static/js/template-wrapper.js
                    try:
                        zoom_raw = float(content.get("thumbnail_zoom", 1.0))
                        x_raw = float(content.get("thumbnail_offset_x", 0.0))
                        y_raw = float(content.get("thumbnail_offset_y", 0.0))

                        # Clamp values
                        zoom = max(1.0, min(4.0, zoom_raw))
                        x = max(-2000.0, min(2000.0, x_raw))
                        y = max(-2000.0, min(2000.0, y_raw))

                        if zoom != 1.0 or x != 0.0 or y != 0.0:
                            # Apply transform. Origin center is default for transform, but good to be explicit if CSS allows.
                            # We inject inline style.
                            transform = f"translate({x}px, {y}px) scale({zoom})"
                            existing_style = bg.get("style", "")
                            bg["style"] = f"{existing_style}; transform-origin: center center; transform: {transform};".lstrip("; ")
                    except (ValueError, TypeError):
                        pass

        elif slide_type == "text":
            text = (content.get("text") or "").strip()
            col = soup.select_one(".text-column")
            if col is not None:
                col.clear()
                if text:
                    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
                    if not parts:
                        parts = [text]
                    for part in parts:
                        ptag = soup.new_tag("p")
                        ptag.string = part
                        col.append(ptag)

        elif slide_type == "photo":
            image_url = content.get("image_url") or ""
            caption = content.get("caption") or ""
            source = content.get("source") or ""

            img = soup.select_one("#main-photo") or soup.select_one("img.display-photo")
            if img is not None and image_url:
                img["src"] = _normalize_src(str(image_url), self.template_dir, self.repo_root)

            cap_el = soup.select_one("#caption-text")
            if cap_el is not None:
                cap_el.string = str(caption)

            src_el = soup.select_one("#source-text")
            if src_el is not None:
                src_el.string = str(source)

        elif slide_type == "closing":
            sources = content.get("primary_sources") or []
            container = soup.select_one(".sources-container")
            list_el = soup.select_one(".sources-list")
            if list_el is not None:
                list_el.clear()
                if sources:
                    for s in sources:
                        item = soup.new_tag("div")
                        item["class"] = "source-item"
                        item.string = str(s)
                        list_el.append(item)
                else:
                    if container is not None:
                        # Hide the block if no sources exist
                        container["style"] = (container.get("style", "") + ";display:none;").lstrip(";")

        else:
            # Unknown slide type; return template as-is.
            logger.warning(f"Unknown slide type '{slide_type}', returning template without injection.")

        return str(soup)


