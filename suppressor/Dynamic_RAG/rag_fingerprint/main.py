import argparse

from .analyzer import analyze_extension_static
from .utils import FingerprintError


def extract_command(
    extension_path: str,
    output_dir: str,
    include_declared_third_party: bool = False,
) -> None:
    analyze_extension_static(
        target=extension_path,
        output_dir=output_dir,
        include_declared_third_party=include_declared_third_party,
    )
    print(f"Extracted fingerprint to {output_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser("rag_fingerprint")
    sub = parser.add_subparsers(dest="command", required=True)

    ex = sub.add_parser("extract")
    ex.add_argument("extension")
    ex.add_argument("--output", required=True)
    ex.add_argument("--include-declared-third-party", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "extract":
            extract_command(
                args.extension,
                args.output,
                include_declared_third_party=args.include_declared_third_party,
            )
    except FingerprintError as e:
        print(f"ERROR: {e}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
