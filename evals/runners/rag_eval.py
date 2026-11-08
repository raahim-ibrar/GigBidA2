"""Score recorded retrieval rankings against supplied relevant evidence labels."""

from evals.runners.offline import main as score


def main():
    score("retrieval")


if __name__ == "__main__":
    main()
