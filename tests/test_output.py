import io
import unittest

from mesh_contingency.output import SafeOutput, printable


class PrintableTest(unittest.TestCase):
    def test_terminal_sequences_are_escaped(self):
        self.assertEqual(printable("\x1b[2J\x1b[31mred"), "\\x1b[2J\\x1b[31mred")  # clear screen, colour
        self.assertEqual(printable("\x1b]0;owned\x07"), "\\x1b]0;owned\\x07")  # window title (OSC)
        self.assertEqual(printable("ok\rfake line"), "ok\\x0dfake line")  # overwrite the line
        self.assertEqual(printable("\x9b31m"), "\\x9b31m")  # 8-bit CSI
        self.assertEqual(printable("a\x00b\x7f"), "a\\x00b\\x7f")

    def test_text_direction_controls_are_escaped(self):
        self.assertEqual(printable("abc\u202edcba"), "abc\\u202edcba")
        self.assertEqual(printable("\u2066x\u2069"), "\\u2066x\\u2069")

    def test_ordinary_text_is_unchanged(self):
        for text in ["plain text", "line one\nline two\tend", "café naïve Zürich", "ok 👍 🏳️‍🌈 👨‍👩‍👧",
                     "日本語", "(1/3) John 3:16 For God so loved the world"]:
            self.assertEqual(printable(text), text)


class SafeOutputTest(unittest.TestCase):
    def test_writes_escaped_and_passes_the_rest_on(self):
        buffer = io.StringIO()
        out = SafeOutput(buffer)
        print("[a1b2] \x1b[2Jhi", file=out)
        out.flush()
        self.assertEqual(buffer.getvalue(), "[a1b2] \\x1b[2Jhi\n")
        self.assertFalse(out.isatty())

    def test_keeps_nothing_by_default(self):
        out = SafeOutput(io.StringIO())
        print("hello", file=out)
        self.assertEqual(list(out.lines), [])

    def test_keeps_the_last_lines_whole_and_escaped(self):
        out = SafeOutput(io.StringIO(), keep=2)
        print("one", file=out)
        print("two", "parts", file=out)  # written as several pieces
        out.write("three \x1b[2J")
        self.assertEqual([line for _, line in out.lines], ["one", "two parts"])
        out.write("end\nfour\n")
        self.assertEqual([line for _, line in out.lines], ["three \\x1b[2Jend", "four"])

    def test_listeners_get_each_new_line(self):
        out = SafeOutput(io.StringIO(), keep=5)
        print("old", file=out)
        heard = []

        def listener(when, line):
            heard.append(line)

        self.assertEqual([line for _, line in out.listen(listener)], ["old"])
        print("new", file=out)
        out.unlisten(listener)
        print("after", file=out)
        self.assertEqual(heard, ["new"])


if __name__ == "__main__":
    unittest.main()
