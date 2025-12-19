"""
Preview Generator - Creates an HTML preview page to compare generated thumbnails.
"""

import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Path to template assets (relative from output directory)
TEMPLATE_IMG_PATH = "../../template_design/img"


def generate_preview_html(story_data, thumbnails, output_path=None):
    """
    Generates an HTML preview page to compare thumbnail options.
    
    Args:
        story_data: dict with hook_title, subtitle, domain_tag
        thumbnails: list of dicts with concept_number, concept_type, image_url/image_path, scene_description
        output_path: Where to save the HTML. Defaults to output/test_preview.html
    
    Returns:
        str: Path to the generated HTML file
    """
    
    hook_title = story_data.get('hook_title', 'TITLE HERE')
    subtitle = story_data.get('subtitle', 'Subtitle goes here.')
    domain_tag = story_data.get('domain_tag', 'Domain')
    
    # Format title for HTML (convert to line breaks for display)
    # Split long titles into multiple lines
    title_words = hook_title.split()
    title_lines = []
    current_line = []
    
    for word in title_words:
        current_line.append(word)
        if len(' '.join(current_line)) > 15 or len(current_line) >= 3:
            title_lines.append(' '.join(current_line))
            current_line = []
    
    if current_line:
        title_lines.append(' '.join(current_line))
    
    title_html = '<br>'.join(title_lines)
    
    # Build image data for JavaScript
    image_data = []
    for thumb in thumbnails:
        img_path = thumb.get('image_url') or thumb.get('image_path', '')
        
        # Make path relative if it's absolute
        if img_path and os.path.isabs(img_path):
            # Try to make it relative to output dir
            try:
                output_dir = os.path.dirname(output_path) if output_path else os.path.join(os.path.dirname(__file__), 'output')
                img_path = os.path.relpath(img_path, output_dir)
            except:
                pass
        
        image_data.append({
            'number': thumb.get('concept_number', 0),
            'type': thumb.get('concept_type', 'unknown'),
            'path': img_path,
            'description': thumb.get('scene_description', '')[:200]
        })
    
    # Generate the HTML
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>TheBoldUnknown - Thumbnail Preview</title>
  
  <!-- Montserrat -->
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;800&display=swap" rel="stylesheet">

  <style>
    * {{
      box-sizing: border-box;
    }}
    
    html, body {{
      margin: 0;
      padding: 0;
      min-height: 100vh;
      background: #111;
      font-family: "Montserrat", sans-serif;
    }}

    body {{
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 20px;
      color: #fff;
    }}

    /* Control Panel */
    .control-panel {{
      position: fixed;
      top: 20px;
      right: 20px;
      background: rgba(0,0,0,0.9);
      border: 1px solid rgba(255,255,255,0.2);
      border-radius: 12px;
      padding: 20px;
      z-index: 1000;
      min-width: 280px;
    }}
    
    .control-panel h3 {{
      margin: 0 0 15px 0;
      font-size: 14px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: rgba(255,255,255,0.6);
    }}
    
    .concept-btn {{
      display: block;
      width: 100%;
      padding: 12px 16px;
      margin-bottom: 10px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.2);
      border-radius: 8px;
      color: #fff;
      font-family: inherit;
      font-size: 13px;
      text-align: left;
      cursor: pointer;
      transition: all 0.2s;
    }}
    
    .concept-btn:hover {{
      background: rgba(255,255,255,0.1);
      border-color: rgba(255,255,255,0.4);
    }}
    
    .concept-btn.active {{
      background: rgba(255,255,255,0.15);
      border-color: #fff;
    }}
    
    .concept-btn .number {{
      font-weight: 700;
      margin-right: 8px;
    }}
    
    .concept-btn .type {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      opacity: 0.7;
    }}
    
    .concept-description {{
      margin-top: 15px;
      padding-top: 15px;
      border-top: 1px solid rgba(255,255,255,0.1);
      font-size: 12px;
      line-height: 1.5;
      color: rgba(255,255,255,0.6);
      max-height: 150px;
      overflow-y: auto;
    }}

    /* Cover Preview */
    :root {{
      --frame-width: 1080px;
      --frame-height: 1350px;
      --margin: 70px;
      --ui-color: rgba(255, 255, 255, 0.9);
      --dim-color: rgba(255, 255, 255, 0.5);
    }}

    .scale-wrapper {{
      width: var(--frame-width);
      height: var(--frame-height);
      transform-origin: center center;
      margin: 40px 0;
    }}

    .slide {{
      position: relative;
      width: 1080px;
      height: 1350px;
      background: #05060a;
      color: #fff;
      overflow: hidden;
      box-shadow: 0 0 50px rgba(0,0,0,0.8);
      border-radius: 8px;
    }}

    .bg-image {{
      position: absolute;
      top: 0; left: 0; width: 100%; height: 100%;
      object-fit: cover;
      opacity: 0.9;
      transition: opacity 0.3s;
    }}

    .vignette {{
      position: absolute;
      top: 0; left: 0; width: 100%; height: 100%;
      background: radial-gradient(circle at center, transparent 30%, rgba(0,0,0,0.8) 100%);
      z-index: 1;
      mix-blend-mode: multiply;
    }}

    .bottom-gradient {{
      position: absolute;
      bottom: 0; left: 0; width: 100%; height: 55%;
      background: linear-gradient(to bottom, transparent 0%, rgba(0,0,0,0.6) 50%, rgba(0,0,0,0.95) 100%);
      z-index: 2;
      pointer-events: none;
    }}
    
    .ui-layer {{
      position: relative;
      z-index: 10;
      width: 100%;
      height: 100%;
      box-sizing: border-box;
      padding: var(--margin);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}

    .header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-top: 1px solid rgba(255,255,255,0.3);
      padding-top: 20px;
    }}

    .logo {{
      width: 90px;
      height: auto;
      filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));
    }}

    .meta-data {{
      text-align: right;
      font-size: 18px;
      font-weight: 500;
      letter-spacing: 0.15em;
      line-height: 1.4;
      color: var(--dim-color);
      text-transform: uppercase;
    }}

    .center-stage {{
      flex-grow: 1;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      align-items: center;
      text-align: center;
      margin-bottom: 20px;
      padding-bottom: 0;
    }}

    .main-title {{
      font-weight: 800;
      font-size: 100px;
      line-height: 0.95;
      text-transform: uppercase;
      letter-spacing: -0.03em;
      text-shadow: 0 10px 40px rgba(0,0,0,0.7);
      margin: 0;
    }}

    .subtitle {{
      font-weight: 500;
      font-size: 24px;
      line-height: 1.4;
      max-width: 600px;
      margin-top: 30px;
      color: rgba(255, 255, 255, 0.9);
      text-shadow: 0 2px 10px rgba(0,0,0,0.8);
    }}

    .title-deco {{
      width: 2px;
      height: 120px;
      background: linear-gradient(to bottom, transparent, #fff, transparent);
      margin: 0 40px;
      opacity: 0.5;
    }}
    
    .title-row {{
      display: flex;
      align-items: center;
    }}

    .footer {{
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      border-bottom: 1px solid rgba(255,255,255,0.3);
      padding-bottom: 20px;
    }}

    .footer-left {{
      font-size: 16px;
      letter-spacing: 0.1em;
      color: var(--dim-color);
      text-transform: uppercase;
    }}

    .arrow-container {{
      animation: floatRight 2s ease-in-out infinite;
    }}
    
    .swipe-arrow {{
      width: 50px;
      height: auto;
      filter: brightness(0) invert(1);
      opacity: 0.9;
    }}

    @keyframes floatRight {{
      0%, 100% {{ transform: translateX(0); }}
      50% {{ transform: translateX(8px); }}
    }}

    .mark {{
      position: absolute;
      width: 20px;
      height: 20px;
      border-color: rgba(255,255,255,0.4);
      border-style: solid;
      pointer-events: none;
    }}
    .mark-tl {{ top: 50px; left: 50px; border-width: 2px 0 0 2px; }}
    .mark-tr {{ top: 50px; right: 50px; border-width: 2px 2px 0 0; }}
    .mark-bl {{ bottom: 50px; left: 50px; border-width: 0 0 2px 2px; }}
    .mark-br {{ bottom: 50px; right: 50px; border-width: 0 2px 2px 0; }}

    /* Info Panel */
    .info-panel {{
      position: fixed;
      bottom: 20px;
      left: 20px;
      background: rgba(0,0,0,0.9);
      border: 1px solid rgba(255,255,255,0.2);
      border-radius: 12px;
      padding: 20px;
      max-width: 400px;
    }}
    
    .info-panel h4 {{
      margin: 0 0 10px 0;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: rgba(255,255,255,0.5);
    }}
    
    .info-panel p {{
      margin: 0;
      font-size: 11px;
      line-height: 1.6;
      color: rgba(255,255,255,0.7);
    }}

    /* Keyboard hint */
    .keyboard-hint {{
      position: fixed;
      bottom: 20px;
      right: 20px;
      font-size: 11px;
      color: rgba(255,255,255,0.4);
    }}
    
    kbd {{
      background: rgba(255,255,255,0.1);
      padding: 2px 6px;
      border-radius: 4px;
      margin: 0 2px;
    }}
  </style>
</head>
<body>

  <!-- Control Panel -->
  <div class="control-panel">
    <h3>Select Thumbnail</h3>
    {generate_buttons_html(image_data)}
    <div class="concept-description" id="description">
      Select a concept to see its description.
    </div>
  </div>

  <!-- Cover Preview -->
  <div class="scale-wrapper">
    <div class="slide">
      
      <!-- Background Image (switchable) -->
      <img id="bg-image" src="{image_data[0]['path'] if image_data else ''}" alt="Cover" class="bg-image">
      <div class="vignette"></div>
      <div class="bottom-gradient"></div>

      <!-- Technical Corner Marks -->
      <div class="mark mark-tl"></div>
      <div class="mark mark-tr"></div>
      <div class="mark mark-bl"></div>
      <div class="mark mark-br"></div>

      <!-- Main UI -->
      <div class="ui-layer">
        
        <!-- Top Row -->
        <div class="header">
          <img src="{TEMPLATE_IMG_PATH}/TBU_Logo4.png" alt="TBU" class="logo">
          <div class="meta-data">
            {domain_tag.upper()}<br>
            Analysis
          </div>
        </div>

        <!-- Center Content -->
        <div class="center-stage">
          <div class="title-row">
            <div class="title-deco"></div> 
            
            <h1 class="main-title">
              {title_html}
            </h1>

            <div class="title-deco"></div>
          </div>

          <p class="subtitle">
            {subtitle}
          </p>
        </div>

        <!-- Bottom Row -->
        <div class="footer">
          <div class="footer-left">
            01/08<br>
            SWIPE FOR MORE
          </div>
          <div class="arrow-container">
            <img src="{TEMPLATE_IMG_PATH}/next.png" alt="Next" class="swipe-arrow">
          </div>
        </div>

      </div>

    </div>
  </div>

  <!-- Info Panel -->
  <div class="info-panel">
    <h4>Story Info</h4>
    <p><strong>Title:</strong> {hook_title}</p>
    <p><strong>Domain:</strong> {domain_tag}</p>
    <p><strong>Generated:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
  </div>

  <!-- Keyboard Hint -->
  <div class="keyboard-hint">
    Press <kbd>1</kbd> <kbd>2</kbd> <kbd>3</kbd> to switch concepts
  </div>

  <script>
    // Image data
    const images = {generate_js_array(image_data)};
    
    let currentIndex = 0;
    
    function selectConcept(index) {{
      if (index < 0 || index >= images.length) return;
      
      currentIndex = index;
      const img = images[index];
      
      // Update background image
      document.getElementById('bg-image').src = img.path;
      
      // Update description
      document.getElementById('description').textContent = img.description || 'No description available.';
      
      // Update button states
      document.querySelectorAll('.concept-btn').forEach((btn, i) => {{
        btn.classList.toggle('active', i === index);
      }});
    }}
    
    // Keyboard navigation
    document.addEventListener('keydown', (e) => {{
      if (e.key >= '1' && e.key <= '3') {{
        selectConcept(parseInt(e.key) - 1);
      }} else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {{
        selectConcept((currentIndex + 1) % images.length);
      }} else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {{
        selectConcept((currentIndex - 1 + images.length) % images.length);
      }}
    }});
    
    // Initialize
    selectConcept(0);

    // Scaling
    function resizeSlide() {{
      const baseWidth = 1080;
      const baseHeight = 1350;
      const availableWidth = window.innerWidth - 350; // Account for control panel
      const availableHeight = window.innerHeight - 100;
      const scale = Math.min(
        availableWidth / baseWidth,
        availableHeight / baseHeight,
        0.8 // Max scale
      );
      const wrapper = document.querySelector('.scale-wrapper');
      if (wrapper) {{
        wrapper.style.transform = `scale(${{scale}})`;
      }}
    }}
    window.addEventListener('load', resizeSlide);
    window.addEventListener('resize', resizeSlide);
  </script>

</body>
</html>
'''
    
    # Save the HTML
    if not output_path:
        output_dir = os.path.join(os.path.dirname(__file__), 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, 'test_preview.html')
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    logger.info(f"Preview saved to {output_path}")
    return output_path


def generate_buttons_html(image_data):
    """Generate HTML for concept buttons."""
    buttons = []
    for img in image_data:
        buttons.append(f'''
    <button class="concept-btn" onclick="selectConcept({img['number'] - 1})">
      <span class="number">{img['number']}</span>
      <span class="type">{img['type']}</span>
    </button>''')
    return '\n'.join(buttons)


def generate_js_array(image_data):
    """Generate JavaScript array literal for image data."""
    items = []
    for img in image_data:
        desc = img['description'].replace("'", "\\'").replace('\n', ' ')
        items.append(f"{{ number: {img['number']}, type: '{img['type']}', path: '{img['path']}', description: '{desc}' }}")
    return '[' + ', '.join(items) + ']'
