import unittest

from scripts.markdown_links import heading_anchors


class MarkdownHeadingAnchorTests(unittest.TestCase):
    def test_counts_duplicate_headings_like_github(self):
        self.assertEqual(
            heading_anchors("# Recovery\n# Recovery\n## Recovery!"),
            {"recovery", "recovery-1", "recovery-2"},
        )

    def test_ignores_headings_inside_tilde_fenced_blocks(self):
        markdown = "~~~text\n# Example heading\n~~~~\n# Real heading\n"
        self.assertEqual(heading_anchors(markdown), {"real-heading"})

    def test_fence_with_trailing_text_does_not_close_block(self):
        markdown = "```text\n``` trailing text\n# Still code\n```\n# Real heading\n"
        self.assertEqual(heading_anchors(markdown), {"real-heading"})

    def test_backtick_in_info_string_does_not_open_fence(self):
        markdown = "```invalid`info\n# Real heading\n"
        self.assertEqual(heading_anchors(markdown), {"real-heading"})

    def test_normalizes_inline_code_and_unicode(self):
        self.assertEqual(heading_anchors("## `orders-api` naïve"), {"orders-api-naïve"})


if __name__ == "__main__":
    unittest.main()
