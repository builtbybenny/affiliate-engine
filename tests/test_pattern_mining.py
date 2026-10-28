from __future__ import annotations

import re
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from core import llm, patterns, planner


def _ngrams(text: str, size: int = 6) -> set[str]:
    words = re.findall(r"[a-z']+", text.lower())
    return {" ".join(words[i:i + size]) for i in range(len(words) - size + 1)}


class PatternMiningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.products = planner.load_products()
        patterns._BRIEF_CACHE.clear()

    def test_rotation_runs_one_day_in_three(self) -> None:
        start = date(2026, 10, 20)
        days = [start + timedelta(days=i) for i in range(9)]
        indexes = [i for i, d in enumerate(days) if patterns.rotation_day(d)]
        self.assertEqual(len(indexes), 3, "exactly one day in three uses the signal")
        self.assertEqual(
            [b - a for a, b in zip(indexes, indexes[1:])], [3, 3],
            "signal days must be evenly spaced, never back to back",
        )

    def test_accounts_are_mapped_per_product(self) -> None:
        systeme = planner.find_by_slug("systeme", self.products)
        self.assertIn("systeme.io", patterns.accounts_for(systeme))
        unknown = {"id": "brand-new-tool", "name": "Brand New Tool"}
        self.assertEqual(patterns.accounts_for(unknown), [])

    def test_unknown_product_produces_no_signal(self) -> None:
        rotation = next(
            date(2026, 10, 20) + timedelta(days=offset) for offset in range(3)
            if patterns.rotation_day(date(2026, 10, 20) + timedelta(days=offset))
        )
        with patch.object(patterns, "_fetch_posts") as fetch:
            self.assertEqual(
                patterns.brief_for({"id": "brand-new-tool", "name": "New"}, rotation), ""
            )
        fetch.assert_not_called()

    def test_dry_runs_never_hit_the_network(self) -> None:
        rotation = next(
            date(2026, 10, 20) + timedelta(days=offset) for offset in range(3)
            if patterns.rotation_day(date(2026, 10, 20) + timedelta(days=offset))
        )
        product = planner.find_by_slug("beehiiv", self.products)
        with patch.object(patterns, "_fetch_posts") as fetch:
            self.assertEqual(patterns.brief_for(product, rotation, allow_network=False), "")
        fetch.assert_not_called()

    def test_strongest_third_of_each_account_is_selected(self) -> None:
        posts = [
            {"caption": f"post {i}", "likes": i, "comments": 0} for i in range(9)
        ]
        top = patterns.top_posts(posts)
        self.assertEqual(len(top), 3)
        self.assertEqual([p["likes"] for p in top], [8, 7, 6])

    def test_hook_kinds_are_classified_from_text(self) -> None:
        cases = {
            "Why is your inbox still empty?": "question",
            "2500 subscribers on the free plan": "number-led",
            "Your newsletter has zero subscribers until you launch.": "you-led",
            "Stop paying for three separate tools": "imperative",
            "Community is the quiet growth channel": "statement",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(patterns.hook_kind(text), expected)

    def test_digest_describes_shape_and_never_quotes_the_source(self) -> None:
        captions = [
            "Stop stitching five dashboards into one spreadsheet every night before bed",
            "Your subscriber list quietly bleeds out whenever the pricing page gets confusing",
            "We redesigned eight dashboard pages and the whole thing finally feels calm now",
            "Most creators quit the newsletter before the first hundred readers ever arrive",
            "Sponsorship revenue is the only channel that compounds while you are asleep",
            "Everyone talks about audience growth but almost nobody measures churn honestly",
        ]
        posts = [
            {"caption": text, "likes": 30 - index, "comments": index % 3}
            for index, text in enumerate(captions)
        ]
        text = patterns.digest(posts, "beehiiv")
        self.assertTrue(text)
        self.assertIn("beehiiv", text)
        self.assertIn("strongest of 6", text)
        self.assertIn("must not be reused", text)
        for caption in captions:
            overlap = _ngrams(caption) & _ngrams(text)
            self.assertEqual(overlap, set(), f"digest quoted the source: {overlap}")

    def test_api_failure_is_silent(self) -> None:
        product = planner.find_by_slug("beehiiv", self.products)
        rotation = next(
            date(2026, 10, 20) + timedelta(days=offset) for offset in range(3)
            if patterns.rotation_day(date(2026, 10, 20) + timedelta(days=offset))
        )
        patterns._BRIEF_CACHE.clear()

        class Response:
            status_code = 500

            @staticmethod
            def json() -> dict:
                return {}

        with patch.object(patterns.requests, "get", return_value=Response()):
            self.assertEqual(patterns.brief_for(product, rotation), "")

        patterns._BRIEF_CACHE.clear()
        with patch.object(patterns.requests, "get", side_effect=RuntimeError("offline")):
            self.assertEqual(patterns.brief_for(product, rotation), "")

    def test_signal_is_fetched_once_and_only_used_as_guidance(self) -> None:
        product = planner.find_by_slug("beehiiv", self.products)
        rotation = next(
            date(2026, 10, 20) + timedelta(days=offset) for offset in range(3)
            if patterns.rotation_day(date(2026, 10, 20) + timedelta(days=offset))
        )
        posts = [
            {"caption": "Your list stays free until you reach the plan limit", "likes": 50, "comments": 2},
            {"caption": "Pricing changes land on the first of the month", "likes": 40, "comments": 1},
            {"caption": "A quiet week for the team", "likes": 2, "comments": 0},
            {"caption": "Welcome to the new home for writers", "likes": 1, "comments": 0},
        ]
        patterns._BRIEF_CACHE.clear()
        with patch.object(patterns, "_fetch_posts", return_value=posts) as fetch:
            first = patterns.brief_for(product, rotation)
            second = patterns.brief_for(product, rotation)
        self.assertTrue(first)
        self.assertEqual(first, second)
        self.assertEqual(fetch.call_count, len(patterns.accounts_for(product)))

        prompts: list[str] = []

        def generate(prompt: str, **kwargs):
            prompts.append(prompt)
            return None

        with patch.object(llm, "available", return_value=True), patch.object(
            llm, "_generate", side_effect=generate
        ):
            llm.write_copy(product, "Quick Start", [], [], "", pattern=first)
            llm.write_copy(product, "Quick Start", [], [], "")
        self.assertIn(first, prompts[0])
        self.assertNotIn(first, prompts[-1])


if __name__ == "__main__":
    unittest.main()
