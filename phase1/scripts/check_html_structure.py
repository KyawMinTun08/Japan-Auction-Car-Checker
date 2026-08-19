from html.parser import HTMLParser
from pathlib import Path


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs) -> None:
        return

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in VOID:
            self.errors.append(f"unexpected closing void tag </{tag}>")
            return
        if not self.stack:
            self.errors.append(f"unexpected closing tag </{tag}>")
            return
        if self.stack[-1] != tag:
            self.errors.append(f"expected </{self.stack[-1]}> but found </{tag}>")
            if tag in self.stack:
                self.stack = self.stack[: self.stack.index(tag)]
            return
        self.stack.pop()


root = Path(__file__).resolve().parents[2]
parser = StructureParser()
parser.feed((root / "index.html").read_text(encoding="utf-8"))
parser.close()
if parser.stack:
    parser.errors.append("unclosed tags: " + ", ".join(parser.stack[-8:]))
if parser.errors:
    raise SystemExit("HTML structure errors:\n" + "\n".join(parser.errors[:20]))
print("HTML structure OK")
