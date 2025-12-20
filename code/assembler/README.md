# Assembler

The Assembler is a Python-based module responsible for converting approved story assemblies (HTML/CSS) into final PNG image assets for Instagram carousels.

It uses **Playwright** (headless Chromium) to render the HTML templates with high fidelity, ensuring that fonts, layouts, and high-resolution images are captured exactly as designed.

## Directory Structure

```text
code/assembler/
├── main.py              # Entry point script (batch processor)
├── builder.py           # HTML content injection & asset resolution
├── renderer.py          # Playwright rendering engine
├── db_utils.py          # Database operations
├── requirements.txt     # Python dependencies
├── schema.sql           # Database migration(s)
└── output/              # Generated PNGs are saved here by default
    └── <story_id>/
        ├── 01_cover.png
        ├── 02_text.png
        └── ...
```

## Setup

1.  **Install Dependencies**
    The assembler runs in the same virtual environment as the other Python services, or a dedicated one.
    ```bash
    pip install -r requirements.txt
    ```

2.  **Install Playwright Browsers**
    This is required for the rendering engine to work.
    ```bash
    playwright install chromium
    ```

3.  **Environment Variables**
    Ensure a `.env` file exists in `code/` or `code/assembler/` with your database credentials:
    ```
    DATABASE_URL=postgresql://user:pass@host:port/dbname
    ```

## Usage

### Run the Batch Assembler
To process all stories that have been "Approved for Assembly" in the Pre-Assembler dashboard:

```bash
# Run from the project root (code/)
python assembler/main.py
```

### Workflow
1.  **Fetch**: The script queries the database for stories with `approved_for_assembly=True` that haven't been finalized yet.
2.  **Build**: For each story slide, `builder.py` injects the text, images, and metadata into the corresponding HTML template (`template_design/chosen_templates/`).
    *   It resolves local assets (e.g., logos) to absolute file paths.
    *   It extracts base64 thumbnails from the DB and saves them as temporary files.
3.  **Render**: `renderer.py` loads the HTML in a headless browser (1080x1350 viewport) and takes a screenshot.
4.  **Save**: The resulting PNGs are saved to `assembler/output/<story_uuid>/`.
5.  **Finalize**: The `story_assemblies` table is updated:
    *   `status` -> `finalized`
    *   `rendered_files` -> JSON list of the generated PNG paths.

## Troubleshooting

*   **Missing Fonts**: The templates use Google Fonts (Montserrat). Ensure the machine running the assembler has internet access to fetch these fonts during rendering.
*   **Database Connection**: If the script fails to connect, check your `DATABASE_URL` and ensure you are whitelisted if using a cloud DB (e.g., Supabase).
*   **Playwright Errors**: If you see "Executable doesn't exist", run `playwright install chromium` again.

