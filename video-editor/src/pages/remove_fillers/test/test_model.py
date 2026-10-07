import unittest

from pages.remove_fillers.model import (
    Word,
    compute_cuts,
    compute_keep_segments,
    detect_fillers,
    estimate_result_duration,
    normalize,
    parse_fillers,
    sentence_boundaries,
)


def rounded(segments):
    return [(round(s, 3), round(e, 3)) for s, e in segments]


def words_of(*specs):
    return [Word(text, start, end) for text, start, end in specs]


# acceptance.md의 fixture와 같은 전사 결과
FIXTURE_WORDS = words_of(
    ("안녕하세요", 0.2, 1.0),
    ("이제", 1.5, 1.8),
    ("시작합니다", 1.9, 2.6),
    ("그래서", 2.65, 2.9),
    ("진짜", 2.95, 3.5),
    ("좀", 3.55, 3.7),
    ("어려워요", 3.75, 4.5),
)
FIXTURE_SEGMENTS = [(0.2, 4.5, " 안녕하세요 이제 시작합니다. 그래서 진짜 좀 어려워요.")]
FILLERS = {"이제", "그래서", "좀"}


class ParseTest(unittest.TestCase):
    def test_normalize_strips_spaces_and_punctuation(self):
        self.assertEqual(normalize(" 이제,"), "이제")
        self.assertEqual(normalize("좀..."), "좀")

    def test_parse_fillers_skips_blank_and_comments(self):
        self.assertEqual(parse_fillers("이제\n\n# 주석\n 좀 \n"), {"이제", "좀"})


class SentenceBoundariesTest(unittest.TestCase):
    def test_uses_segment_edges_and_inner_punctuation(self):
        first, last = sentence_boundaries(FIXTURE_WORDS, FIXTURE_SEGMENTS)
        self.assertEqual([i for i, v in enumerate(first) if v], [0, 3])
        self.assertEqual([i for i, v in enumerate(last) if v], [2, 6])

    def test_token_count_mismatch_falls_back_to_segment_edges(self):
        segments = [(0.2, 4.5, "안녕하세요. 이제시작합니다. 그래서 진짜 좀 어려워요.")]
        first, last = sentence_boundaries(FIXTURE_WORDS, segments)
        self.assertEqual([i for i, v in enumerate(first) if v], [0])
        self.assertEqual([i for i, v in enumerate(last) if v], [6])

    def test_words_are_grouped_by_segment(self):
        words = words_of(("a", 0.0, 0.5), ("b", 0.6, 1.0), ("c", 2.0, 2.5), ("d", 2.6, 3.0))
        segments = [(0.0, 1.0, "a b"), (2.0, 3.0, "c d")]
        first, last = sentence_boundaries(words, segments)
        self.assertEqual(first, [True, False, True, False])
        self.assertEqual(last, [False, True, False, True])

    def test_no_segments_marks_only_overall_edges(self):
        first, last = sentence_boundaries(FIXTURE_WORDS[:3], [])
        self.assertEqual(first, [True, False, False])
        self.assertEqual(last, [False, False, True])


class DetectFillersTest(unittest.TestCase):
    def test_fixture(self):
        found = detect_fillers(FIXTURE_WORDS, FILLERS, FIXTURE_SEGMENTS)
        self.assertEqual([f.word.text for f in found], ["이제", "그래서"])
        self.assertIn("앞 간격 0.50s", found[0].reasons)
        self.assertEqual(found[1].reasons, ("문장 시작",))

    def test_filler_inside_sentence_without_gap_is_kept(self):
        found = detect_fillers(FIXTURE_WORDS, {"좀"}, FIXTURE_SEGMENTS)
        self.assertEqual(found, [])

    def test_gap_after_counts(self):
        words = words_of(("a", 0.0, 0.5), ("좀", 0.55, 0.7), ("b", 1.0, 1.5), ("c", 1.55, 2.0))
        found = detect_fillers(words, {"좀"}, [(0.0, 2.0, "a 좀 b c")])
        self.assertEqual(found[0].reasons, ("뒤 간격 0.30s",))

    def test_punctuation_in_word_is_ignored(self):
        words = words_of(("이제,", 0.0, 0.3), ("b", 0.35, 1.0))
        self.assertEqual(len(detect_fillers(words, {"이제"}, [])), 1)


class CutsTest(unittest.TestCase):
    def test_fixture_cuts_are_clamped_to_neighbours(self):
        found = detect_fillers(FIXTURE_WORDS, FILLERS, FIXTURE_SEGMENTS)
        cuts = compute_cuts(found, FIXTURE_WORDS, 6.0, 0.1, 0.15)
        # 이제: [1.4, min(1.95, 1.9)]  그래서: [max(2.55, 2.6), min(3.05, 2.95)]
        self.assertEqual(rounded(cuts), [(1.4, 1.9), (2.6, 2.95)])
        keep = compute_keep_segments(cuts, 6.0)
        self.assertEqual(rounded(keep), [(0.0, 1.4), (1.9, 2.6), (2.95, 6.0)])
        self.assertAlmostEqual(estimate_result_duration(keep, 0.05), 5.25)

    def test_adjacent_fillers_merge(self):
        words = words_of(("a", 0.0, 1.0), ("이제", 1.5, 1.8), ("좀", 1.85, 2.0), ("b", 2.5, 3.0))
        found = detect_fillers(words, {"이제", "좀"}, [])
        cuts = compute_cuts(found, words, 3.0, 0.1, 0.15)
        self.assertEqual(rounded(cuts), [(1.4, 2.15)])

    def test_cut_is_clamped_to_video_bounds(self):
        words = words_of(("이제", 0.05, 0.3), ("b", 0.8, 1.0))
        found = detect_fillers(words, {"이제"}, [])
        self.assertEqual(rounded(compute_cuts(found, words, 1.0, 0.1, 0.15)), [(0.0, 0.45)])

    def test_overlapping_whisper_timestamps_do_not_invert_cut(self):
        words = words_of(("a", 0.0, 1.6), ("이제", 1.5, 1.8), ("b", 1.7, 2.5))
        found = detect_fillers(words, {"이제"}, [(0.0, 1.8, "a 이제"), (1.7, 2.5, "b")])
        self.assertEqual(rounded(compute_cuts(found, words, 3.0, 0.1, 0.15)), [(1.5, 1.8)])

    def test_tiny_keep_segments_dropped(self):
        self.assertEqual(compute_keep_segments([(0.0, 0.98)], 1.0), [])

    def test_estimate_without_padding(self):
        self.assertAlmostEqual(estimate_result_duration([(0.0, 1.0), (2.0, 3.0)], 0.0), 2.0)


if __name__ == "__main__":
    unittest.main()
