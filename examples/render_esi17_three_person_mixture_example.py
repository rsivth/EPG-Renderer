from __future__ import annotations

from update_examples import render_examples


def main() -> None:
    (path,) = render_examples(("esi17-three-person-mixture",))
    print(path.name)


if __name__ == "__main__":
    main()
