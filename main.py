import asyncio
import re
from contextlib import asynccontextmanager

import feedparser
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import FileResponse


HN_RSS_URL = "https://news.ycombinator.com/rss"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={}"

news = []
last_error = None


async def fetch_latest_news():
    global news, last_error

    try:
        async with httpx.AsyncClient(
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "Chrome/139.0 Safari/537.36"
                )
            },
        ) as client:

            # ---------------------------------------------------------
            # 1. Fetch Hacker News RSS
            # ---------------------------------------------------------
            response = await client.get(HN_RSS_URL)
            response.raise_for_status()

            feed = feedparser.parse(response.text)

            stories = []

            # ---------------------------------------------------------
            # 2. Process newest 5 stories
            # ---------------------------------------------------------
            for entry in feed.entries[:5]:

                title = entry.get(
                    "title",
                    "No title"
                )

                # RSS "comments" contains the HN discussion URL
                comments_url = entry.get(
                    "comments",
                    ""
                )

                match = re.search(
                    r"[?&]id=(\d+)",
                    comments_url
                )

                if not match:
                    print(
                        f"Could not determine HN ID for: {title}"
                    )
                    continue

                story_id = match.group(1)

                hn_url = HN_ITEM_URL.format(story_id)

                # External article URL
                article_url = entry.get(
                    "link",
                    hn_url
                )

                story = {
                    "id": story_id,
                    "title": title,
                    "url": article_url,
                    "hn_url": hn_url,
                    "by": "unknown",
                    "score": 0,
                }

                # -----------------------------------------------------
                # 3. Fetch HN discussion page
                # -----------------------------------------------------
                try:
                    story_response = await client.get(
                        hn_url
                    )
                    story_response.raise_for_status()

                    soup = BeautifulSoup(
                        story_response.text,
                        "html.parser"
                    )

                    story_row = soup.find(
                        "tr",
                        {
                            "class": "athing",
                            "id": story_id,
                        },
                    )
                    if story_row:

                        # The metadata is in the next <tr>
                        subtext_row = story_row.find_next_sibling(
                            "tr"
                        )

                        if subtext_row:

                            # -----------------------------
                            # Score
                            # -----------------------------
                            score_element = (
                                subtext_row.select_one(
                                    ".score"
                                )
                            )

                            if score_element:
                                score_text = (
                                    score_element.get_text(
                                        strip=True
                                    )
                                )

                                score_match = re.search(
                                    r"(\d+)",
                                    score_text
                                )

                                if score_match:
                                    story["score"] = int(
                                        score_match.group(1)
                                    )

                            # -----------------------------
                            # Author
                            # -----------------------------
                            author_element = (
                                subtext_row.select_one(
                                    ".hnuser"
                                )
                            )

                            if author_element:
                                story["by"] = (
                                    author_element.get_text(
                                        strip=True
                                    )
                                )

                    else:
                        print(
                            f"Could not find story "
                            f"{story_id} in HN page"
                        )

                except Exception as e:
                    print(
                        f"Could not fetch metadata "
                        f"for {story_id}: {e}"
                    )

                stories.append(story)

            # ---------------------------------------------------------
            # 4. Save results
            # ---------------------------------------------------------
            news = stories
            last_error = None

            print(
                f"Successfully fetched "
                f"{len(news)} Hacker News stories"
            )

    except Exception as e:

        last_error = (
            f"{type(e).__name__}: {e}"
        )

        print(
            f"Hacker News fetch failed: "
            f"{last_error}"
        )

    except Exception as e:

        last_error = (
            f"{type(e).__name__}: {e}"
        )

        print(
            f"Hacker News fetch failed: "
            f"{last_error}"
        )


async def daily_news_task():
    while True:

        try:
            await fetch_latest_news()

        except Exception as e:
            print(
                f"Background task error: "
                f"{type(e).__name__}: {e}"
            )

        # Run once every 24 hours
        await asyncio.sleep(
            60 * 60 * 24
        )


@asynccontextmanager
async def lifespan(app: FastAPI):

    # Fetch immediately when the application starts
    await fetch_latest_news()

    # Start daily background task
    task = asyncio.create_task(
        daily_news_task()
    )

    yield

    # Stop background task
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Hacker News Daily",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------
# Homepage
# ---------------------------------------------------------------------

@app.get("/")
async def homepage():
    return FileResponse(
        "static/index.html"
    )


# ---------------------------------------------------------------------
# API
# ---------------------------------------------------------------------

@app.get("/api/news")
async def get_news():
    return {
        "count": len(news),
        "news": news,
        "error": last_error,
    }


# ---------------------------------------------------------------------
# Manual refresh
# ---------------------------------------------------------------------

@app.post("/api/refresh")
async def refresh_news():
    await fetch_latest_news()

    return {
        "message": "News refreshed",
        "count": len(news),
        "error": last_error,
    }
