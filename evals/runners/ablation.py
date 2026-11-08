"""Score recorded ablations against a named baseline on aligned jobs."""

from evals.runners.comparison import main as compare


def main():
    compare("ablation")


if __name__ == "__main__":
    main()
