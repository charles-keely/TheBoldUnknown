import asyncio
import os
from builder import SlideBuilder
from renderer import Renderer

OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

async def main():
    story_id = "_smoke_test"
    story_dir = os.path.join(OUTPUT_ROOT, story_id)
    os.makedirs(story_dir, exist_ok=True)

    builder = SlideBuilder(story_dir)

    slide = {
        "type": "cover",
        "template": "cover3",
        "visible": True,
        "content": {
            "title": "SMOKE TEST TITLE",
            "subtitle": "Subtitle should appear here.",
            "thumbnail_url": "/template-assets/img/cover_image.png",
            "domain_tag": "EMERGENT TECHNOLOGY",
        },
    }

    html = builder.build_slide(slide, 0)

    out_path = os.path.join(story_dir, "01_cover.png")

    async with Renderer() as renderer:
        await renderer.render(html, out_path)

    print(out_path)

if __name__ == "__main__":
    asyncio.run(main())

