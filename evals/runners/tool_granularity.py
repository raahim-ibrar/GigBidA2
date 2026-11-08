"""Score recorded tool conditions on the same fixed tasks."""

from evals.runners.comparison import main as compare


def main():
    compare("tool_granularity")


if __name__ == "__main__":
    main()
