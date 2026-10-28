from __future__ import annotations

import json
import os
import random
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from core import briefs, copywriter, llm, planner


class ContentQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.products = planner.load_products()
        self.future_product = {
            "id": "future-product",
            "name": "Future Product",
            "benefits": "One clear workflow|A current plan benefit",
            "specs": "One verifiable capability",
            "price": "0",
            "currency": "USD",
            "trial": "Free plan",
            "alt": "Old Rival",
        }

    def test_template_hooks_are_dynamic_across_current_and_future_products(self) -> None:
        products = [*self.products, self.future_product]
        for product in products:
            with self.subTest(product=product["id"]):
                hook = copywriter.pick_hook("product_spotlight", product, random.Random(3))
                self.assertTrue(copywriter.hook_coherent(hook, product, from_ai=False))
                self.assertIn(product["name"].casefold(), hook.casefold())
                self.assertTrue(copywriter.punchy(hook))
                self.assertLessEqual(len(hook.split()), 10)
                self.assertTrue(any(detail.casefold() in hook.casefold() for detail in (
                    *planner.parse_benefits(product), product.get("specs", ""), product.get("trial", "")
                ) if detail.strip()))
                self.assertNotIn((product.get("alt") or "").lower(), hook.lower())

    def test_template_slides_are_unique_and_use_one_clear_cta(self) -> None:
        for product in [*self.products, self.future_product]:
            with self.subTest(product=product["id"]):
                slides = copywriter.build_slide_texts(product, "product_spotlight", random.Random(2))
                self.assertEqual(len({slide.strip().casefold() for slide in slides}), len(slides))
                self.assertEqual(slides[-1], "Check the current terms via the link in bio")
                self.assertFalse(any("Save this" in slide for slide in slides))

    def test_template_caption_uses_catalog_facts_and_discloses_affiliate_link(self) -> None:
        for product in [*self.products, self.future_product]:
            with self.subTest(product=product["id"]):
                caption = copywriter.build_caption(
                    product, "product_spotlight", datetime.now().date(),
                    random.Random(7), include_hashtags=False,
                )
                self.assertIn(product["name"], caption)
                self.assertIn(copywriter.DISCLOSURE, caption)
                self.assertLessEqual(len(caption), 2200)
                self.assertNotIn(product["alt"].lower(), caption.lower())

    def test_hook_choice_ignores_model_self_scores_and_rejects_cliches(self) -> None:
        candidates = [
            {"text": "Your newsletter plan costs $0 today", "score": 1},
            {"text": "Unlock the game-changing secret", "score": 100},
            {"text": "A useful change for creators", "score": 99},
        ]
        first = llm.pick_retention_hook(candidates)
        reverse_scores = [dict(c, score=100 - c["score"]) for c in candidates]
        second = llm.pick_retention_hook(reverse_scores)
        self.assertEqual(first, second)
        self.assertNotIn("unlock", first.lower())
        self.assertNotIn("game-changing", first.lower())
        self.assertLessEqual(len(first.split()), 10)

    def test_validate_copy_rejects_unsupported_claims_and_patterns(self) -> None:
        product = self.products[0]
        good = {
            "hook": f"A free plan for {product['name']}.",
            "slides": ["Build a first funnel", "Keep your email together"],
            "framework": "value_stack",
            "caption": (
                f"A free plan for {product['name']}.\n"
                f"{product['name']} lists a free plan in its current product details.\n"
                "You can start with one simple funnel.\n"
                "Start with the free plan through the link in bio.\n\n"
                + copywriter.DISCLOSURE
            ),
        }
        self.assertTrue(llm.validate_copy(good, product)[0])
        bad_cases = [
            dict(good, caption=good["caption"].replace("one simple funnel", "10x revenue")),
            dict(good, caption=good["caption"].replace("You can start", "I personally earned $500")),
            dict(good, caption=good["caption"].replace("A free plan", "It's not expensive, it's revolutionary")),
            dict(good, slides=["Build a first funnel", "Build a first funnel"]),
            dict(good, caption=good["caption"].replace(copywriter.DISCLOSURE, "")),
            dict(good, caption=good["caption"].replace("Start with the free plan through the link in bio.", "Thoughts? Like, share, and tag a friend.")),
            dict(good, caption=good["caption"].replace("A free plan for", "A free plan from Kajabi for")),
        ]
        for bad in bad_cases:
            with self.subTest(copy=bad):
                self.assertFalse(llm.validate_copy(bad, product)[0])

    def test_write_copy_keeps_interface_and_returns_none_without_gemini_key(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            result = llm.write_copy(
                self.future_product, "The Quick Win", [], [], "",
            )
        self.assertIsNone(result)

    def test_write_copy_uses_one_correction_then_safe_fallback(self) -> None:
        product = self.future_product
        malformed = '{"not":"valid output"}'
        prompt_calls: list[str] = []

        def generate(prompt: str, **kwargs) -> str:
            prompt_calls.append(prompt)
            return malformed

        with patch.object(llm, "available", return_value=True), patch.object(llm, "_generate", side_effect=generate):
            result = llm.write_copy(product, "The Quick Win", [], [], "")
        self.assertIsNone(result)
        self.assertEqual(len(prompt_calls), 2)

    def test_briefs_with_missing_or_expired_timestamp_are_not_served_stale(self) -> None:
        product = self.future_product
        stale = {
            "updated": "old",
            "products": {
                product["id"]: {
                    "built": (datetime.now(timezone.utc) - timedelta(days=14)).isoformat(),
                    "keywords": ["old phrase"],
                    "facts": ["Expired discount (source: unknown)"],
                    "angles": ["Old promo angle"],
                }
            },
        }
        missing_date = {"updated": "old", "products": {product["id"]: {"facts": ["stale"]}}}
        for saved in (stale, missing_date):
            with self.subTest(saved=saved), patch.object(briefs, "_load", return_value=saved):
                with patch.object(briefs, "build", return_value=None):
                    self.assertEqual(briefs.get(product, refresh=True), {})

    def test_uncited_cached_facts_and_angles_are_not_passed_as_claims(self) -> None:
        product = self.future_product
        brief = {
            "keywords": ["workflow software"],
            "facts": ["10x revenue (source: unverified)"],
            "objections": ["Will this be difficult to start?"],
            "angles": ["Secret tool earns thousands"],
            "built": datetime.now(timezone.utc).isoformat(),
        }
        with patch.object(llm, "available", return_value=True), patch.object(
            llm, "_generate", return_value=None
        ) as generated:
            result = llm.write_copy(product, "The Quick Win", [], [], "", brief=brief)
        self.assertIsNone(result)
        self.assertEqual(generated.call_count, 1)
        prompt = generated.call_args.args[0]
        self.assertNotIn("10x revenue (source: unverified)", prompt)
        self.assertNotIn("Secret tool earns thousands", prompt)
        self.assertIn("workflow software", prompt)

    def test_recent_openings_come_from_published_captions_and_are_product_scoped(self) -> None:
        product = planner.find_by_slug("systeme", self.products)
        hooks = copywriter.recent_hooks(product)
        self.assertTrue(hooks, "published captions should give the engine memory")
        archive = copywriter.ARCHIVE_DIR
        paths = [
            *(archive / "carousels").glob("*_systeme/caption.txt"),
            *(archive / "reels").glob("*_systeme_caption.txt"),
        ]
        openings = set()
        for path in paths:
            first = next(
                (line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()),
                "",
            )
            if first:
                openings.add(first)
        self.assertLessEqual(set(hooks), openings)
        self.assertEqual(copywriter.recent_hooks({"id": "brand-new-tool"}), [])

    def test_fallback_hooks_vary_and_avoid_recent_openings(self) -> None:
        for product in self.products:
            with self.subTest(product=product["id"]):
                used = set(copywriter.recent_hooks(product))
                seen = set()
                for seed in range(25):
                    hook = copywriter.pick_hook("product_spotlight", product, random.Random(seed))
                    self.assertNotIn(hook, used, "fallback repeated a recently published opening")
                    self.assertTrue(copywriter.punchy(hook))
                    self.assertLessEqual(len(hook.split()), 10)
                    seen.add(hook)
                self.assertGreater(len(seen), 1, "seeded runs should not always pick one sentence")

    def test_fallback_caption_has_one_next_step_and_no_internal_labels(self) -> None:
        for product in [*self.products, self.future_product]:
            with self.subTest(product=product["id"]):
                caption = copywriter.build_caption(
                    product, "product_spotlight", date(2026, 10, 28), random.Random(4),
                    include_hashtags=False,
                )
                self.assertEqual(caption.count("link in bio"), 1)
                self.assertEqual(caption.count(copywriter.DISCLOSURE), 1)
                self.assertNotIn("Listed trial terms", caption)
                self.assertNotIn("Save this", caption)

    def test_fallback_copy_survives_a_row_with_no_details(self) -> None:
        sparse = {
            "id": "bare", "name": "Bare Tool", "benefits": "", "specs": "",
            "price": "", "currency": "", "trial": "", "alt": "",
        }
        hook = copywriter.pick_hook("product_spotlight", sparse, random.Random(1))
        self.assertIn("Bare Tool", hook)
        self.assertTrue(copywriter.punchy(hook))
        slides = copywriter.build_slide_texts(sparse, "product_spotlight", random.Random(1))
        self.assertGreaterEqual(len(slides), 2)
        caption = copywriter.build_caption(
            sparse, "product_spotlight", date(2026, 10, 28), random.Random(1),
            include_hashtags=False,
        )
        self.assertIn("Bare Tool", caption)
        self.assertIn(copywriter.DISCLOSURE, caption)

    def test_numeric_claims_are_compared_by_value_not_formatting(self) -> None:
        product = planner.find_by_slug("beehiiv", self.products)
        self.assertFalse(llm._unsupported_numbers("Newsletters up to 2500 subscribers free", product))
        self.assertFalse(llm._unsupported_numbers("Newsletters up to 2,500 subscribers free", product))
        self.assertTrue(llm._unsupported_numbers("Newsletters up to 10,000 subscribers free", product))

    def test_gate_rejects_bait_second_action_and_unnamed_copy(self) -> None:
        product = self.products[0]
        hook = f"A free plan for {product['name']}."
        caption = (
            f"{hook}\n"
            f"{product['name']} lists a free plan in its current product details.\n"
            "Start with the free plan through the link in bio.\n\n"
            + copywriter.DISCLOSURE
        )
        good = {
            "hook": hook,
            "slides": ["Build a first funnel", "Keep your email together"],
            "framework": "value_stack",
            "caption": caption,
        }
        self.assertTrue(llm.validate_copy(good, product)[0])
        rejected = {
            "engagement bait": dict(good, caption=caption.replace("Start with the free plan", "Save this for later. Start with the free plan")),
            "second action": dict(good, caption=caption.replace("Start with the free plan", "Then comment below. Start with the free plan")),
            "too many CTAs": dict(
                good,
                caption=caption.replace(
                    copywriter.DISCLOSURE,
                    "Grab it from the link in bio, then the link in bio again.\n\n" + copywriter.DISCLOSURE,
                ),
            ),
            "unnamed product": {
                "hook": "A free plan that actually works.",
                "slides": ["Build a first funnel", "Keep your email together"],
                "framework": "value_stack",
                "caption": (
                    "A free plan that actually works.\nKeep the tools in one place and start through the link in bio.\n\n"
                    + copywriter.DISCLOSURE
                ),
            },
        }
        for name, bad in rejected.items():
            with self.subTest(case=name):
                self.assertFalse(llm.validate_copy(bad, product)[0])

    def test_gate_rejects_a_reused_published_opening(self) -> None:
        product = self.products[0]
        hook = f"A free plan for {product['name']}."
        draft = {
            "hook": hook,
            "slides": ["Build a first funnel", "Keep your email together"],
            "framework": "value_stack",
            "caption": (
                f"{hook}\n"
                f"{product['name']} lists a free plan in its current product details.\n"
                "Start with the free plan through the link in bio.\n\n"
                + copywriter.DISCLOSURE
            ),
        }
        with patch.object(copywriter, "recent_hooks", return_value=[]):
            self.assertTrue(llm.validate_copy(draft, product)[0])
        with patch.object(copywriter, "recent_hooks", return_value=[hook]):
            ok, reason = llm.validate_copy(draft, product)
        self.assertFalse(ok)
        self.assertIn("recently published", reason)

    def test_preferred_opening_wins_unless_a_gate_rejects_it(self) -> None:
        product = self.future_product
        payload = {
            "hooks": ["Save 10 hours every week", "One clear workflow, one tool"],
            "hook": "One clear workflow, one tool",
            "slides": ["One clear workflow", "A current plan benefit"],
            "framework": "value_stack",
            "caption": (
                "Save 10 hours every week\n"
                "One clear workflow keeps the work in one place.\n"
                "Start with Future Product through the link in bio."
            ),
        }
        with patch.object(llm, "available", return_value=True), patch.object(
            llm, "_generate", return_value=json.dumps(payload)
        ), patch.object(copywriter, "recent_hooks", return_value=[]):
            result = llm.write_copy(product, "The Quick Win", [], [], "")
        self.assertIsNotNone(result)
        self.assertEqual(result["hook"], "One clear workflow, one tool")
        self.assertTrue(result["caption"].startswith(result["hook"]))
        self.assertFalse(llm._unsupported_numbers(result["caption"], product))

    def test_duplicate_and_cta_slides_are_repaired_not_fatal(self) -> None:
        product = self.future_product
        payload = {
            "hooks": ["One clear workflow, one tool"],
            "hook": "One clear workflow, one tool",
            "slides": [
                "One clear workflow, one tool",
                "Keep email and funnels together",
                "Keep email and funnels together",
                "A current plan benefit",
                "Start free through the link in bio",
            ],
            "framework": "value_stack",
            "caption": (
                "One clear workflow, one tool\n"
                "Future Product keeps the work in one place and lists a free plan.\n"
                "Start through the link in bio, then decide."
            ),
        }
        with patch.object(llm, "available", return_value=True), patch.object(
            llm, "_generate", return_value=json.dumps(payload)
        ), patch.object(copywriter, "recent_hooks", return_value=[]):
            result = llm.write_copy(product, "The Quick Win", [], [], "")
        self.assertIsNotNone(result)
        self.assertEqual(
            result["slides"], ["Keep email and funnels together", "A current plan benefit"]
        )
        self.assertEqual(result["caption"].count("link in bio"), 1)

    def test_an_opening_with_no_body_below_it_is_rejected(self) -> None:
        product = self.future_product
        thin = {
            "hook": "One clear workflow, one tool",
            "slides": ["One clear workflow", "A current plan benefit"],
            "framework": "value_stack",
            "caption": (
                "One clear workflow, one tool\nStart free through the link in bio.\n\n"
                + copywriter.DISCLOSURE
            ),
        }
        ok, reason = llm.validate_copy(thin, product)
        self.assertFalse(ok)
        self.assertIn("body", reason)

    def test_current_cached_briefs_without_source_url_are_not_factual_inputs(self) -> None:
        disk_briefs = json.loads(briefs.BRIEFS.read_text(encoding="utf-8"))
        for product in self.products:
            entry = disk_briefs.get("products", {}).get(product["id"], {})
            if entry:
                self.assertFalse(entry.get("facts"))
                self.assertFalse(entry.get("angles"))


if __name__ == "__main__":
    unittest.main()
