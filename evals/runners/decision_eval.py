"""Score recorded decisions, price bands and externally annotated claims."""

from evals.runners.offline import main as score


def main():
    score("decisions")


if __name__ == "__main__":
    main()
