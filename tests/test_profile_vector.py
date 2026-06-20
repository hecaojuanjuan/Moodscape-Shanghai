import unittest

from services.profile_vector import build_user_profile_vector, cosine_similarity


class ProfileVectorTest(unittest.TestCase):
    def test_core_answers_build_weighted_profile_vector(self):
        profile = build_user_profile_vector(
            {
                "pace": "slow_stop",
                "healing_space": "quiet_street",
                "shanghai_style": "old_shanghai",
            }
        )

        self.assertGreater(profile["vector"]["feature:quietness"], 1)
        self.assertIn("慢节奏", profile["traits"])
        self.assertIn("安静", profile["traits"])
        self.assertIn("老上海", profile["traits"])

    def test_skippable_answers_count_with_lower_weight(self):
        profile = build_user_profile_vector(
            {
                "pace": "slow_stop",
                "companion": "solo",
                "travel_persona": "inspiration_hunter",
            }
        )

        self.assertEqual(profile["answered_questions"], ["pace", "companion", "travel_persona"])
        self.assertEqual(profile["question_weights"]["pace"], 1.0)
        self.assertEqual(profile["question_weights"]["companion"], 0.35)
        self.assertEqual(profile["question_weights"]["travel_persona"], 0.35)
        self.assertLess(profile["vector"]["mindset:灵感"], profile["vector"]["feature:quietness"])

    def test_empty_or_skipped_answers_return_empty_profile(self):
        profile = build_user_profile_vector(
            {
                "pace": None,
                "healing_space": "",
                "companion": "unknown",
            }
        )

        self.assertEqual(profile["vector"], {})
        self.assertEqual(profile["traits"], [])
        self.assertEqual(profile["answered_questions"], [])

    def test_cosine_similarity_handles_empty_vectors(self):
        self.assertEqual(cosine_similarity({}, {"feature:quietness": 1}), 0)
        self.assertAlmostEqual(
            cosine_similarity({"a": 1, "b": 1}, {"a": 1, "b": 1}),
            1,
        )


if __name__ == "__main__":
    unittest.main()
