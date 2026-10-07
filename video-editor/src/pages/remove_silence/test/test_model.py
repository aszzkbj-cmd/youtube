import unittest

from pages.remove_silence.model import compute_keep_segments


def rounded(segments):
    return [(round(s, 3), round(e, 3)) for s, e in segments]


class ComputeKeepSegmentsTest(unittest.TestCase):
    def test_no_silence_keeps_everything(self):
        self.assertEqual(compute_keep_segments([], 10.0, 0.15, 0.3), [(0.0, 10.0)])

    def test_middle_silence_applies_both_margins(self):
        keep = compute_keep_segments([(2.0, 5.0)], 10.0, 0.15, 0.3)
        self.assertEqual(rounded(keep), [(0.0, 2.3), (4.85, 10.0)])

    def test_leading_and_trailing_silence_skip_outer_margin(self):
        keep = compute_keep_segments([(0.0, 1.0), (8.0, 10.0)], 10.0, 0.15, 0.3)
        self.assertEqual(rounded(keep), [(0.85, 8.3)])

    def test_silence_shorter_than_margins_is_kept(self):
        keep = compute_keep_segments([(2.0, 2.4)], 10.0, 0.15, 0.3)
        self.assertEqual(keep, [(0.0, 10.0)])

    def test_all_silence_returns_empty(self):
        self.assertEqual(compute_keep_segments([(0.0, 10.0)], 10.0, 0.15, 0.3), [])

    def test_tiny_segments_are_dropped(self):
        # 두 무음 사이 음성이 margin 적용 후에도 0.05초 미만이면 버린다
        keep = compute_keep_segments([(0.0, 3.0), (3.01, 10.0)], 10.0, 0.0, 0.0)
        self.assertEqual(keep, [])

    def test_acceptance_fixture_expectation(self):
        # acceptance.md의 speech.mp4: 무음 [1,3], [4,6] → [0,1.3] + [2.85,4.3]
        keep = compute_keep_segments([(1.0, 3.0), (4.0, 6.0)], 6.0, 0.15, 0.3)
        self.assertEqual(rounded(keep), [(0.0, 1.3), (2.85, 4.3)])


if __name__ == "__main__":
    unittest.main()
