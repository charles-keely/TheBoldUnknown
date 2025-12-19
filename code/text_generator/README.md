# Text Generator

This service generates the final text content for TheBoldUnknown Instagram stories, including:
1.  **Story Slides**: 7-9 narrative slides based on research.
2.  **Cover Options**: 6 viral hook options derived from the generated story.
3.  **Photo Captions**: Documentary-style captions for approved photos.

**Model Used:** GPT-5.2

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Environment Variables**:
    Ensure your `.env` file contains:
    - `OPENAI_API_KEY`
    - `DATABASE_URL` (or `POSTGRES_HOST`, `POSTGRES_USER`, etc.)

## Usage

Run the generator using `main.py`.

### Basic Usage (Process Next Available Story)
By default, this processes the first "completed" story research that hasn't been generated yet.
```bash
python main.py
```

### Dry Run (Testing)
To test the output without saving to the database, use `--dry-run`. It's highly recommended to use `--out` to save the result to a Markdown file for easy reading.

```bash
python main.py --dry-run --out test_output.md
```

### Process a Specific Story
To generate text for a specific story (even if it's already been generated or to select a specific one from the queue), use `--story-id`.

```bash
python main.py --story-id <UUID> --dry-run --out specific_story.md
```

### Random Story (Great for Testing)
To test the generator on a RANDOM completed story (generated or not), use `--random`. This is useful for checking variety without manually finding IDs.

```bash
python main.py --random --dry-run --out random_test.md
```

### Options
- `--limit <N>`: Process only N stories.
- `--story-id <UUID>`: Target a specific story ID.
- `--random`: Select a random completed story.
- `--dry-run`: Do not save results to the database.
- `--out <file.md>`: Write the generated content to a Markdown file.

## Testing Flow

1.  Identify a story ID you want to test (see Database or use a helper script).
2.  Run with dry-run:
    ```bash
    python main.py --story-id <ID> --dry-run --out test.md
    ```
3.  Review `test.md`.
4.  If satisfied, run without dry-run to save to DB:
    ```bash
    python main.py --story-id <ID>
    ```
