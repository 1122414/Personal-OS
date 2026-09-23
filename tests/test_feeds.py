import unittest

from server.feeds import parse_feed


class FeedTests(unittest.TestCase):
    def test_rss_summary_strips_markup(self):
        content = b"<rss><channel><item><title>Agent update</title><link>https://example.com/a</link><description>&lt;b&gt;New&lt;/b&gt; runtime</description></item></channel></rss>"
        items = parse_feed(content)
        self.assertEqual(items[0]["title"], "Agent update")
        self.assertEqual(items[0]["summary"], "New runtime")

    def test_atom_entry(self):
        content = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Paper</title><link href="https://example.com/p"/><summary>Summary</summary></entry></feed>'
        self.assertEqual(parse_feed(content)[0]["url"], "https://example.com/p")


if __name__ == "__main__":
    unittest.main()
