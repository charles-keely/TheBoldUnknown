# Photo Researcher

This module is an automated system for finding, verifying, and curating images for stories in "TheBoldUnknown" pipeline.

It sits downstream of the `story_researcher` module. Once a story has been fully researched (status: `completed`), this system finds visual assets to accompany it.

## Features

- **Intelligent Query Generation**: Uses GPT-5.1 to generate specific, high-yield search queries based on the story's "ground truth."
- **Deep Verification**: Scrapes the source webpage of every image to cross-reference captions and context.
- **AI Analysis**: Uses GPT-5.1 Vision to "see" the image and verify it matches the story details.
- **Quality Control**: Scores images on Relevance, Verifiability, and Usability.
- **Aesthetic Tagging**: Labels images as "cinematic," "archival," "clean," etc.
- **AI Detection**: Flags images that appear to be AI-generated.

## Setup

1.  **Dependencies**:
    Ensure you have the required Python packages installed:
    ```bash
    pip install -r photo_researcher/requirements.txt
    ```

2.  **Environment Variables**:
    Your root `.env` file must contain:
    - `OPENAI_API_KEY`: For GPT-5.1.
    - `GOOGLE_CUSTOM_SEARCH_KEY`: Google Cloud API Key.
    - `GOOGLE_SEARCH_ENGINE_ID`: Programmable Search Engine ID (CX).
    - `POSTGRES_*`: Database credentials.

3.  **Database**:
    The system uses the `story_photos` table. If it doesn't exist, the code will attempt to create it automatically, but you can also run the schema manually from `photo_researcher/schema.sql`.

## Usage

### Run the Worker

To process the queue of stories that need photos:

```bash
python3 -m photo_researcher.main
```

**Options:**

- `--limit N`: Process only the next `N` stories (default: 5).
  ```bash
  python3 -m photo_researcher.main --limit 20
  ```

- `--single`: Process a single story and exit (useful for testing).
  ```bash
  python3 -m photo_researcher.main --single
  ```

- `--save-output`: Saves a detailed Markdown report (`photo_research_report.md`) of the run, including rejected images and analysis reasoning. Highly recommended for debugging.
  ```bash
  python3 -m photo_researcher.main --single --save-output
  ```

## How It Works (The Pipeline)

1.  **Fetch**: Finds stories in the DB with status `completed` that have fewer than 2 approved photos.
2.  **Generate**: Creates 1-3 specific search queries (e.g., "Stora Förvar cave excavation 1891").
3.  **Search**: Queries Google Images (Custom Search JSON API) and fetches top 5 results per query.
4.  **Validate**: Checks if the image URL is accessible and valid.
5.  **Scrape**: Visits the webpage hosting the image to scrape captions, title, and context.
6.  **Analyze**: Sends the Image + Story Research + Source Context to GPT-5.1 Vision.
    - Scores: Relevance (0-10), Verifiability (0-10), Usability (0-10).
    - Checks: AI Generation?
7.  **Decide**:
    - **Approved**: If Relevance ≥ 7 AND Verifiability ≥ 6 AND Usability ≥ 6 AND NOT AI.
    - **Rejected**: Otherwise.
8.  **Save**: Stores the image, analysis, and metadata in the `story_photos` table.
