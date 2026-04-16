import json
import unittest

import main


class TextInterpreterTests(unittest.TestCase):
    def setUp(self):
        self.interpreter = main.TextInterpreter()

    def test_english_keyboard_hebrew_intended(self):
        context = self.interpreter.interpret("tbh aubt tu,l ntus.")
        self.assertEqual(context.intended_text, "אני שונא אותך מאוד.")
        self.assertEqual(context.intended_language, "Hebrew")

    def test_hebrew_keyboard_english_intended(self):
        context = self.interpreter.interpret("ןצ רקשךךט ישאק טםו")
        self.assertEqual(context.intended_text, "im really hate you")
        self.assertEqual(context.intended_language, "English")

    def test_normal_hebrew_stays_hebrew(self):
        context = self.interpreter.interpret("אני אוהב אותך אחי")
        self.assertEqual(context.intended_text, "אני אוהב אותך אחי")
        self.assertEqual(context.intended_language, "Hebrew")

    def test_normal_english_stays_english(self):
        context = self.interpreter.interpret("i really hate you")
        self.assertEqual(context.intended_text, "i really hate you")
        self.assertEqual(context.intended_language, "English")


class LocalModeratorTests(unittest.TestCase):
    def setUp(self):
        self.interpreter = main.TextInterpreter()
        self.moderator = main.LocalModerator(interpreter=self.interpreter)

    def evaluate_text(self, text):
        return self.moderator.evaluate(self.interpreter.interpret(text))

    def test_positive_hebrew_is_safe(self):
        result = self.evaluate_text("אני אוהב אותך אחי")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "SAFE")

    def test_hebrew_curse_is_harmful(self):
        result = self.evaluate_text("זונה")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "HURTFUL")
        self.assertEqual(result.language, "Hebrew")

    def test_love_plus_hate_is_harmful(self):
        result = self.evaluate_text("אני אוהב אותך אבל אני שונא אותך")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "HURTFUL")

    def test_threat_is_harmful(self):
        result = self.evaluate_text("לך תמות")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "HURTFUL")

    def test_english_insult_is_harmful(self):
        result = self.evaluate_text("i hate you")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "HURTFUL")
        self.assertEqual(result.language, "English")

    def test_mixed_language_curse_is_harmful(self):
        result = self.evaluate_text("dsum wiyh זונה")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "HURTFUL")


class AIResponseParserTests(unittest.TestCase):
    def setUp(self):
        self.interpreter = main.TextInterpreter()
        self.parser = main.AIResponseParser(self.interpreter)
        self.hebrew_candidates = self.interpreter.interpret("אני שונא אותך").candidates
        self.english_candidates = self.interpreter.interpret("i hate you").candidates

    def test_valid_json_harmful(self):
        payload = json.dumps({
            "status": "HURTFUL",
            "language": "English",
            "confidence": 0.91,
            "replacement": "I'm frustrated right now.",
        })
        result = self.parser.parse(payload, "English", self.english_candidates)
        self.assertEqual(result.status, "HURTFUL")
        self.assertEqual(result.replacement, "I'm frustrated right now")

    def test_valid_json_safe(self):
        result = self.parser.parse('{"status":"SAFE","language":"Hebrew","confidence":0.8,"replacement":""}', "Hebrew", self.hebrew_candidates)
        self.assertEqual(result.status, "SAFE")

    def test_malformed_json_falls_back_to_legacy(self):
        result = self.parser.parse("Output: I'm frustrated right now.", "English", self.english_candidates)
        self.assertEqual(result.status, "HURTFUL")
        self.assertEqual(result.replacement, "I'm frustrated right now")

    def test_wrong_language_replacement_falls_back(self):
        payload = json.dumps({
            "status": "HURTFUL",
            "language": "Hebrew",
            "confidence": 0.95,
            "replacement": "I'm frustrated right now.",
        })
        result = self.parser.parse(payload, "Hebrew", self.hebrew_candidates)
        self.assertEqual(result.replacement, "אני כועס כרגע, אבל אני לא רוצה לפגוע.")

    def test_mixed_language_replacement_falls_back(self):
        result = self.parser.parse("אני כועס כרגע. (I'm angry right now.)", "Hebrew", self.hebrew_candidates)
        self.assertEqual(result.replacement, "אני כועס כרגע")


class ReplacementPlannerTests(unittest.TestCase):
    def test_plan_keeps_raw_length_and_logical_replacement(self):
        context = main.TextInterpreter().interpret("tbh aubt tu,l")
        plan = main.ReplacementPlanner.create_plan(context, "אני כועס כרגע.")
        self.assertEqual(plan.raw_text, "tbh aubt tu,l")
        self.assertEqual(plan.raw_length, len("tbh aubt tu,l"))
        self.assertEqual(plan.replacement_text, "אני כועס כרגע.")


class PreviewSmokeTests(unittest.TestCase):
    def test_popup_formatter_does_not_reverse_hebrew(self):
        formatter = main.PopupTextFormatter()
        text, justify, anchor = formatter.label_text_options("אני כועס כרגע, אבל אני לא רוצה לפגוע", 150)
        self.assertEqual(text, "אני כועס כרגע, אבל אני לא רוצה לפגוע")
        self.assertEqual(justify, "right")
        self.assertEqual(anchor, "e")


if __name__ == "__main__":
    unittest.main()
